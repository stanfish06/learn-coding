# Ranking & root-search scope (static evidence)

All facts below come from the binary itself (strings/metadata) at
`/Applications/Raycast.app/Contents/MacOS/Raycast`, SHA-256 `c8ff6219…bec1e95`.

## 1. The ranking engine is a discrete module: `RaycastSearch`

The binary embeds Swift source-file paths (used by type contexts / reflection), which enumerate the module:

```
RaycastSearch/Search.swift                 query + search entry points
RaycastSearch/SearchProviders.swift        provider abstraction
RaycastSearch/SearchVisit.swift            dedup / visit tracking
RaycastSearch/DataSource.swift             data source protocol
RaycastSearch/DataSourceLoader.swift
RaycastSearch/FSDataSource.swift           filesystem-backed source
RaycastSearch/FileSearch.swift             file-specific search
RaycastSearch/FileSearchQuery.swift
RaycastSearch/RootFuzzyIndex.swift         root-search index
RaycastSearch/RootFuzzyRanking.swift       ★ ranking engine
RaycastSearch/Levenshtein.swift            edit-distance primitive
RaycastSearch/Trie.swift                   prefix index
RaycastSearch/RadixAutoCompletion.swift    autocomplete index
RaycastSearch/DatabaseAutoCompletion.swift autocomplete persistence
```

Related source paths outside the module (in scope): `RaycastApp/CommandListItem.swift`,
`RaycastApp/CommandListViewController.swift`, `RaycastApp/ActionBarViewController.swift`,
`RaycastApp/MacAppListItem.swift`.

Total distinct `.swift` paths embedded in the binary: **1209**.

## 2. Ranking protocol family (`RaycastSearch` module, mangled names)

```
$s13RaycastSearch8RankableP                 Rankable
$s13RaycastSearch11RankingRuleP             RankingRule
$s13RaycastSearch13ScoreRankableP           ScoreRankable
$s13RaycastSearch16FrecencyRankableP        FrecencyRankable
$s13RaycastSearch20ScoreRankableVisitorP    ScoreRankableVisitor   (visitor dispatch)
$s13RaycastSearch10DataSourceP              DataSource
$s13RaycastSearch0B8ProviderP               Provider
$s13RaycastSearch0B6ResultP                 Result
$s13RaycastSearch9IndexableP                Indexable
$s13RaycastSearch10SearchableP              Searchable
$s13RaycastSearch18AutoCompletionItemP      AutoCompletionItem
$s13RaycastSearch24AutoCompletionRepositoryP
$s13RaycastSearch04FileB5QueryP             File*Query
$s13RaycastSearch04File*                    file-search specifics
```

Design: items are `Rankable`; scoring is dispatched through a **visitor** (`ScoreRankableVisitor`) over
`ScoreRankable` values; recency/frequency enters through a separate `FrecencyRankable`; `RankingRule`
expresses the ordering rules.

## 3. Concrete scoring types (string table)

```
CombinedScoreVisitor          aggregates per-field scores
FileNameScoreVisitor          title/file-name field
FilePathScoreVisitor          path field
FileDateScoreVisitor          date signal
FileContentTypeScoreVisitor   content-type signal
FuzzyScore                    fuzzy-match score type
PrefixScore                   prefix-match score type
RootFuzzyRanking              root-search ranking engine
ExtensionSuggestionsRanker    command-extension suggestions
FrecencyRankable              frecency dimension
```

Rule types: `RankingRule`, `RankingRules`, `ScoreRule`, `FrecencyRule`.
Frecency model: `FrecenciesWithNewHalfLifeValue` → decay uses a **half-life** parameter.
Signals: `searchRecordFrecenciesDidReset`, `searchRecordRankingChanged`, `searchRecordRankingsDidReset`,
`itemRankingReset`, `emojiResetRanking`.
Fields observed: `frecencyScore`, `categoryScore`, `nameScore`, `directoryScores`, `alwaysRank`,
`mergeableRanks`.
Matching primitives named in the module: `FuzzyScore`, `PrefixScore`, `levenshtein`, `trigram`.
Frecency query helpers: `addEmojiRecordFrecencyDatePinned`, `updateRanking(`.

## 4. Launcher UI surface (ObjC-visible, so addressable by name)

```
0x102757d90  RaycastApp.RootSearchService                    (pure Swift — no ObjC methods)
0x102757e60  RaycastApp.RootSearchViewController             (pure Swift — no ObjC methods)
             nested: StateForSearchTerm, StateForEmptySearch,
                     ListItemsForSearchTerm, ListItemsForEmptySearch
0x10275fc70  RaycastApp.SearchBarViewController              0x1011983c0 viewDidLoad, 0x10119a7b8 viewDidAppear
0x102757f10  RaycastApp.SearchBarView                        0x100a76db8 initWithFrame:
0x10275fdd0  RaycastApp.SearchBarHistoryController
0x102754350  RaycastApp.CommandPaletteMenuListViewController
0x10005c468  RaycastApp.ActionBarViewController               viewDidLoad (anchor for the action bar)
```

`CommandListViewController`, `RootSearchService`, `RootSearchViewController` expose **zero ObjC methods**, i.e.
they are pure Swift and therefore unnamed in the stripped binary.

## 5. The open problem (why the deliverable is not finished)

The binary is stripped: `nm` shows 532 `T` symbols; Hopper names only ObjC-bridged methods and import stubs.
Verified by direct probe:

| Probe | Result |
|---|---|
| `search_procedures "$s"` | 3798 hits — 2598 `imp___stubs__` imports, 1199 `_objc_msgSend$…` stubs, **1 local def** |
| `search_procedures "Fuzzy" / "Rank" / "Frecen" / "RootSearch"` | **0 hits each** |
| `analyze_swift_types` | 3406 entries — 3405 ObjC-bridged, 0 Swift-named |
| `inspect_native_dispatch_metadata` | `swift_decls: 0`, `swift_conformances: 0`, `swift_dispatch_slots: 0` (ObjC side: 549 classes, 204 protocols) |
| Hopper loader args `-f -o` (Swift + ObjC metadata) | no change to naming |
| `trace_feature "root search ranking"` | 0 matches, 0 references |

Conclusion: **function names cannot be recovered from the stripped symbol table.** Addresses for the ranking
code must come from Swift metadata (type context descriptors → method descriptors / vtables) or from
call-graph traversal starting at the ObjC-visible launcher anchors.

Useful anchors already located:

| String | VM address | xref |
|---|---|---|
| `RootFuzzyRanking` | `0x1026a40f0` | `0x10272c62c` |
| `CombinedScoreVisitor` | `0x1026a39d0` | `0x10272c25c` |
| `frecencyScore` | `0x1029c8d70` | `0x102841eb4` |
| `RaycastSearch/RootFuzzyRanking.swift` | `0x102915150` | — |

`__TEXT` maps 1:1 at `0x100000000 + file offset`, so string → VM address is exact and reproducible with
`strings -t x`.
