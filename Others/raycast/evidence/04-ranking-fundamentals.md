# Ranking fundamentals (data model + scoring mechanics)

Everything here is read out of the binary; each claim names the evidence it came from.
Regenerate the inputs with `tools/fields.py` (field descriptors), `tools/vtable.py` (class vtables),
`tools/witnesses.py` (protocol conformances), and the Hopper session driver (decompilation).

## 1. Data model — `RaycastSearch` ranking types

From `__swift5_fieldmd` (field descriptors), which survive stripping:

| Type | Kind | Fields / cases |
|---|---|---|
| `SearchScore` | struct | `id: Int`, `name`, `alias`, `category`, `terms` |
| `RankElement` | struct | `frecencyScore: Float`, `recordOffset`, `nameScore`, `categoryScore`, `termScore`, `contentType`, `compactedData` |
| `PrefixScore` | enum | `unmatched`, `prefix`, `exact` |
| `FuzzyScore` | enum | `matched(…)`, `unmatched`, `exact(…)` |
| `TriggerScore` | enum | `prefix`, `exact`, `overbounds`, `unmatched` |
| `SensitivityLevel` | enum | `low`, `medium`, `high` |
| `SearchMode` | enum | `staggered(…)`, `sequential`, `passthrough` |
| `FuzzySettings` | enum | `staggered(…)`, `sequential` |
| `RootFuzzyIndex` | struct | `source`, `corpus` |
| `Trie` | class | `root` |
| `TrieNode` | class | `key`, `parent`, `children`, `isTerminating`, `path`, `mask`, `meta` |
| `TrieMatch` | struct | `value`, `indices`, `meta` |
| `RankingRules` | class | `rules: [Rule]`, `precompute: Bool` |
| `RootFuzzyRanking` | **uninhabited enum** | — (namespace of static functions) |
| `Levenshtein` | **uninhabited enum** | — |
| `Frecency` | **uninhabited enum** | — |
| `ScoreRule` | **uninhabited enum** | — |

Two consequences that shape the rest of the work:

* Scores are **categorical first, numeric second**: match quality is an enum case
  (`exact` / `prefix` / `matched` / `unmatched` / `overbounds`), and numbers appear only where those
  cases are converted. There is no single "similarity float" in the data model.
* `RootFuzzyRanking`, `Levenshtein`, `Frecency` and `ScoreRule` are uninhabited enums, i.e. pure
  namespaces. Their functions are static, so they do **not** appear in any vtable or witness table —
  they must be located through their call sites.

## 2. Aggregation: the combined score is a plain sum

`CombinedScoreVisitor` (implementation `0x10212d334`, witness table `0x102cbe110`) decompiles to:

```c
r21 = sub_10212b994(0);                 // CombinedScoreVisitor metadata (swift_getSingletonMetadata)
d8  = *(double *)(r0 + r21[0xd]);       // accumulator field, read via the metadata field offset
r23 = visitorCount;                     // [visitor] array count
r19 = visitors + 0x20;                  // array payload, 0x28 bytes per element
do {
    sub_100016784(r19, &saved);         // copy the visitor existential
    d0 = witness[1](&item, ...);        // call visitor -> its Double score
    d8 = d8 + d0;                       // SUM
    r19 += 0x28; r23 -= 1;
} while (r23 != 0);
```

So: `combined(item) = Σ visitor_i(item)` over an array of visitors (40-byte stride).

## 3. Ordering: `ScoreRule` compares a stored value

`ScoreRule` (`0x102146dc0`) is a comparator, not a scorer:

```c
r21 = metadata(descriptor 0x1026a4370); r22 = metadata(descriptor 0x1026a3af0);
r19 = swift_dynamicCast(&box, &lhs, r21, r22, 6);
if (r19) { d8 = *(double *)(accessor() + fieldOffset(metadata[0xd])); ... } else { fallback(&box); }
... same for the rhs -> d9 ...
if (d9 < d8) r8 = 1;                    // descending by score
return r19 ? r8 : 0;
```

The value is read from the item through a **metadata field offset** (`metadata[0xd]`), which is why the
comparator works for any `Rankable` regardless of layout. `PrefixRule` (`0x1021466ac`) by contrast
lowercases both operands (`Swift.String.lowercased`) and compares them
(`Swift._stringCompareWithSmolCheck`) — a case-insensitive prefix test.

`RankingRules` is a class holding `rules: [Rule]` plus a `precompute` flag. Its vtable
(`metadata 0x102f058c8` + `0x38`) only yields `init` (`0x102146804`) and `deinit`
(`0x102148428`) — its ranking methods are `final`/extension functions and therefore not in the vtable.

### Ordering is a comparator chain, not one number

`rules: [Rule]` with the rule types `ScoreRule` / `PrefixRule` / `FrecencyRule`, and `RankElement`
carrying **separate** `nameScore`, `categoryScore`, `termScore`, `frecencyScore` fields, together mean
the ordering compares dimensions in sequence rather than summing them into a single value. This matters:
with a summed score, a keyword match on a high-frecency item can outrank an exact title match. The CLI
implements the chain as `nameScore → termScore → frecencyScore → input order`
(`src/rank.swift`, `rank(...)`); `ScoreRule`'s own "score" dimension is the one whose field offset is
read at `metadata[0xd]`.

## 4. Per-field scorers

Five visitors, all conforming to a single internal protocol (witness tables adjacent in
`__DATA_CONST.__const`), each returning a contribution for its field:

| Visitor | Witness table | Body | Field it scores | Signals seen in code |
|---|---|---|---|---|
| `FileNameScoreVisitor` | `0x102cbe100` | `0x10212dd10` | file name / extension | `Foundation.URL.pathExtension.getter`, `Swift.StringProtocol.localizedStandardRange`, constants **+2.0** and **+1.0** |
| `FilePathScoreVisitor` | `0x102cbe0d0` | `0x10212e04c` | full path | `swift_dynamicCast`, path manipulation helpers |
| `FileDateScoreVisitor` | `0x102cbe0e0` | `0x10212da84` | modification date | `type metadata accessor for Foundation.Date` |
| `FileContentTypeScoreVisitor` | `0x102cbe0f0` | `0x10212e278` | UTI / content type | `UniformTypeIdentifiers.UTType` (`isDeclared`, `applicationBundle`, `identifier`), constants **+2.0** and **−4.0** |
| `CombinedScoreVisitor` | `0x102cbe110` | `0x10212d334` | aggregation | sum loop, see §2 |

The constants appear in the recurring shape `d0 = *(score)…; d1 = <constant>`, i.e. the running score and
a constant are handed to a helper — the visible numeric anchors are **+2.0 / +1.0 for name matches** and
**+2.0 / −4.0 for content-type matches and mismatches**.

## 5. Frecency

* `RankElement.frecencyScore` is a **`Float`** (`Sf`), while the other scores are `Double`-typed in code.
* `Frecency` is a namespace enum; the string table also carries `FrecenciesWithNewHalfLifeValue`, so
  decay is expressed as a **half-life** over elapsed time.
* `FrecencyRule` (`0x102145904`) forwards to `0x102145904`→`sub_102145904` and `0x102146988`, whose bodies
  are small wrappers around `Foundation.Date` conversions — the arithmetic itself is inlined from
  `Frecency`'s static functions.

## 6. What is still open

1. The **case → number mapping** per scorer (which of `exact` / `prefix` / `matched` / `unmatched` /
   `overbounds` yields which constant, and how `SearchMode` / `SensitivityLevel` gate them).
2. The **fuzzy matching algorithm** itself (`FuzzyScore`'s associated values, `RootFuzzyRanking`'s static
   functions) and `Levenshtein`'s use for typo tolerance.
3. The **frecency formula** (half-life value, weighting of count vs recency).

Recommended next probes, in order:

* Read the full bodies of `0x10212dd10` / `0x10212e278` with register-level care — the branch targets and
  the helper called with `(score, constant)` give the case → number mapping directly.
* Find writers of `RankElement`'s score fields: `RankElement`'s field offsets are known from its metadata,
  so stores through those offsets locate the code that computes `nameScore` / `categoryScore` /
  `termScore` / `frecencyScore`.
* Locate the namespace-enum statics through their call sites: `FuzzyScore` / `PrefixScore` /
  `TriggerScore` metadata accessors are known (`0x102144c78`, `0x102144c54`, `0x102144dcc`), so callers of
  those accessors are the conversion sites.
