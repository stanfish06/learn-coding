# The three ordering rules, in detail

Follows `09-final-order.md` (the chain mechanism). This file pins what each rule actually compares.

## The compared record: `FileModel`

`ScoreRule`/`PrefixRule`/`FrecencyRule` conform to `SortComparator` over `Rankable`; for file search the
concrete record is `FileModel`, whose 10 fields are (declaration order = memory order):

```
0 url   1 name   2 contentType   3 kind   4 size
5 createdAt   6 modifiedAt   7 lastUsedAt   8 imageAttributes   9 score
```

**Field offsets are read through the type's metadata**, so the first thing to pin is where the offset
vector starts. `FileModel`'s metadata record sits at `0x102f04e78`:

```
+0x00  rebased ptr -> 0x102f04e08     (value-witness table)
+0x08  0x00000200                     (MetadataKind::Struct)
+0x10  rebased ptr -> 0x10272c234     (FileModel type descriptor)
+0x18  ten int32 slots, zero on disk  (field offsets, filled by the runtime)
```

Slot `+0x18` is field index 0. Cross-check that fixes the base: the accessor user at `0x10212b9d8` reads
slot `+0x18` and then loads a **16-byte value** (`ldp x19, x20, [x8]`) — a `String`-shaped pair, which is
field 0 = `url`. Slot arithmetic then gives:

```
slot 0x18 -> field 0  url          slot 0x30 -> field 6  modifiedAt
slot 0x1c -> field 1  name         slot 0x34 -> field 7  lastUsedAt
slot 0x20 -> field 2  contentType  slot 0x38 -> field 8  imageAttributes
slot 0x24 -> field 3  kind         slot 0x3c -> field 9  score
slot 0x28 -> field 4  size
slot 0x2c -> field 5  createdAt
```

## `ScoreRule` — sorts by `lastUsedAt`, descending

```asm
102146e50: bl    0x10212b994          ; FileModel singleton metadata accessor
102146e54: ldrsw x8, [x0, #0x34]      ; slot 0x34 = field 7
102146e58: ldr   d8, [x23, x8]        ; lhs, 8 bytes
…        (same for the rhs into d9)
if (d9 < d8) → orderedDescending       ; later date first
```

So the primary key for file results is **`lastUsedAt` — when the file was last used** — ordered newest
first (the comparison is `if (d9 < d8) -> 1`, i.e. greater value first; the `order` property is a shared
thunk at `0x102146dac`, so no rule inverts its own direction). This is where frecency actually reaches the
order: not through `FrecencyRule`, but as the field `ScoreRule` compares.

That also matches `FileDateScoreVisitor` (`0x10212da84`), which reads the *same* slot `+0x34` — the file
scorer and the ordering rule are looking at the same date.

## `PrefixRule` — case-insensitive name comparison, as the tie-break

`0x1021466a8`: the rule pulls a `String` out of each operand through the witness table
(`ldp x25, x26, [x24, #0x18]` → `blr x8`), lowercases both sides (`String.lowercased` →
`0x10256ba18`), and compares them with `Swift._stringCompareWithSmolCheck`, with an equality/length
short-circuit (`cmp x23, x24; ccmp x19, x20, #0, eq`). It therefore breaks ties by **name, case
insensitively, prefix-shaped matches first**.

## `FrecencyRule` — present, complete, never instantiated

Its `compare` (`0x102145900`) boxes both operands (repeated stack allocations through the runtime
allocator at `0x102b8b000+0xfe8`) before comparing. It is never constructed: a whole-`__TEXT` scan for
`adrp`+`add` pairs into the witness-table block finds **0 instantiation sites** for its witness table
(`0x102cbee68`), and its type metadata is referenced only by its own accessor (`0x102146654`), which is
never called. Third instance of complete-but-unwired code in this build, after the Levenshtein function and the
unused decode table in `05`.

## Consequence: matching filters, `lastUsedAt` orders

Across all 52 users of `FileModel`'s metadata accessor, the fields read are:

```
url 6   lastUsedAt 6   name 5   size 5   kind 5   contentType 4   modifiedAt 3   createdAt 3
imageAttributes 0      score 0
```

`score` — the fuzzy match score — is **not read through the metadata** by any of them. Combined with
`rank(matched:term:isNormalized:new:)` keeping only records whose score is positive, the picture for file
search is:

* the fuzzy scorer **filters** candidates (an unalignable query yields no candidate at all),
* `ScoreRule` **orders** them by `lastUsedAt` descending,
* `PrefixRule` breaks ties by name.

So for file results the visible order is recency of use first, not match quality. Where (or whether) the
fuzzy score itself orders anything is still open — as is whether command results use a different record
type whose field 7 holds a genuine score.
