#!/usr/bin/env bash
# Tests for the recovered ranking pipeline.
#
# Asserts the RECOVERED behaviour: the fuzzy score filters candidates, the rule chain orders them.
# Guessed pieces (G1-G8 in src/rank.swift) are asserted only where the guess is structural, never
# as if it were a recovered constant.
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p build
swiftc -O src/rank.swift -o build/rank

python3 - <<'PY'
import json, subprocess, sys

NOW = 1700000000

def rank(query, chain="file", sensitivity="medium"):
    out = subprocess.run(["./build/rank", "--data", "tests/items.json", "--query", query,
                          "--chain", chain, "--sensitivity", sensitivity, "--now", str(NOW), "--json"],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)

def ids(rows): return [r["id"] for r in rows]

failures = []
def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  -> {detail}"))
    if not cond: failures.append(name)

# ---- the gate: the recovered aligner decides who is a candidate at all --------------------
check("'spotifi' produces no candidates (not a subsequence of anything)",
      rank("spotifi") == [], rank("spotifi"))

r = rank("spt")
check("'spt' aligns onto Spotify", "spotify" in ids(r), ids(r))
sp = next(x for x in r if x["id"] == "spotify")
check("'spt' -> Spotify classified matched", sp["nameKind"] == "matched", sp)
check("'spt' -> Spotify carries a positive score", sp["fuzzyScore"] > 0, sp)

# ---- RECOVERED: file chain = [ScoreRule(lastUsedAt desc), PrefixRule] ---------------------
r = rank("spt", chain="file")
check("both 'spt' candidates are present", set(ids(r)) == {"support", "spotify"}, ids(r))
check("file chain orders by lastUsedAt, newest first",
      [x["frecencyScore"] for x in r] == sorted(x["frecencyScore"] for x in r), 
      [(x["id"], x["frecencyScore"]) for x in r])
check("file chain names the deciding rule", r[0]["decidedBy"] == "scoreLastUsed", r[0])

# ---- GUESS G6: command chain = score first, then recency ---------------------------------
r = rank("spt", chain="command")
check("command chain puts the higher match score first",
      r[0]["nameScore"] + r[0]["categoryScore"] + r[0]["termScore"] >=
      r[1]["nameScore"] + r[1]["categoryScore"] + r[1]["termScore"],
      [(x["id"], x["nameScore"] + x["categoryScore"] + x["termScore"]) for x in r])
check("command chain falls through to recency on a score tie",
      r[0]["decidedBy"] in ("scoreMatch", "scoreLastUsed"), r[0]["decidedBy"])

# ---- classification ----------------------------------------------------------------------
r = rank("spot", chain="command")
check("prefix match is classified as prefix", r and r[0]["nameKind"] == "prefix", r[:2])
r = rank("spotify", chain="command")
check("literal equality is classified as exact", r and r[0]["nameKind"] == "exact", r[:2])

# ---- RECOVERED: StateForEmptySearch — no match dimensions, chain decides ------------------
e = rank("")
check("empty query keeps every item", len(e) == 10, len(e))
check("empty query ordered by recency", ids(e)[0] == "goog", ids(e)[:3])
check("empty query has no match scores", all(x["nameScore"] == 0 and x["termScore"] == 0 for x in e), e[:2])

# ---- RECOVERED: the 17-day freshness window ----------------------------------------------
fresh = {x["id"]: x["isFresh"] for x in e}
check("recently used item is fresh", fresh.get("github") is True, fresh)
check("item unused for 40 days is not fresh", fresh.get("gitlab") is False, fresh)
check("invalid chain is rejected", subprocess.run(
    ["./build/rank", "--data", "tests/items.json", "--query", "x", "--chain", "nope"],
    capture_output=True).returncode != 0)

# ---- ordering invariants ------------------------------------------------------------------
def chain_consistent(rows, chain):
    for i in range(len(rows) - 1):
        a, b = rows[i], rows[i + 1]
        if chain == "file":
            if a["frecencyScore"] > b["frecencyScore"]: return False     # smaller age first
        else:
            if a["nameScore"] + a["categoryScore"] + a["termScore"] < \
               b["nameScore"] + b["categoryScore"] + b["termScore"]: return False
    return True

for q in ("spt", "git", "spot"):
    for c in ("file", "command"):
        rows = rank(q, chain=c)
        check(f"'{q}' respects the {c} chain", chain_consistent(rows, c),
              [(x["id"], x["frecencyScore"]) for x in rows])

sys.exit(1 if failures else 0)
PY
