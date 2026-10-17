// rank.swift — Raycast root-search ranking, rebuilt from the recovered binary.
//
// ─────────────────────────────────────────────────────────────────────────────────────────────
// MARKER CONVENTION USED THROUGHOUT THIS FILE
//   RECOVERED  — read out of the shipped binary; each site names its address and evidence file.
//   GUESS      — my inference. Not verified. Each guess states what would confirm or refute it.
//   PENDING    — a recovered mechanism whose numeric/table detail is not yet read.
// ─────────────────────────────────────────────────────────────────────────────────────────────
//
// RECOVERED pieces
//   * Fuzzy score — evidence/07: max-plus weighted subsequence alignment at 0x10213dd28.
//     Skip penalty 1, per-character weights drawn from {2,3,4,8,16}, UInt16-saturating
//     (`and w13, w13, #0xffff`), packed return (score in the low 16 bits).
//   * Match classification — evidence/05: exact / prefix / matched / unmatched. A candidate that
//     cannot be aligned at all is dropped, which is why there is no typo tolerance.
//   * Ranking half — evidence/06: recency is a raw `Date.distance` interval stored as Float, plus a
//     freshness cutoff built with `Calendar(identifier: .iso8601).date(byAdding: .day, value: -17)`.
//   * Ordering — evidence/09: `SortComparator` + `Sequence.sorted(using:)`, chain built per surface.
//     File search builds [ScoreRule, PrefixRule] — ScoreRule stored first.
//   * Rules — evidence/10: ScoreRule compares the 8-byte field at metadata slot +0x34, which for
//     FileModel's 10-field layout is field 7 = `lastUsedAt`, greater value first. PrefixRule compares
//     names case-insensitively (`String.lowercased` + `_stringCompareWithSmolCheck`). `FrecencyRule`
//     exists but is instantiated at zero sites in this build.
//
// ── GUESSES (not recovered — listed here so they are not mistaken for findings) ──────────────────
//   G1  which position class maps to which weight in {2,3,4,8,16}            (charWeight)
//   G2  the SensitivityLevel -> minimum-score table                          (accepts(score:))
//   G3  where `prefix` sits in the numeric ladder (modelled as 2, same as exact)  (MatchKind.score)
//   G4  the meaning of flag bits 0x1/0x2 (modelled as "has a category")      (makeRankElement)
//   G5  that PrefixRule falls back to lexicographic name order               (compare, .prefix)
//   G6  the `command` chain: score-first, then recency, then prefix          (Chain.command)
//   G7  ties resolve to input order (Swift's sort is not documented stable)  (rank)
//   G8  frecencyScore sign/direction (modelled as age in seconds)            (makeRankElement)
//
// Build: swiftc -O src/rank.swift -o build/rank
// Usage: build/rank --data tests/items.json --query git [--chain file|command] [--json]

import Foundation

// MARK: - Input model (mirrors RaycastSearch.IndexedElement)

struct Item: Codable {
    var id: String
    var name: String
    var alias: String?
    var category: String?
    var keywords: [String]?
    var terms: [String]?
    var lastUsedAt: Double?      // RECOVERED: `lastUsedAt` is field 7 of FileModel (evidence/10)
    var contentType: String?

    var allTerms: [String] { (keywords ?? []) + (terms ?? []) }
}

struct Dataset: Codable { var items: [Item] }

// MARK: - SensitivityLevel (evidence/05)

enum SensitivityLevel: String {
    case low, medium, high

    /// Minimum recovered alignment score accepted as a match.
    /// PENDING: the binary converts a score into a FuzzyScore case against a threshold and
    /// `SensitivityLevel` feeds that decision, but the table has not been read out.
    /// G2: these three numbers are my invention — a `switch` on SensitivityLevel in the binary would
    /// confirm or replace them.
    func accepts(score: UInt16) -> Bool {
        switch self {
        case .low: return score >= 16
        case .medium: return score >= 8
        case .high: return score >= 4
        }
    }
}

// MARK: - Recovered fuzzy scorer (evidence/07)

/// Per-character weight over the RECOVERED value set {2,3,4,8,16}.
/// RECOVERED: the values themselves (loaded as scalars and as `dup.2d` broadcast vectors), the unit
/// skip penalty, and the UInt16 saturation.
/// G1: the classifier below is a guess — which position class earns 16 vs 8 vs 4 vs 3 vs 2 is not
/// read. Confirming it needs the code that computes the weight before the DP step, or a trace of the
/// weight argument for known inputs.
func charWeight(queryIndex: Int, candidate: [Character], at j: Int) -> Int {
    let c = candidate[j]
    let prev = j > 0 ? candidate[j - 1] : nil
    if prev == nil || prev == " " || prev == "-" || prev == "." || prev == "/" { return 16 }
    if c.isUppercase && (prev?.isLowercase ?? false) { return 8 }
    if queryIndex == 0 { return 4 }
    return 2          // note: 3 from the recovered set is never produced by this guess
}

/// The recovered scorer: maximise the score of aligning `query` as a subsequence of `candidate`.
///   dp[j] = max(dp[j-1] - 1, dp_prev[j-1] + weight(candidate[j]))
/// RECOVERED: recurrence, two rolling rows, skip penalty 1, `and #0xffff` saturation, the
/// equal-length literal-compare fast path, and "needle longer than haystack" failing outright.
/// RECOVERED: the result is the maximum over positions, not the final cell.
func fuzzyScore(query: String, candidate: String) -> UInt16? {
    let q = Array(query.lowercased())
    let c = Array(candidate.lowercased())
    guard !q.isEmpty, !c.isEmpty, q.count <= c.count else { return nil }
    if q == c { return UInt16.max }

    let NEG = -1
    var prev = [Int](repeating: 0, count: c.count)
    var cur = [Int](repeating: 0, count: c.count)
    var best = 0

    for i in 0..<q.count {
        var rowBest = NEG
        for j in 0..<c.count {
            let skip = (j > 0 && cur[j - 1] > 0) ? cur[j - 1] - 1 : NEG
            var diag = NEG
            if q[i] == c[j] {
                let base = (i == 0) ? 0 : (j > 0 ? prev[j - 1] : NEG)
                if base >= 0 { diag = base + charWeight(queryIndex: i, candidate: c, at: j) }
            }
            cur[j] = max(skip, diag)
            rowBest = max(rowBest, cur[j])
        }
        if rowBest <= 0 { return nil }
        best = rowBest
        prev = cur
        cur = [Int](repeating: 0, count: c.count)
    }
    return UInt16(min(max(0, best), Int(UInt16.max)))
}

// MARK: - Match classification (mirrors PrefixScore / FuzzyScore / TriggerScore)

enum MatchKind: String {
    case exact, prefix, matched, unmatched

    /// RECOVERED: name exact = 2 and name matched = 1 (the constants seen in the file scorer).
    /// G3: where `prefix` sits is a guess — modelled as 2, i.e. as good as exact. The recovered enum
    /// `PrefixScore { unmatched, prefix, exact }` orders them, but the numbers for its cases are not read.
    var score: Int16 {
        switch self {
        case .exact: return 2
        case .prefix: return 2      // G3
        case .matched: return 1
        case .unmatched: return 0
        }
    }
    var isMatch: Bool { self != .unmatched }
}

/// RECOVERED: exact = literal equality, prefix = `hasPrefix`, otherwise the recovered scorer decides.
/// A `nil` score (unalignable) is unmatched — this is the gate that removes non-candidates.
func classify(needle: String, target: String, sensitivity: SensitivityLevel) -> MatchKind {
    let n = needle.lowercased(), t = target.lowercased()
    if n.isEmpty { return .unmatched }
    if n == t { return .exact }
    if t.hasPrefix(n) { return .prefix }
    guard let s = fuzzyScore(query: n, candidate: t) else { return .unmatched }
    return sensitivity.accepts(score: s) ? .matched : .unmatched
}

// MARK: - RankElement (mirrors RaycastSearch.RankElement)

struct RankElement {
    var item: Item
    var frecencyScore: Float      // RECOVERED: raw `Date.distance` interval stored as Float
    var nameScore: Int16
    var categoryScore: Int16
    var termScore: Int16
    var flags: UInt8              // RECOVERED: a flag bitfield exists; 0x8 tracks the date cutoff
    var fuzzyScore: UInt16
    var nameKind: MatchKind
    var termKind: MatchKind

    var isFresh: Bool { flags & 0x08 != 0 }
    var lastUsed: Double { item.lastUsedAt ?? 0 }
    var matchScore: Int { Int(nameScore) + Int(categoryScore) + Int(termScore) }
}

/// RECOVERED as a literal: `Calendar(identifier: .iso8601).date(byAdding: .day, value: -17, to: now)`.
let freshWindowDays = 17.0

func makeRankElement(item: Item, query: String, now: Double, sensitivity: SensitivityLevel) -> RankElement? {
    let trimmed = query.trimmingCharacters(in: .whitespaces)
    let lastUsed = item.lastUsedAt ?? 0
    let age = now - lastUsed

    var flags: UInt8 = 0
    if age <= freshWindowDays * 86_400 { flags |= 0x08 }   // RECOVERED: bit 0x8, date past the cutoff
    if item.category != nil { flags |= 0x01 }              // G4: bit meanings guessed

    // RECOVERED: recency is a Date.distance interval. G8: stored here as age-in-seconds; the binary's
    // exact operand order (which date is subtracted from which) is not pinned.
    let frecency = Float(max(0, age))

    if trimmed.isEmpty {
        // RECOVERED: StateForEmptySearch — no match dimensions, so the chain decides the order.
        return RankElement(item: item, frecencyScore: frecency, nameScore: 0, categoryScore: 0,
                           termScore: 0, flags: flags, fuzzyScore: 0, nameKind: .unmatched,
                           termKind: .unmatched)
    }

    let nameKind = classify(needle: trimmed, target: item.name, sensitivity: sensitivity)
    let aliasKind = item.alias.map { classify(needle: trimmed, target: $0, sensitivity: sensitivity) } ?? .unmatched
    let categoryKind = item.category.map { classify(needle: trimmed, target: $0, sensitivity: sensitivity) } ?? .unmatched
    var termKind: MatchKind = .unmatched
    for t in item.allTerms {
        let m = classify(needle: trimmed, target: t, sensitivity: sensitivity)
        if m.score > termKind.score { termKind = m }
    }

    // RECOVERED: the score gates the candidate — no alignment anywhere means no candidate at all.
    guard nameKind.isMatch || aliasKind.isMatch || categoryKind.isMatch || termKind.isMatch else { return nil }

    let raw = fuzzyScore(query: trimmed, candidate: item.name) ?? 0
    return RankElement(item: item, frecencyScore: frecency,
                       nameScore: max(nameKind.score, aliasKind.score),
                       categoryScore: categoryKind.score, termScore: termKind.score,
                       flags: flags, fuzzyScore: raw, nameKind: nameKind, termKind: termKind)
}

// MARK: - Rules (evidence/09 + 10)

enum Rule: String {
    case scoreLastUsed   // RECOVERED: ScoreRule comparing FileModel.lastUsedAt (field 7), newest first
    case scoreMatch      // G6: ScoreRule against a match-score field — the command-surface guess
    case prefix          // RECOVERED: PrefixRule, case-insensitive name comparison
    case frecency        // RECOVERED but unused: FrecencyRule has zero instantiation sites
}

enum Chain: String {
    case file, command

    /// RECOVERED for `file`: the chain built at 0x102132068 stores ScoreRule first, PrefixRule second.
    /// G6 for `command`: assumed score-first, then recency, then prefix. Confirming it needs the
    /// record type command search sorts on and the chain it constructs.
    var rules: [Rule] {
        switch self {
        case .file: return [.scoreLastUsed, .prefix]
        case .command: return [.scoreMatch, .scoreLastUsed, .prefix]
        }
    }
    var note: String {
        switch self {
        case .file: return "RECOVERED — file search builds [ScoreRule(lastUsedAt), PrefixRule]"
        case .command: return "GUESS G6 — command surfaces modelled as score-first, then recency, then prefix"
        }
    }
}

/// Applies the chain in order; returns the comparison and which rule decided it.
/// Ties that fall off the end keep input order (G7).
func compare(_ a: RankElement, _ b: RankElement, chain: Chain) -> (ComparisonResult, Rule?) {
    for rule in chain.rules {
        let r: ComparisonResult
        switch rule {
        case .scoreLastUsed:
            // RECOVERED: `if (d9 < d8) -> 1`, i.e. the larger value sorts first; all three rules share
            // one `order` thunk (0x102146dac), so none inverts its own direction.
            if a.lastUsed == b.lastUsed { continue }
            r = a.lastUsed > b.lastUsed ? .orderedAscending : .orderedDescending
        case .scoreMatch:
            let x = a.matchScore, y = b.matchScore
            if x == y { continue }
            r = x > y ? .orderedAscending : .orderedDescending
        case .prefix:
            let ap = a.nameKind == .prefix || a.nameKind == .exact
            let bp = b.nameKind == .prefix || b.nameKind == .exact
            if ap != bp { r = ap ? .orderedAscending : .orderedDescending }
            else if a.item.name.lowercased() != b.item.name.lowercased() {
                // G5: the binary compares the lowercased names; whether the comparison is
                // lexicographic or prefix-only is the guessed part.
                r = a.item.name.lowercased() < b.item.name.lowercased() ? .orderedAscending : .orderedDescending
            } else { continue }
        case .frecency:
            if a.frecencyScore == b.frecencyScore { continue }
            r = a.frecencyScore < b.frecencyScore ? .orderedAscending : .orderedDescending
        }
        return (r, rule)
    }
    return (.orderedSame, nil)
}

struct Ranking {
    var elements: [RankElement]
    /// rule that decided each adjacent pair (index i is the rule between elements i and i+1)
    var decisions: [Rule?]
}

func rank(items: [Item], query: String, now: Double, sensitivity: SensitivityLevel, chain: Chain) -> Ranking {
    let candidates = items.compactMap { makeRankElement(item: $0, query: query, now: now, sensitivity: sensitivity) }
    let sorted = candidates.enumerated().sorted { lhs, rhs in
        let (r, _) = compare(lhs.element, rhs.element, chain: chain)
        if r == .orderedSame { return lhs.offset < rhs.offset }   // G7: input order as the tie-break
        return r == .orderedAscending
    }.map { $0.element }

    var decisions: [Rule?] = []
    for i in 0..<max(0, sorted.count - 1) {
        decisions.append(compare(sorted[i], sorted[i + 1], chain: chain).1)
    }
    return Ranking(elements: sorted, decisions: decisions)
}

// MARK: - CLI

func fail(_ message: String) -> Never {
    FileHandle.standardError.write((message + "\n").data(using: .utf8)!)
    exit(1)
}
func number(_ raw: String?, _ label: String) -> Double {
    guard let raw, let v = Double(raw) else { fail("bad \(label): \(raw ?? "missing")") }
    return v
}

var args = Array(CommandLine.arguments.dropFirst())
var dataPath: String?, query: String?
var now = Date().timeIntervalSince1970
var jsonOut = false
var sensitivity = SensitivityLevel.medium
var chain = Chain.file

while let arg = args.first {
    args.removeFirst()
    switch arg {
    case "--data": dataPath = args.first; args.removeFirst()
    case "--query": query = args.first; args.removeFirst()
    case "--now": now = number(args.first, "--now"); args.removeFirst()
    case "--sensitivity":
        guard let raw = args.first, let l = SensitivityLevel(rawValue: raw) else { fail("bad --sensitivity") }
        sensitivity = l; args.removeFirst()
    case "--chain":
        guard let raw = args.first, let c = Chain(rawValue: raw) else { fail("bad --chain (file|command)") }
        chain = c; args.removeFirst()
    case "--json": jsonOut = true
    default: fail("unknown argument: \(arg)")
    }
}

guard let dataPath, let query else { fail("usage: rank --data items.json --query TEXT [--chain file|command] [--sensitivity low|medium|high] [--now EPOCH] [--json]") }
guard let data = FileManager.default.contents(atPath: dataPath) else { fail("cannot read \(dataPath)") }
let dataset: Dataset
do { dataset = try JSONDecoder().decode(Dataset.self, from: data) } catch { fail("cannot decode: \(error)") }

let ranking = rank(items: dataset.items, query: query, now: now, sensitivity: sensitivity, chain: chain)

if jsonOut {
    let payload: [[String: Any]] = ranking.elements.enumerated().map { (i, e) in
        ["id": e.item.id, "name": e.item.name,
         "nameScore": Int(e.nameScore), "categoryScore": Int(e.categoryScore), "termScore": Int(e.termScore),
         "nameKind": e.nameKind.rawValue, "termKind": e.termKind.rawValue,
         "fuzzyScore": Int(e.fuzzyScore),
         "frecencyScore": Double(e.frecencyScore), "isFresh": e.isFresh, "flags": Int(e.flags),
         "order": i + 1,
         "decidedBy": i < ranking.decisions.count ? (ranking.decisions[i]?.rawValue ?? "tie") : "last"]
    }
    let out = try! JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys])
    print(String(data: out, encoding: .utf8)!)
} else {
    print("# chain=\(chain.rawValue)  \(chain.note)")
    print("# the fuzzy score filters candidates; the chain orders them. GUESSES: G1–G8, see src/rank.swift")
    for (i, e) in ranking.elements.enumerated() {
        let name = e.item.name
        let pad = String(repeating: " ", count: max(0, 24 - name.count))
        print(String(format: "%2d. %@%@ name=%-9@ term=%-9@ score=%-4d used=%5.1fh fresh=%-3@",
                     i + 1, name, pad,
                     "\(e.nameKind.rawValue)" as NSString, "\(e.termKind.rawValue)" as NSString,
                     Int(e.fuzzyScore), (now - e.lastUsed) / 3600.0, e.isFresh ? "yes" : "no" as NSString))
        if i < ranking.decisions.count {
            print("      └─ next ordered by: \(ranking.decisions[i]?.rawValue ?? "input order (tie)")")
        }
    }
}
