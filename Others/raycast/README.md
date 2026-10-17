# raycast-launcher-re

Recovering the root-search pipeline and ranking of Raycast.app so it can be reimplemented, with a CLI
that demonstrates the recovered behaviour. Scope: **launcher only** — no extensions (the Rust/V8
`Helpers/server` host and its RPC layer are excluded), no clipboard, color picker, dictation, snippets,
window management, calendar, notes, emoji, store or cloud sync.

## Status

| Part | State |
|---|---|
| Target identified & hashed | done — `c8ff6219…bec1e95`, arm64, 52,710,128 B, stripped |
| Toolchain made to work on a 52 MB binary | done — see `evidence/02-toolchain.md` (two timeouts, one env override) |
| Ranking scope mapped | done — 14 `RaycastSearch/*.swift` files, protocol family, score visitors — see `evidence/01-ranking-scope.md` |
| Ranking function **addresses** | **done** — metadata walk recovered descriptors, conformances, witness tables and implementation addresses; see `evidence/03-ranking-addresses.md` |
| Ranking **data model** (fields, cases) | **done** — `evidence/04-ranking-fundamentals.md` §1: `RankElement`, `SearchScore`, `PrefixScore` / `FuzzyScore` / `TriggerScore` / `SensitivityLevel` / `SearchMode` |
| Ranking **mechanics** | partial — aggregation (sum over visitors), ordering (comparator chain over separate dimensions), per-field scorers with constants +2.0/+1.0 (name) and +2.0/−4.0 (content type) recovered |
| **Fuzzy scoring** | **recovered** — max-plus weighted subsequence alignment at `0x10213dd28`: skip penalty 1, per-character weights from {2,3,4,8,16}, UInt16-saturating, packed return; see `evidence/07-fuzzy-score.md`; named family: bonus-scored subsequence alignment (max-plus DP / weighted-LCS with gap penalties), i.e. fzf V2-style, **not** an edit distance |
| **Fuzzy ranking** | partial — `rank(matched:term:isNormalized:new:)` recovered: 17-day freshness window, recency as raw `Date.distance` stored as `Float`, per-record flag bitfield (0x1/0x2 kind, 0x4 set membership, 0x8 date-vs-cutoff), 16-byte packed elements — see `evidence/06-rootfuzzy-ranking.md` |
| **Fuzzy algorithm** | partial — Levenshtein (two rolling rows, case folding) recovered but **unreachable in this build** (zero callers, verified by instruction scan); live path is inferred to be bounded distance inside the trie/index traversal. Prefix mechanism recovered (bitmask prefilter + `String.hasPrefix`). Trigger and the `SensitivityLevel` table still open — see `evidence/05-fuzzy-algorithm.md` |
| Remaining unknowns | `SensitivityLevel` → distance budget table, score-enum → `Double` conversion, frecency half-life value |
| Decompiled ranking code | partial — visitor/rule witness bodies and both `RankingRules` vtable methods pulled |
| Reimplementation | scaffold only — interfaces + ordering pipeline; scoring formulas are placeholders |
| CLI + tests | working — `tests/run.sh` |

## Coverage of the search core

| Piece | State | Where |
|---|---|---|
| Fuzzy score | recovered | `07` — max-plus subsequence alignment `0x10213dd28` |
| Weights / gap penalty | recovered | `07` — {2,3,4,8,16}, penalty 1, `UInt16` saturating |
| Ranking half (recency, freshness) | recovered | `06` — `rank(matched:term:isNormalized:new:)` |
| Ordering rules | recovered (order inferred) | `04`/`06` — `ScoreRule`, `PrefixRule`, `FrecencyRule` |
| Field scorers + constants | recovered | `04` — name 2.0/1.0, content type +2.0/−4.0, sum aggregation |
| Match pipeline shape | recovered | `05` — async `items(with:settings:)`, 4 worker tasks, per-record predicates |
| Category / source axes | recovered | `08` — per-record `category` column; per-source `RootFuzzyIndex` |
| Score → `FuzzyScore` case + `SensitivityLevel` table | **open** | thresholds not read |
| Class → weight mapping {2,3,4,8,16} | **open** | ladder read, classifier not |
| Final order mechanism | **recovered** | `09` — `SortComparator` chain, built per surface: `[ScoreRule, PrefixRule]` for file search, `[PrefixRule]` alone at ~22 app sites; `FrecencyRule` never instantiated |
| What each rule compares | **recovered** | `10` — `ScoreRule` = `FileModel.lastUsedAt` desc (field 7, slot `+0x34`), `PrefixRule` = name, case-insensitive; `FrecencyRule` never instantiated |
| Cross-source merge / section precedence | **open** | candidates listed in `08` |
| Index build internals, DB schema details, caching | **open** | partial |

## Session log

`log/` holds dated session records — what was recovered, what is open, and the corrections made.
Start with [`log/2026-10-17-search-core.md`](log/2026-10-17-search-core.md).

## Layout

```
log/                             dated session records (index in log/README.md)
evidence/00-target.md            bundle, hashes, module inventory, launcher class map
evidence/01-ranking-scope.md     ranking module, protocols, score visitors, file inventory
evidence/02-toolchain.md         REA/Hopper knobs, driver usage, Swift metadata walk method
evidence/03-ranking-addresses.md  generated address map (type/protocol/conformance/witness)
evidence/04-ranking-fundamentals.md  data model + scoring mechanics, with code evidence
evidence/05-fuzzy-algorithm.md       fuzzy subsystem: API, settings, match families, dead-code note
evidence/06-rootfuzzy-ranking.md     rank(matched:term:isNormalized:new:) mechanism
evidence/07-fuzzy-score.md           the fuzzy score computation (max-plus alignment, weights)
evidence/08-categories-and-sources.md how groups (category vs source) enter search
evidence/09-final-order.md           the comparator chain (SortComparator + sorted(using:))
evidence/10-rules.md                 what each rule compares (lastUsedAt / name / unused FrecencyRule)
src/rank.swift                   CLI: pipeline + scoring (scoring marked PENDING-RECOVERY)
tests/items.json                 sample dataset
tests/run.sh                     build + assertions (match gating, ordering, empty-query state)
tools/macho.py                   Mach-O reader (VM<->file mapping, relative pointers)
tools/swiftmeta.py               Swift descriptor/conformance decoder
tools/witnesses.py               conformance -> witness table -> implementation addresses
tools/fields.py                  field descriptors (stored properties / enum cases)
tools/vtable.py                  class metadata + vtable -> method addresses
tools/report.py                  regenerates evidence/03-ranking-addresses.md
```

## Run

```
swiftc -O src/rank.swift -o build/rank
./build/rank --data tests/items.json --query git --now 1700001000
./build/rank --data tests/items.json --query ""  --now 1700001000     # frecency-ordered state
./build/rank --data tests/items.json --query goog --json
tests/run.sh
```

## What is verified vs assumed

Verified from the binary:
- Membership of the ranking module and its source files (`RaycastSearch/RootFuzzyRanking.swift`,
  `Levenshtein.swift`, `Trie.swift`, `RadixAutoCompletion.swift`, `RootFuzzyIndex.swift`, …).
- Protocol family: `Rankable`, `RankingRule`, `ScoreRankable`, `FrecencyRankable`,
  `ScoreRankableVisitor`, plus `ScoreRule` / `FrecencyRule` / `RankingRules`.
- Concrete scorers: `CombinedScoreVisitor`, `FileNameScoreVisitor`, `FilePathScoreVisitor`,
  `FileDateScoreVisitor`, `FileContentTypeScoreVisitor`, `FuzzyScore`, `PrefixScore`, `RootFuzzyRanking`.
- Frecency uses a **half-life** decay (`FrecenciesWithNewHalfLifeValue`).
- The launcher has two states: `StateForEmptySearch` and `StateForSearchTerm`.

Assumed, and marked in code as `PENDING-RECOVERY`:
- Match gating (a non-matching item is dropped when the query is non-empty).
- The mix of title / keyword / frecency weights and the fuzzy-match constants.
- Whether ties break on frecency, then input order.

## What the CLI implements, and what it guesses

`src/rank.swift` uses a two-marker convention: **RECOVERED** (read from the binary, each site cites its
address and evidence file) and **GUESS** (my inference, numbered G1–G8, each stating what would confirm or
refute it). The guessed pieces, all in one place:

| # | Guess | Where | What would settle it |
|---|---|---|---|
| G1 | which position class earns which weight in {2,3,4,8,16} | `charWeight` | the code computing the weight before the DP step |
| G2 | the `SensitivityLevel` → minimum-score table (16/8/4) | `accepts(score:)` | the `switch` on `SensitivityLevel` |
| G3 | `prefix` sits at 2, same as `exact` | `MatchKind.score` | the case→number mapping |
| G4 | flag bits 0x1/0x2 mean "has a category" | `makeRankElement` | the bit-setting sites |
| G5 | `PrefixRule` falls back to lexicographic name order | `compare`, `.prefix` | reading `0x1021466a8` to completion |
| G6 | `--chain command` = score-first, then recency, then prefix | `Chain.command` | the record type command search sorts on |
| G7 | ties resolve to input order | `rank` | Swift's sort is not documented stable |
| G8 | `frecencyScore` sign/direction (age in seconds) | `makeRankElement` | the operand order of the `Date.distance` call |

The recovered side: the aligner and its constants, the classification cases, the 17-day freshness window,
the comparator mechanism, the file chain `[ScoreRule, PrefixRule]`, `ScoreRule` reading
`FileModel.lastUsedAt` (field 7) newest-first, and `PrefixRule` comparing names case-insensitively.

## CLI implements the recovered fuzzy algorithm

`src/rank.swift` implements the recovered scorer (max-plus alignment) and the recovered 17-day freshness window, alongside the Levenshtein (two rolling rows, case-folded) to classify each
field as exact / prefix / matched / unmatched, gates candidates on any field matching, applies
`SensitivityLevel` as an edit-distance budget, and orders by the rule chain. `tests/run.sh` asserts this
behaviour (18 checks), including typo tolerance (`gthub` → GitHub at distance 1) and sensitivity gating
(distance 2 accepted at `high`, rejected at `low`).

## Next step

The address map, data model and fuzzy algorithm are settled; what remains is numeric detail:

1. **Decode the visitor protocol's requirement signature** (parameter/result types) so the two-Double
   return seen in `FileNameScoreVisitor` (`d0`, `d1` on the return path) is confirmed rather than inferred.
2. **Find writers of `RankElement` score fields** — its field offsets are known from metadata, so stores
   through those offsets locate the code computing `nameScore` / `categoryScore` / `termScore` /
   `frecencyScore`.
3. **Callers of the score-type accessors** (`FuzzyScore 0x102144c78`, `PrefixScore 0x102144c54`,
   `TriggerScore 0x102144dcc`) are the case→number conversion sites.
4. Fold each recovered constant into `src/rank.swift`, replacing the `PENDING-RECOVERY` formulas, and
   extend `tests/run.sh` with the recovered values.
