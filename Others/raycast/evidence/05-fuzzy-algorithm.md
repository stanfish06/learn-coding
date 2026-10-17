# The fuzzy algorithm (recovered)

Evidence: decompiled bodies from the live Hopper session (`procedure_pseudo_code`), plus the field
descriptors. Addresses are in the arm64 image (base `0x100000000`).

## 1. Levenshtein distance — `RaycastSearch/Levenshtein.swift`

Two implementations exist; both are character/byte-level Levenshtein with **two rolling rows**
(memory O(n), not a full matrix).

**Swift-string variant — `0x10212772c`** (421 lines of pseudocode, the meaty one). The trap call inside
it names its own source:

```
sub_1012e3a1c(…, "RaycastSearch/Levenshtein.swift", 0x1f, 0x2, 0x13, …)
```

Structure, in order:

```c
n = String.count(query)                                     // query length
row_prev = Array._allocateBufferUninitialized(n, minimumCapacity: n)   // buffer of n+1
bzero(row_prev + 0x20, n << 3)
row_cur  = <Array(repeating: 0, count: n + 1)>              // sub_10057bec8 fills 0…n
for each character T in target {                            // outer: target characters
    for i in 0..<n {                                        // inner: query characters
        if T == Q[i] {                                      // Swift._stringCompareWithSmolCheck
            row_cur[i+1] = row_prev[i];
        } else {
            // up / left / diagonal, then +1  -> classic recurrence
            v = row_cur[i];        // *(r23 + i*8 + 0x20)
            u = row_cur[i+1];      // *(r23 + i*8 + 0x28)
            d = row_prev[i];       // *(r24 + i*8 + 0x20)
            if (u < v) v = u;
            if (d < v) v = d;      // min(up, left, diagonal)
            row_cur[i+1] = v + 1;
        }
    }
    swap(row_prev, row_cur);
}
distance = row_current[last]                                // *(r24 + n*8 + 0x18)
```

So the recurrence is exactly

```
d[i][j] = (t_j == q_i) ? d[i-1][j-1] : 1 + min(d[i-1][j], d[i][j-1], d[i-1][j-1])
```

with `Array` bounds checks that trap (`brk #0x1`) if any index leaves its buffer, and
`swift_isUniquelyReferenced_nonNull_native` + `sub_102127b4c` for row copy-on-write.

### Reachability: this function is dead code in the shipped binary

A raw instruction scan over the whole of `__TEXT` (every `bl`/`b` word, PC-relative target decoded)
finds **zero callers** of `0x10212772c`; `xrefs`, rebased-pointer and relative-pointer scans all return
nothing too. The same holds for the `withCString` wrapper `0x102127acc`. The scan was validated against a
known call site: it reproduces the five callers of the array helper `0x1021202d4` exactly.

So the DP above is a *recovered algorithm*, not the live code path. Generic specialization in Swift
produces the reachable copies by inlining; the standalone copy stayed in the image and is unreferenced.

**How to read that**: either it is work the Raycast team is testing but has not integrated yet, or it is a
leftover specialization whose call sites were optimised away. Both are consistent with the evidence; the
distinguishing detail is that the function is complete and correct (it names its own source file, carries
proper trap messages, and implements a full two-row DP), which is more consistent with deliberate code
that is simply not wired up than with dead compiler output. It is kept in `src/rank.swift` on purpose, as
the marker for "typo tolerance would live here" — if a future build starts referencing `0x10212772c`,
that is the change to look for.

**Correction to an earlier claim in this file:** the pair `0x102127b4c` → `0x1021202d4` is *not* a
byte-level distance twin. `0x1021202d4` is a Swift `Array` buffer-growth helper (called with
`(isUnique, newCount, elementSize, array)` and followed by an element store at `array + n*8 + 0x20`), and
`0x102127b4c` is an array copy — both are called repeatedly from inside the DP for row copy-on-write.

## 1b. The matcher's API and settings (recovered)

`0x10213a04c` (`RaycastSearch/RootFuzzyIndex.swift`, 138 K chars of heavily inlined code) carries its own
function name in a trap-message literal, which names the entry point:

```
items(with:settings:)                     ← the fuzzy-match entry point
"search-index-fuzzy-items"                ← os_signpost name
"Fuzzy index retrieval"                   ← signpost/description
"Failed reading all db records for fuzzy matching"   ← error string
"RaycastSearch/RootFuzzyIndex.swift"      ← source path
```

The `settings:` argument type is recoverable too. Two `Settings` structs exist; the one in the matcher's
own type block is:

```swift
struct Settings {          // 0x10272c5a0, RaycastSearch
    var mode: SearchMode            // staggered | sequential | passthrough
    var isTermNormalized: Bool
}
```

The whole matcher data model sits in one contiguous type block:

```
0x10272c584  SearchMode    { staggered(…), sequential, passthrough }
0x10272c5a0  Settings      { mode, isTermNormalized }
0x10272c5bc  SensitivityLevel { low, medium, high }
0x10272c5d8  PrefixScore   { unmatched, prefix, exact }
0x10272c5f4  FuzzyScore    { matched(…), unmatched, exact(…) }
0x10272c610  TriggerScore  { prefix(…), exact(…), overbounds(…), unmatched }
0x10272c62c  RootFuzzyRanking   (uninhabited enum — statics)
0x10272c650  RankElement   { frecencyScore: Float, recordOffset, nameScore, categoryScore,
                             termScore, contentType, compactedData }
0x10272c6f4  RankingRules  (class, rules: [Rule], precompute: Bool)
```

So the *mode is passed in by the caller* (`settings.mode`), which is why the same matcher serves both
staggered (non-contiguous) and sequential (contiguous) behaviour.

The ranking half has its own named entry point. `0x102153874`
(`RaycastSearch/RootFuzzyRanking.swift`, 47 K chars) carries:

```
rank(matched:term:isNormalized:new:)      ← the ranking entry point and its argument labels
"search-ranking-fuzzy"                    ← os_signpost name
"RaycastSearch/RootFuzzyRanking.swift"    ← source path
```

So the two halves of the subsystem, with argument labels:

```swift
// RaycastSearch/RootFuzzyIndex.swift
func items(with term: String, settings: Settings) -> [Item]        // 0x10213a04c

// RaycastSearch/RootFuzzyRanking.swift
static func rank(matched: [Item], term: String,
                 isNormalized: Bool, new: Bool) -> [Ranked]        // 0x102153874
```

`isNormalized` appears in both the settings struct and this signature; `new:` is the remaining unknown
flag. The flow implied by the labels: `items(with:settings:)` produces the matched candidate set, then
`rank(matched:term:isNormalized:new:)` scores and orders it.

Term normalisation inside the retrieval path uses `StringProtocol.applyingTransform` (diacritic folding),
which is what `isTermNormalized` tracks; the normaliser helper `0x10213e8b4` is called from eight sites,
including `0x10214788c` (Search.swift) and `0x102155840`/`0x102155864` (RootFuzzyRanking.swift).

## 1c. What each family is, now that the pieces line up

| Family | Mechanism | Where read |
|---|---|---|
| sequential | contiguous substring/`hasPrefix` style test | `hasPrefix` sites (bitmask prefilter + confirmation) |
| staggered | non-contiguous character match producing matched indices | mode flag + `TrieMatch.indices`; body not yet isolated |
| trigger | keyword/alias match with boundary awareness (`overbounds`) | not yet located |

`TrieMatch { value, indices, meta }` is the staggered result shape: the matched text plus the positions
that matched — exactly what a non-contiguous match must carry and a contiguous one does not need.

## 2. Where the live matcher probably is

The reachable fuzzy path cannot be the standalone DP, and `strstr` is not used anywhere in the
`RaycastSearch` module, so the likely shape is **bounded edit distance inside the index traversal**:

* `TrieNode` carries `key, parent, children, isTerminating, path, mask, meta` — `mask` is a bitmask,
  and the prefix sites confirm bitmask prefiltering is how this code narrows candidates
  (bitset iteration with `rbit`/`clz`/`x & (x-1)`, then confirmation).
* `TrieMatch { value, indices, meta }` carries positions, so traversal yields the match path.
* `SensitivityLevel` would then set the bound that prunes traversal, which is exactly the parameter whose
  value never appears as a literal inside the distance routine.

Untested: this is an inference from structure, not from reading the traversal code.

## 2b. Where the term actually meets the records

`items(with:settings:)` (`0x10213a04c`) is `async` and splits its work across **four concurrent child tasks**:

```c
Swift.withTaskGroup<A, B>();                                  // 2 variants, picked by an OS-version check
Swift.Task.checkCancellation(task);
swift_task_create(0x3100, ctx, closureContext, asyncFnPointer, …)   // x4
```

Each task gets a freshly allocated closure context
(`swift_allocObject(0x102cbe668, 0x69, …)` — 105 bytes, holding the normalised term and settings), and the
async-function-pointer tables sit in `__TEXT.__const` (`0x1026a3e68` → `0x100076edc`, which is itself a
partial-apply thunk whose closure body is `0x100076f40`).

The continuation (`0x10213b460`) then walks the records that came back and keeps only those that survive a
predicate:

```c
do {
    sub_1016aee88(record, tmp);            // copy the record
    if (record[0x8] == 0x1) { …skip… }     // kind filter
    r0 = sub_1000f299c(*record);           // Hasher-based Set membership (pointer identity)
    if ((r1 & 0x1) != 0x0) { append(result); }
    record += stride;
} while (--count);
```

So the pipeline is: **term + settings → normalised, captured into worker tasks → per-record predicates →
matched set → `rank(matched:term:isNormalized:new:)` for recency/freshness flags**.

This is the answer to "if `rank()` has no string matching, how does `spt` find Spotify": the comparison is
in the *retrieval half*, behind task-group dispatch, not in the ranking half. Which predicate performs the
character comparison is still unresolved — the workers are reached indirectly, and Hopper (the only
decompiler available here) has been OOM-killed three times on this 52 MB binary, so those closure bodies
have not been decompiled yet. `objdump` can disassemble arbitrary ranges without analysis, so the next
attempt should read the worker closure in assembly.

## 2c. Why the match loop resists static reading

The retrieval path is a chain of *indirect* targets, each one resolvable only by decoding tables:

```
items(with:settings:)                      0x10213a04c
  └─ withTaskGroup → swift_task_create(…, asyncFnPointerTable, closureContext)   ×4
       table 0x1026a3e60  → closure body   0x102142640      (partial-apply thunk 0x100076edc)
       captured state    swift_allocObject(0x102cbe668, 0x69, …)  105 bytes = term + settings
  └─ continuation                           0x10213b460
       └─ per-record predicates: Set membership (0x1000f299c, Hasher + bitset, pointer identity)
```

`0x102142640` itself copies its captured context field-by-field through a **metadata field-offset table**
(`ldrsw x8, [x23, #0x30]` … `ldrb w9, [x20, x8]`) and then calls yet another closure via `blr x8`.

Consequences for this investigation: no call-graph edge, no xref, and no rebased/relative pointer exists
for the interesting bodies, because every hop is a function pointer carried in a heap context. Each step
has to be resolved by decoding the table that supplies the pointer, and Hopper — the only decompiler
available here — was OOM-killed three times on this 52 MB image, so those bodies currently have to be read
as raw `objdump` output.

## 3. How distance becomes a score

The distance is consumed through the score enums recovered from field descriptors:

```
PrefixScore  : unmatched | prefix | exact
FuzzyScore   : matched(…) | unmatched | exact(…)
TriggerScore : prefix | exact | overbounds | unmatched
SensitivityLevel : low | medium | high
SearchMode   : staggered(…) | sequential | passthrough
```

Read together with the code, this gives:

| Signal | Meaning |
|---|---|
| `exact` | distance 0 (or a literal equality check for the prefix/trigger families) |
| `matched` | within the edit budget — the budget is what `SensitivityLevel` selects |
| `unmatched` | beyond the budget |
| `overbounds` | match extends past the term's bounds (matched inside a longer field) |
| `prefix` | matched at the start of the field |

`SensitivityLevel.low/medium/high` therefore map to *distance thresholds*; the numeric thresholds
themselves are not yet recovered (they are not literal constants in the Levenshtein function — they are
applied by the caller that turns a distance into `FuzzyScore`).

## 4. What the scorers do with it

`SearchScore` (the searchable record) carries `id, name, alias, category, terms`. `RankElement` carries
the per-item results `nameScore`, `categoryScore`, `termScore`, `frecencyScore: Float`, `contentType`
and `compactedData`. `RootFuzzyRanking` is a namespace (uninhabited enum) that turns
`(query, SearchScore)` into those per-field scores; `RankingRules` (class, `rules: [Rule]`,
`precompute: Bool`) applies them, and `CombinedScoreVisitor` sums the visitor contributions
(see `04-ranking-fundamentals.md`).

Per-field constants observed in the visitor bodies: name **+2.0** (exact) / **+1.0** (matched);
content type **+2.0** (match) / **−4.0** (mismatch).

## 5. Consequences for a reimplementation

1. Matching is **edit-distance based, not subsequence based**: transpositions cost 2 (no
   Damerau extension), and a long query against a short target simply fails the threshold.
2. Cost is `O(len(target) × len(query))` with `O(len(query))` memory per comparison, per field, per
   candidate — so the index (`RootFuzzyIndex`, `Trie`, `FuzzyAutoCompletion`) exists to avoid running it
   on everything.
3. Case handling: the visitor bodies lowercase with `Swift.String.lowercased` before comparing, so
   matching is case-insensitive but **not** diacritic-insensitive.
4. `TriggerScore.overbounds` implies triggers (keywords/aliases) are matched with an explicit
   bounds check rather than a plain `contains`.

## 6. Open items

* The `SensitivityLevel` → distance-threshold table, and where the score enums are converted to the
  `Double`s that `ScoreRule` reads.
* The reachable fuzzy matcher (candidates: `Trie.swift` traversal `0x1021296dc`/`0x102129e18`/`0x10212a5c0`,
  `RootFuzzyIndex.swift` `0x10213a04c`/`0x102141144`, and the `Search.swift` pipeline functions
  `0x1021478f8`–`0x10214b130`).
* `RootFuzzyIndex.corpus` layout and how candidates are selected before scoring (the index side).
* `Frecency`'s half-life formula (`FrecenciesWithNewHalfLifeValue`).
