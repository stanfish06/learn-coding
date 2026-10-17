# How the final order is produced

## 1. The mechanism is Swift's `SortComparator` + `sorted(using:)`

The binary imports exactly those, and nothing else in that family:

```
_$s10Foundation14SortComparatorP7compareySo18NSComparisonResultV8ComparedQz_AHtFTq   // compare(_:_:) -> ComparisonResult
_$s10Foundation14SortComparatorP5orderAA0B5OrderO…                                    // var order: SortOrder
_$sST10FoundationE6sorted5usingSay7ElementQzGqd___tAA14SortComparatorRd__8ComparedQyd__…  // Sequence.sorted(using:)
```

So ordering is not a hand-rolled sort and not a SQL `ORDER BY`: candidates are sorted with a
**comparator chain**, the modern Swift `SortComparator` API.

## 2. The comparators are the three rule structs

All three are empty structs (`ScoreRule`, `PrefixRule`, `FrecencyRule` have no stored fields — see
`04-ranking-fundamentals.md`), and each conforms to `SortComparator` with a shared `order` implementation:

| Rule | conformance descriptor | witness table | `compare` | `order` |
|---|---|---|---|---|
| `ScoreRule` | `0x1026a4440` | `0x102cbef10` | `0x102146dc0` | `0x102146dac` |
| `PrefixRule` | `0x1026a4388` | `0x102cbeeb0` | `0x1021466a8` | `0x102146dac` |
| `FrecencyRule` | `0x1026a4340` | `0x102cbee68` | `0x102145900` | `0x102146dac` |

`ScoreRule`'s witness table carries `Compared = Rankable` (`0x10272c758`), so the comparator operates on
`Rankable` existentials.

`ScoreRule.compare` (`0x102146dc0`) reads a `Double` out of each side through a **metadata field offset**
and returns descending for greater values:

```c
d8 = *(double *)(accessor() + fieldOffset(metadata[…]));   // lhs
d9 = …                                                     // rhs
if (d9 < d8) r8 = 1;      // rhs smaller -> orderedDescending, i.e. larger first
```

`PrefixRule.compare` (`0x1021466a8`) lowercases both operands (`Swift.String.lowercased`) and compares them
with `Swift._stringCompareWithSmolCheck` — a case-insensitive prefix test. `FrecencyRule.compare`
(`0x102145900`) tail-calls the shared helper at `0x102146988`.

## 3. The chain is configured per call site, not globally

`RankingRules` is a class holding `rules: [Rule]` (array of comparator existentials, 40 bytes each) plus
`precompute: Bool`; its accessor is `0x102146d8c` and its initializer `0x102146804`. Two distinct chains
are built in this build:

**(a) file search — `[ScoreRule, PrefixRule]`** (`0x102132064`–`0x102132090`):

```asm
adrp x8, 0x102cbe000 ; add x8, x8, #0xf00      ; ScoreRule metadata
adrp x9, 0x102cbe000 ; add x9, x9, #0xf10      ; ScoreRule witness table
stp  x8, x9, [x0, #0x38]                        ; element 0
adrp x8, … #0xed8                              ; PrefixRule metadata
adrp x9, … #0xeb0                              ; PrefixRule witness table
stp  x8, x9, [x0, #0x60]                        ; element 1
mov  x0, #0
bl   0x102146d8c                               ; RankingRules.accessor()
```

ScoreRule is stored first, PrefixRule second — so score is primary and prefix-ness breaks ties.

**(b) prefix-only — `[PrefixRule]`** at ~22 app sites, e.g. `0x100003498`:

```asm
adrp x8, … #0xed8 ; add x8, x8, #0xed8         ; PrefixRule metadata
adrp x9, … #0xeb0 ; add x9, x9, #0xeb0         ; PrefixRule witness
stp  x8, x9, [x0, #0x38]                        ; single element
bl   0x102146d8c                               ; RankingRules.accessor()
```

So different surfaces configure different orderings: file search sorts by score then prefix; many list
surfaces sort by prefix alone.

## 4. `FrecencyRule` is present but never instantiated

A whole-`__TEXT` scan for `adrp`+`add` pairs resolving into the witness-table block
(`0x102cbe000`–`0x102cc0000`) gives instantiation counts:

```
PrefixRule witness 0x102cbeeb0   22 sites
ScoreRule witness  0x102cbef10    1 site   (the file-search chain above)
FrecencyRule witness 0x102cbee68  0 sites
```

`FrecencyRule`'s type metadata (`0x102cbee90`) is referenced only by its own accessor (`0x102146654`),
which is itself never called. So frecency is **not** part of any comparator chain in this build — the
second case (after the Levenshtein function) of complete-but-unwired code.

That reframes the earlier finding about `rank(matched:term:isNormalized:new:)`: it computes the recency
`Float` and the freshness flags per record, but since no `FrecencyRule` is constructed, recency must reach
the ordering some other way — most plausibly folded into the score that `ScoreRule` compares (the packed
`RankElement.compactedData` exists precisely to pack several scores into one sortable value), or applied by
the caller outside the comparator chain. That is the remaining unknown here.

## 5. What the final order therefore is

```
candidates (one or more sources)
   │  per record: nameScore / categoryScore / termScore + recency Float  →  packed RankElement
   ▼
RankingRules(rules: [ScoreRule, PrefixRule])       ← configured per surface
   │  Sequence.sorted(using: <chain>)
   ▼
final order: score descending, then prefix-ness, then whatever the chain's tail is
```

Open items: how multiple sources' candidate arrays are merged before the sort, and whether the value
`ScoreRule` compares already contains frecency.
