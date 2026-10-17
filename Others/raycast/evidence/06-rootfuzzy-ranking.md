# RootFuzzyRanking.rank(matched:term:isNormalized:new:) — mechanism

Recovered from `0x102153874` in the shipped arm64 image (706 lines of Hopper pseudocode, 47 851 chars),
file `RaycastSearch/RootFuzzyRanking.swift`, signpost `"search-ranking-fuzzy"`. This is the *ranking*
half of the fuzzy subsystem; the matching half is `RootFuzzyIndex.items(with:settings:)` (`0x10213a04c`).

## Signature (from the function's own trap literal + argument flow)

```swift
static func rank(matched: [Record],
                 term: String,
                 isNormalized: Set<String>,   // arg3 is used as a Swift.Set in a Hasher lookup
                 new: Bool) -> [PackedElement]
```

Argument flow read from the body: `arg0` is the iterated collection, `arg1` is the term (its count is read
and range-checked against `UInt16`), `arg2` is passed through as a boolean-ish value, `arg3` is used as the
`Set` storage in the membership test (line 176: `r20 = var_D0; Swift.Hasher.init(r20, _seed: …)`).

## What it does, in order

**1. Start signpost** `search-ranking-fuzzy` (line 92), then build a date window:

```c
Foundation.Date.init(now);
Calendar.init(identifier: .iso8601);
Calendar.date(byAdding: .day, value: -17, to: now, wrappingComponents: …)   // value 0xffffffffffffffef = -17
```

So there is a **17-day cutoff** computed with an ISO-8601 calendar and the `.day` component.

**2. Term normalisation cache.** `isNormalized` is a `Set<String>`; the body hashes the term and probes the
set — `Swift.Hasher.init` → `String.hash(into:)` → `Hasher._finalize`, then linear probing
(`r20 = r20 + 1 & mask`) with `Swift._stringCompareWithSmolCheck` for key equality, consulting a bitset
(`(bitset[i >> 6] >> i) & 1`). Terms found in the set skip normalisation.

**3. Per-record loop.** For each matched record it reads a compact record layout and derives a **flags byte**:

```c
r24 = record[0xd];                       // 1-byte kind
r21 = 0;
if (r24 != 0) { if (r24 != 1) r21 |= 0x2; r21 |= 0x1; }     // kind classification -> bits 1|2
…
r21 = (term ∈ isNormalized) ? 0x4 : 0;                       // set membership      -> bit 4
…
Foundation.Date.distance(a, to: b);
asm { fcvt s8, d0 };                                         // Double -> Float
if (s8 > 0)
    append(element);
…
if ((Date.> infix(a, b) & 1) != 0) r21 |= 0x8;               // date comparison     -> bit 8
```

**4. Packed output elements — 16 bytes each.** The append path writes:

```c
array[count] = count + 1;
*(int32_t *)(elem + 0x00) = s8;            // Float  — recency (Date.distance, seconds) 
*(int16_t *)(elem + 0x04) = v120;          // Int16
*(int16_t *)(elem + 0x06) = v130;          // Int16
*(int16_t *)(elem + 0x08) = v134;          // Int16
*(int16_t *)(elem + 0x0a) = 0;             // Int16 = 0
*(int8_t  *)(elem + 0x0c) = 3;             // byte constant 3
*(int8_t  *)(elem + 0x0d) = v128;          // byte
*(int8_t  *)(elem + 0x0e) = flags;         // byte — the bitfield above
```

Two of the `Int16` slots are produced by `csetm w8, ne` (0 / -1) patterns, i.e. boolean-in-int16 values.
The element size is 0x10, and index arithmetic traps (`brk #0x1`) when a value leaves `UInt16` range.

## Reading

* The **`Float` at offset 0 is a raw `Date.distance()` result** — an interval, not a normalised score. This
  is the `frecencyScore: Float` side of `RankElement`, and it is why frecency behaves as recency ordering
  rather than a bounded similarity value.
* The **flags byte is a predicate bitfield**, not a score: bit 0x1/0x2 from the record's kind byte, 0x4 from
  the term-set membership test, 0x8 from a date comparison against the 17-day cutoff.
* The **17-day window** is the only literal constant in the function; with the `new:` parameter and the
  date-comparison flag it reads as a "fresh item" window.
* Notably absent: any character-level string comparison beyond the set lookup. The similarity scoring
  (`nameScore` / `categoryScore` / `termScore`, the prefix/fuzzy/trigger families) is **not** computed here —
  it comes from the matching half (`items(with:settings:)`) and the file-side visitors.

## Is the date used to rank by recency? Two separate mechanisms

**Yes, but they are different code paths and should not be conflated.**

**(a) Usage recency (frecency) — `rank(matched:term:isNormalized:new:)`.**
The `Float` it writes as the first field of every element is a raw `Date.distance(a, to: b)` interval
(`fcvt s8, d0`), guarded by `s8 > 0`. It also derives a 17-day cutoff
(`Calendar.date(byAdding: .day, value: -17, to: now)`) and ORs bit `0x8` into the flags byte when a date
compares past it. `RankElement.frecencyScore: Float` is the field this lands in, and `FrecencyRule` is one
of the three ordering rules (`ScoreRule`, `PrefixRule`, `FrecencyRule`) — so this is *ordering input built
from usage history*, not a file property.

**(b) File modification date — `FileDateScoreVisitor` (`0x10212da84`).**
For file search there is a dedicated scorer whose only date-related signal is
`type metadata accessor for Foundation.Date`. It is one of the field scorers that
`CombinedScoreVisitor` sums, i.e. for a file the date contributes to the *score* alongside name, path and
content type. This is evidence that file dates affect file ranking directly.

So: a file's own date is scored by the file-date visitor; recency of *use* is scored by `rank(...)` and
ordered by `FrecencyRule`. Which concrete date feeds `rank(...)` (last use vs something else) is not yet
pinned — the function reads several record fields and the types are not recoverable from the stripped
metadata.

## Confidence

Read: the signature and argument roles, the ISO-8601 calendar with `.day` and `-17`, the `Set` probing
implementation, the `Date.distance` → `Float` conversion and its `> 0` guard, the `Date.>` comparison, the
flags byte with bits 0x1/0x2/0x4/0x8, the 16-byte element layout and its store offsets, and the UInt16
range traps.

Inferred: that bit 0x8 means "fresh" (the cutoff is 17 days, but which comparison uses which operand pair is
read from register flow, not from types), and that the `Int16` slots carry positions/lengths rather than
scores. The `new:` parameter's exact role is not yet pinned to one branch.
