# The fuzzy score computation (recovered)

Function `0x10213dd28`–`0x10213e7a0` (2,680 bytes) in the `RaycastSearch` region, found by locating
`LC_FUNCTION_STARTS` bounds around a byte-scan DP. This is what turns a query and a candidate string into
the number that ranking consumes.

## Signature shape (from the prologue)

```asm
stur w2, [x29, #-0x6c]      ; 4th arg stashed (a mode/options word)
cmp  x4, x1                 ; lenB vs lenA
b.ge …                      ; needle longer than haystack -> return tag 0x1_00000000, score 0
cmp  x1, x4
b.ne …                      ; equal lengths -> call 0x1013e91c4 (literal compare), return w0 & 1
```

So: two buffers with lengths, plus an options word; with a fast path for equal length (exact comparison)
and a fail path when the needle is longer than the haystack.

## It is a max-plus alignment DP, not edit distance

The inner loop (`0x10213e5d0`–`0x10213e604`):

```asm
ldrh w12, [x9], #0x2        ; w12 = dp[position]           (UInt16 cell, post-increment)
cmp  x25, x11               ; needle index vs position
cset w13, ne                ; 1 when off-diagonal / not a match
sub  w13, w8, w13           ; w13 = weight - penalty
add  w13, w13, w12          ; + dp[previous row at this position]
and  w13, w13, #0xffff      ; saturate back to UInt16
and  w14, w10, #0xffff
cmp  w13, w14
csel w13, w13, w14, hi      ; keep the larger candidate
cmp  w12, #0x0
csel w10, w10, w13, eq      ; only replace the running best when the cell existed
add  x11, x11, #1
cmp  x22, x11
b.ne 0x10213e5d0
```

Read as an algorithm:

```
candidate = weight(char) − (not a diagonal match ? 1 : 0) + dp_previous[position]
dp[position]  = max(candidate, dp[position])      // UInt16, saturating via `and #0xffff`
```

* **Maximisation** (`csel … hi`), where Levenshtein would minimise.
* **Skip penalty is exactly 1** (`cset w13, ne` then subtract) — one unit per non-diagonal step.
* **16-bit saturating arithmetic** (`and w13, w13, #0xffff`) — the DP row is `UInt16`, not `Int`.
* Rolling row: the table is one row of `UInt16` cells read with `ldrh … , #0x2` (2 bytes per cell).

## The weights

Weights appear as both scalar `mov` immediates and as broadcast SIMD vectors (`dup.2d`), i.e. the same
values are used in a vectorised bulk pass and in the scalar loop:

```asm
mov w8, #0x4 ; dup.2d v27, x8      ; 4
mov w8, #0x8 ; dup.2d v28, x8      ; 8
mov w8, #0x10 ; dup.2d v29, x8     ; 16
… mov w8, #0x2                     ; 2   (scalar path)
… mov w8, #0x3                     ; 3
```

So per-character weights come from the set **{2, 3, 4, 8, 16}**, with `4/8/16` also used vectorised. The
staircase 4 → 8 → 16 is the familiar "better position class gets a bigger bonus" ladder (word start /
camel case / …); `2` and `3` are the weaker classes.

The DP row is initialised from const vectors holding the pairs **(0,1), (2,3), (4,5), (6,7)** — i.e. the
base row counts 0…7 as two 64-bit lanes per load:

```
0x1025aa2f0: 0,1      0x102657510: 2,3      0x1026a2790: 4,5      0x1026a2780: 6,7
```

## Return value

```asm
and  w9, w19, #0xffff      ; low 16 bits  = score
lsl  w20, w9, #16          ; next 16 bits = second field (counter/length), shifted in
orr  x0, x8, x9            ; packed 64-bit result
```

Early exits use `mov x8, #0x1_00000000`, i.e. a tag in bits 32+ that distinguishes "no match / fast path"
from a scored result. So the function returns a **packed (score, second field, tag)** value rather than a
plain integer — which is how a `FuzzyScore` case with associated values can carry the score *and* the
match data in one register pair.

## What this settles

* The fuzzy score is a **weighted subsequence alignment score**, maximised over positions, saturating at
  16 bits, with a **per-skip penalty of 1** and per-character bonuses from **{2,3,4,8,16}**.
* It is **not** Levenshtein: that function (`0x10212772c`) minimises and is unreferenced; this one maximises
  and sits in the live path's address neighbourhood.
* It explains the observed behaviour without any typo tolerance: `spt` aligns onto `Spotify` as a
  subsequence and scores; `spotifi` cannot be aligned at all against `spotify` (no such subsequence), and
  since the score only rewards aligned characters, it fails — no substitution is ever attempted.

## Nomenclature — what to call this algorithm

**Precise name: weighted longest-common-subsequence alignment with gap penalties, computed as a
max-plus (tropical) dynamic program — in its local variant** (the score is the maximum over end
positions, not the value of a fixed final cell).

Why LCS-family rather than Smith–Waterman: the scan only ever *aligns equal characters*. On a mismatch it
advances the candidate index alone, which makes the step a gap, not a substitution:

```asm
10213dfb8: ldrb w8, [x16, x19]     ; candidate character
10213dfbc: cmp  w8, w2             ; vs current query character
10213dfc0: b.ne 0x10213df9c        ; not equal -> advance candidate only (gap, cost 1)
```

This is also *why* there is no typo tolerance: an unalignable query fails outright instead of being
aligned with a penalty. Both the instruction evidence and the observed behaviour (`spt` matches,
`spotifi` does not) point the same way.

If a substitution path were ever found, the textbook name would become **Smith–Waterman local alignment**
instead. Nothing so far suggests one.

Alternative names by community:

| Community | Name |
|---|---|
| Algorithms / bioinformatics | weighted LCS alignment; max-plus DP; longest path on a DAG |
| Fuzzy finders | **fzf V2-style fuzzy scoring** ("scheme 2"); bonus-scored subsequence scoring |
| Editors | VSCode / Sublime Text-style fuzzy scoring (Forrest Smith's Sublime reverse-engineering writeup describes this exact structure) |

The constant ladder is that family's signature, and Raycast's variant is a simplified member of it:

| | fzf V2 | VSCode | Raycast (recovered) |
|---|---|---|---|
| per-match score | `SCORE_MATCH = 16` | `Score.Match = 1` | one of **{2,3,4,8,16}** |
| word-boundary bonus | `BONUS_BOUNDARY = 8` | `Bonus.Boundary = 8` | **8** |
| camel-case bonus | `BONUS_CAMEL123 = 7` | `Bonus.CamelCase = 4` | **4** |
| gap penalty | `SCORE_GAP_START = −3`, `−1` extension | `GapStart = −3`, `GapExtension = −1` | **−1 flat** |
| row arithmetic | signed `int16` with floor | `int16` with floor | `UInt16` with `and #0xffff` saturation |

Raycast's differs from fzf's in being simpler: a flat unit gap cost (no start/extension split) and
saturating unsigned arithmetic rather than a signed floor.

**What it is not** — worth ruling out explicitly, because "fuzzy match" is used loosely:

* Levenshtein / Damerau-Levenshtein — those *minimise* an edit count; the Levenshtein function in this
  binary (`0x10212772c`) is unreferenced dead code.
* Jaro / Jaro-Winkler — no transposition window or prefix scaling here.
* Trigram / cosine / token-set similarity — no n-gram index or vector arithmetic in the scorer.
* `fzf --fuzzy` — that flag adds *query typo* matching; this scorer never substitutes.

One-line description for reuse: **a bonus-scored subsequence alignment (max-plus DP), i.e. an
LCS-with-gap-penalties score — not an edit distance.**

## Still open

* Which position class maps to 2 vs 3 vs 4 vs 8 vs 16 (the ladder is read, the classifier that selects it
  is not).
* How the packed second field is used by the caller (`rank(...)` / `RankingRules`).
* Where this function's `FuzzyScore` case is chosen — the thresholds that turn a score into
  `exact` / `matched` / `unmatched`, and where `SensitivityLevel` enters that decision.
