# Categories and sources — how groups enter the search

Raycast's search shows results that belong to different groups (applications, files, extensions, snippets,
commands…). Two distinct mechanisms are involved, and only one of them is a grouping.

## 1. `category` is a per-record column, not a separate index

The search database schema says so directly — a migration named:

```
addCategoryColumnToSearchTable
addAliasHotkeyAndShortcutAddedAtColumnsToSearchTable
addAssumedViewKindColumnToCommands
```

and the record shape that the scorer consumes:

```swift
SearchScore { id: Int, name, alias, category, terms }        // 0x10272c51c
RankElement { frecencyScore: Float, recordOffset,
              nameScore, categoryScore, termScore,           // Int16 dimensions
              contentType, compactedData }                   // 0x10272c650
```

So every indexed record carries its own `category`, and scoring has a **`categoryScore` dimension** next to
`nameScore` and `termScore`. Category is therefore an input to the score and to the ordering rules, not a
separate code path per group.

## 2. `source` is the second, orthogonal axis

```
RootFuzzyIndex { source, corpus }        // 0x10272c500 — one index per source
DataSource                              // protocol, 0x10272bb4c, 1 requirement
SearchProvider                          // protocol, 0x10272ca34
```

and the signposts name the sources explicitly:

```
search-source-fs-records        search-source-fs-mdquery        search-fs-enumerate
search-index-fuzzy-records      search-index-fuzzy-build        search-index-fuzzy-items
search-update-dbrecords         search-items-starting           search-items-starting-sync
search-ranking-fuzzy            search-list-items               search-items-suggestions
```

The app-side source classes are:

```
RaycastSystemSource        RaycastCommandSource        RaycastExtensionsSource
RaycastDynamicExtensionsSource    RaycastToolSource      CloudSyncSearchSource
```

`SearchScope` (0x10272bddc) is *not* a group — its fields are `directory`, `resolvedFromSymlink`,
`isUserScope`, i.e. a filesystem search scope.

So "files" is a *source* (fs), while "applications"/"extensions"/"snippets" are largely *categories* carried
by records. Both axes exist.

## 3. What this implies for ordering

* Candidates arrive from one or more sources, each with its own `RootFuzzyIndex` (source + corpus).
* Every candidate is scored by the same machinery: the max-plus aligner (`0x10213dd28`) plus the field
  scorers, producing per-dimension scores including `categoryScore`.
* Ordering then goes through `RankingRules` (`rules: [Rule]`, with `ScoreRule`, `PrefixRule`,
  `FrecencyRule`) over the separate dimensions.

**Recovered:** the dimensions, the sources, the per-record category, and the ordering rules.
**Not yet recovered:** whether the final ordering is one global chain over the merged candidate set (with
`categoryScore` acting as a per-category bonus) or a per-category ordering with a section precedence — and
where the merge of multiple sources' result arrays happens. Candidates for that code are the `Search.swift`
pipeline (`0x1021478f8`–`0x10214b130`, 37 trap sites), `DataSourceLoader.swift` (9 sites) and
`SearchProviders.swift` (1 site).

## 4. Note on a red herring

The `cardCategory*` string family is a features taxonomy, not a search taxonomy:

```
cardCategoryAi  cardCategoryCalculator  cardCategoryClipboardhistory  cardCategoryCloudsync
cardCategoryCode  cardCategoryCommands  cardCategoryDictionary  cardCategoryEmoji
cardCategoryExtensions  cardCategoryFocus  cardCategoryHotkeys  cardCategoryMyschedule
cardCategoryQuicklinks  cardCategoryRaycast  cardCategorySnippets  cardCategoryThemes
cardCategoryTranslator  cardCategoryWindowmanagement
```

`uncategorizableApps` is likewise from an auto-quit AI prompt, unrelated to search ranking.
