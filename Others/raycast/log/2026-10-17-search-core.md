# 2026-10-17 — Raycast root search: scoring, ranking, ordering

Target: `/Applications/Raycast.app`, main binary
`Contents/MacOS/Raycast`, SHA-256 `c8ff6219fa4122ca35c646fa23638a219c69abcc6d2db81bf6931a92cbec1e95`,
52,710,128 bytes, arm64-only, symbol-obfuscated.

Scope agreed at the start: **the launcher core only** — root-search matching, scoring, ranking and
ordering. Explicitly out of scope: extensions and their Rust/V8 host, clipboard, colour picker, dictation,
snippets, window management, calendar, notes, emoji, store, cloud sync, onboarding, and the RPC layer.

Deliverable agreed: recoverable detail sufficient to reimplement, with a small CLI that exercises the
recovered behaviour.

## 1. What is recovered

Ranked by how much of the behaviour they explain. Addresses are in the arm64 image.

### Fuzzy score — the core

* Function `0x10213dd28`–`0x10213e7a0` (2,680 bytes), `evidence/07-fuzzy-score.md`.
* A **max-plus weighted subsequence alignment** — *not* an edit distance:

  ```
  dp[j] = max( dp[j-1] − 1,                  // skip a candidate character, penalty exactly 1
               dp_prev[j-1] + weight(char) ) // align a query character
  score  = max over positions                 // UInt16-saturating (`and w13, w13, #0xffff`)
  ```

* Per-character weights drawn from **{2, 3, 4, 8, 16}** (loaded as scalars *and* as `dup.2d` broadcast
  vectors). Row initialised from const vectors `(0,1) (2,3) (4,5) (6,7)`.
* Fast paths: needle longer than haystack fails outright; equal lengths take a literal compare.
* Return is packed: score in the low 16 bits, a second 16-bit field above it, tag in bits 32+.
* Named family: weighted-LCS alignment with gap penalties / max-plus (tropical) DP, local variant —
  i.e. the fzf-V2-style bonus-scored subsequence scorer. The `8`/`4` boundary-and-camel ladder plus a flat
  unit gap cost is that family's signature.
* This explains the observed behaviour with no extra machinery: `spt` aligns onto `Spotify` and scores;
  `spotifi` cannot be aligned at all (no second `i` after the `f`), and since only aligned characters
  score, it fails. There is no substitution path, hence no typo tolerance.

### The rules and the ordering

* Ordering uses Swift's **`SortComparator` + `Sequence.sorted(using:)`** (both imported; nothing else in
  that family). `evidence/09-final-order.md`.
* The comparators are three empty structs: `ScoreRule`, `PrefixRule`, `FrecencyRule`, each conforming with
  `compare` at `0x102146dc0` / `0x1021466a8` / `0x102145900` and a shared `order` thunk `0x102146dac`.
* `RankingRules { rules: [Rule], precompute: Bool }` holds the chain. It is built **per surface**:
  * file search — `[ScoreRule, PrefixRule]`, ScoreRule stored first (`0x102132064`–`0x102132090`);
  * ~22 app sites — `[PrefixRule]` alone (e.g. `0x100003498`).
* `evidence/10-rules.md` pins what they compare:
  * **`ScoreRule` reads slot `+0x34` of the compared type's metadata**, which for `FileModel`'s ten-field
    layout is **field 7 = `lastUsedAt`**, greater value first. The layout was pinned by finding that
    slot `+0x18` is read as a 16-byte `String` pair = field 0 `url`.
  * **`PrefixRule`** lowercases both names and compares them (`String.lowercased` +
    `_stringCompareWithSmolCheck`).
  * **`FrecencyRule`** is complete but instantiated at **zero** sites in this build.
* **Consequence, and it is the headline finding for ordering: the fuzzy score *filters*, `lastUsedAt`
  *orders*.** Across all 52 users of `FileModel`'s metadata accessor, every field is read except
  `score` and `imageAttributes` — the match score is never read through metadata. So the visible order of
  file results is recency-of-use first, with match quality acting as a gate.

### The ranking half

* `RootFuzzyRanking.rank(matched:term:isNormalized:new:)` at `0x102153874`, `evidence/06-rootfuzzy-ranking.md`.
* Recency is a raw **`Date.distance` interval** converted to `Float` (`fcvt s8, d0`) and stored in
  `RankElement.frecencyScore`. A **17-day cutoff** is computed with
  `Calendar(identifier: .iso8601).date(byAdding: .day, value: -17, to: now)` — the only literal constant
  in the function — and drives flag bit `0x8`.
* Output elements are 16 bytes: `Float` + three `Int16` + `Int16 0` + byte `3` + two flag bytes, with
  `UInt16` range traps. A per-record flags bitfield is assembled from three independent tests
  (kind byte → bits 1|2, set membership → bit 4, date-vs-cutoff → bit 8).

### The pipeline shape

* `RootFuzzyIndex.items(with:settings:)` at `0x10213a04c` (`evidence/05-fuzzy-algorithm.md`):
  async, normalises the term (`StringProtocol.applyingTransform`, diacritic folding), reads DB records
  (`"Failed reading all db records for fuzzy matching"`), and fans out over **four child tasks** via
  `swift_task_create` with the term captured in 105-byte closure contexts. Signposts:
  `search-index-fuzzy-records`, `search-index-fuzzy-build`, `search-index-fuzzy-items`,
  `search-ranking-fuzzy`, `search-source-fs-records`.
* Settings passed in: `struct Settings { var mode: SearchMode; var isTermNormalized: Bool }` at
  `0x10272c5a0`, with `SearchMode { staggered(…), sequential, passthrough }`. **The mode is an input, not
  a branch inside one fixed algorithm** — which is why the same matcher serves both contiguous and
  non-contiguous matching.
* The whole matcher data model is one contiguous type block (`0x10272c584`–`0x10272c7cc`), recovered from
  field descriptors: `SearchMode`, `Settings`, `SensitivityLevel`, `PrefixScore {unmatched,prefix,exact}`,
  `FuzzyScore {matched(…),unmatched,exact(…)}`, `TriggerScore {prefix(…),exact(…),overbounds(…),unmatched}`,
  `RankElement`, `RankingRules`, `ScoreRule`, `PrefixRule`, `FrecencyRule`.

### Groups (categories and sources)

`evidence/08-categories-and-sources.md`. Two orthogonal axes:

* **`category` is a per-record column** — the schema says so (`addCategoryColumnToSearchTable`), and
  `IndexedElement { id, alias, name, category, keywords, terms }` /
  `SearchScore { id, name, alias, category, terms }` carry it. `RankElement.categoryScore` is just another
  scored dimension.
* **`source` is separate** — `RootFuzzyIndex { source, corpus }`, one index per source, with app-side
  classes `RaycastSystemSource`, `RaycastCommandSource`, `RaycastExtensionsSource`,
  `RaycastDynamicExtensionsSource`, `RaycastToolSource`, `CloudSyncSearchSource`.
* `SearchScope` is *not* a group: its fields are `directory`, `resolvedFromSymlink`, `isUserScope`.
* The `cardCategory*` string family is a features taxonomy, not a search taxonomy.

### Complete-but-unwired code (three cases)

A pattern worth recording, because each one is a plausible sign of unintegrated work rather than dead
compiler output:

1. `RaycastSearch/Levenshtein.swift` — a full two-row Levenshtein DP at `0x10212772c` with **zero callers**
   (verified by a raw `bl`/`b` scan over all of `__TEXT`, validated by reproducing known call sites),
   and zero rebased or relative references. It names its own source file in its trap messages.
2. `FrecencyRule` — conformance, witness table, `compare` implementation, and zero instantiation sites.
3. A `CorrectedItem { item, name, levenshtein }` type exists, so Levenshtein *is* wired to query
   correction somewhere.

Interpretation recorded, not asserted: either unintegrated work in progress, or leftovers whose call sites
were optimised away. The signal to watch in a future build is any reference to `0x10212772c`.

## 2. What is open

Ordered by how much they block a faithful reimplementation.

| # | Open item | Where it lives | Consequence |
|---|---|---|---|
| O1 | `SensitivityLevel` → minimum-score table | the `switch` on `SensitivityLevel` (accessor `0x102144a0c`) | determines how lax matching is; currently guessed as 16/8/4 |
| O2 | which position class maps to which weight in {2,3,4,8,16} | the code computing the weight before each DP step | changes absolute scores, hence thresholds and tie behaviour |
| O3 | where the match `score` field is consumed | nothing reads `FileModel.score` through metadata | unclear whether match quality ever orders anything |
| O4 | the cross-source merge | `Search.swift` (`0x1021478f8`–`0x10214b130`), `DataSourceLoader.swift`, `SearchProviders.swift` | decides global vs per-section ordering |
| O5 | command-surface chain (the CLI's `--chain command`) | the record type command search sorts on | currently a documented guess (G6) |
| O6 | `TriggerScore` family (keyword/alias matching, `overbounds`) | not located; `strstr` is unused in the module | triggers are unmodelled |
| O7 | index build internals and the DB schema detail | `RootFuzzyIndex.init(source:)` `0x102141144`, migrations | caching and incremental update unmodelled |
| O8 | `PrefixRule`'s exact fallback | `0x1021466a8` read to completion | lexicographic fallback is a guess (G5) |
| O9 | `SearchMode.staggered` vs `sequential` selection | the callers that build `Settings` | which surface uses which mode |

## 3. Tooling built

All in `tools/`, all regenerable, no decompiler needed except for reading rule bodies:

| Tool | Purpose |
|---|---|
| `macho.py` | Mach-O reader: VM↔file mapping, relative pointers, section lookup |
| `swiftmeta.py` | decodes `__swift5_types` / `__swift5_protos` / `__swift5_proto` descriptors and conformances |
| `witnesses.py` | conformance → witness table → implementation addresses |
| `fields.py` | field descriptors: stored properties and enum cases per type |
| `vtable.py` | class metadata + vtable → method addresses |
| `report.py` | regenerates `evidence/03-ranking-addresses.md` |
| `layout_probe.py`, `exports.py` | used to settle record layout and to rule out the export trie |

Load-bearing format facts, each verified rather than assumed:

* `__swift5_proto` holds 4-byte **pointers to** 16-byte conformance descriptors
  (`Protocol, TypeRef, WitnessTable, Flags`) — 3,627/4,000 resolved to known type descriptors with that
  ordering, 0 with the alternatives.
* Witness-table entries are **8-byte chained-rebase pointers** (`target = 0x100000000 + low32`); entry 0
  points back at the conformance descriptor, which is how the decoding was verified.
* Class metadata stores its descriptor at `+0x28`; the vtable starts at `+0x38`.
* For `FileModel`, field-offset slots start at `metadata+0x18`.

## 4. Operational notes (these cost the most time)

* **REA's MCP cap is two separate timeouts.** pi's per-call limit (`mcp.json`, `"timeout"`) and REA's own
  Hopper launch/analysis/bridge/readiness deadline, default **120 s**, overridable with
  **`REA_HOPPER_STARTUP_TIMEOUT_MS`**. On a 52 MB binary the 120 s default always expires mid-analysis, so
  `open_binary` appears to work while the next call fails. Raising the env var is the fix.
* **`HOPPER_LOADER_ARGS_JSON`** replaces the loader args wholesale (e.g. adding `-f` for Swift metadata).
  Tested: it does **not** make Hopper name pure-Swift functions for this stripped binary, so it is recorded
  as a dead end rather than a fix.
* **Hopper is a singleton leased per REA session.** A timed-out analysis leaves it running (100 % CPU,
  3–5 GB RSS) and a stale lease blocks the next session until the process is killed.
* **Hopper was OOM-killed three times** on this binary. Each restart costs ~12 min of re-analysis, so
  batches should be queued in advance and bodies cached to disk.
* Driving REA directly (`/tmp/rea-raycast/driver.js`, one long-lived session + a file queue) avoids the
  MCP timeout entirely; `objdump` on raw address ranges works when Hopper is down and needs no analysis.
* `LC_FUNCTION_STARTS` (167,612 entries here) gives exact function bounds for any address — the fastest way
  to go from a hit inside a function to a read of the whole function.

## 5. Corrections made during the session

Kept visible because each one changed a conclusion:

1. **"The Levenshtein at `0x10212772c` is the matcher."** Wrong: zero callers and zero references. It is
   complete but unwired. The live scorer is the max-plus aligner.
2. **"`0x102127b4c` → `0x1021202d4` is the byte-level Levenshtein twin."** Wrong on both counts:
   `0x1021202d4` is a Swift `Array` buffer-growth helper and `0x102127b4c` is an array copy; both are
   called *inside* the DP for row copy-on-write.
3. **"Aggregation is a plain sum, so ordering uses one number."** The visitor sum is real, but ordering is
   a comparator chain over separate dimensions. The CLI originally summed frecency into the score, which
   let a keyword hit on a frequently-used item outrank an exact title match.
4. **"`rank()` has no string matching, so where does `spt` → Spotify come from?"** Not a contradiction:
   matching and ranking are two halves. The matching half is the async index retrieval.
5. **CLI bug: score = last DP cell.** The binary takes the maximum over positions; the first
   implementation returned the final cell, which silently rejected good matches.
6. **`swiftmeta.conformances()` was wrong for a long stretch** — it assumed 16-byte inline records instead
   of 4-byte pointers to descriptors, and dropped conformances whose protocol lives in another dylib
   (exactly the `SortComparator` case we needed).
7. **`SearchScope` was guessed to be the group enum.** It is a filesystem search scope.

## 6. Deliverables in this repo

```
evidence/00-target.md              bundle, hashes, module inventory, launcher class map
evidence/01-ranking-scope.md       the RaycastSearch module, protocol family, file inventory
evidence/02-toolchain.md           REA/Hopper knobs, driver usage, failure modes
evidence/03-ranking-addresses.md   generated address map (type/protocol/conformance/witness)
evidence/04-ranking-fundamentals.md data model and scoring mechanics
evidence/05-fuzzy-algorithm.md     subsystem API, settings, match families, dead-code record
evidence/06-rootfuzzy-ranking.md   rank(matched:term:isNormalized:new:) mechanism
evidence/07-fuzzy-score.md         the score computation + nomenclature
evidence/08-categories-and-sources.md  how groups enter search
evidence/09-final-order.md         the comparator chain
evidence/10-rules.md               what each rule compares
src/rank.swift                     the pipeline: aligner → classification → RankElement → rule chain
tests/items.json, tests/run.sh     23 assertions over the recovered behaviour
tools/                             the parsers used for the metadata walk
log/                               this file
```

`tests/run.sh` currently passes 23 checks: the gate (`spotifi` yields nothing, `spt` yields Spotify),
prefix/exact classification, the file chain ordering by recency with the deciding rule named per
comparison, the guessed command chain ordering by score, the empty-query state, the 17-day freshness
window, and chain-consistency invariants across queries.

## 7. Where to start next

1. **O1 then O2** — both are single-site reads (`SensitivityLevel`'s switch; the weight computation feeding
   the DP) and together they turn the scorer from "structurally right" into "numerically right".
   Queue the work with the driver, since each Hopper restart costs ~12 minutes.
2. **O4** — read the `Search.swift` pipeline for the merge step, which answers global-vs-section ordering.
3. **O3** — search for the consumer of `FileModel.score` by looking for it being *written* and following
   the value outward, since no metadata reader takes it.
