#!/usr/bin/env python3
"""Resolve ranking protocol conformances to concrete implementation addresses.

Findings that drive this decoder (validated against the binary):
  * __swift5_proto holds 4-byte relative pointers to conformance descriptors.
  * A conformance descriptor is 16 bytes: Protocol(+0 rel), TypeRef(+4 rel, 0 = indirect),
    WitnessTablePattern(+8 rel), Flags(+12).
  * Witness tables in __DATA_CONST use 8-byte "chained rebase" pointers: the target is
    image_base + low 32 bits (entry[0] points back at the conformance descriptor, which is how
    this was confirmed).

Usage:
    python3 witnesses.py                 # all ranking conformances
    python3 witnesses.py <name-substr>   # filter by type or protocol name
"""
import sys

from macho import MachO

PATH = "/Applications/Raycast.app/Contents/MacOS/Raycast"
BASE = 0x100000000
m = MachO(PATH)

RANKING_PROTOCOLS = {"FrecencyRankable", "RankingRule", "Rankable", "ScoreRankable",
                     "ScoreRankableVisitor", "DataSource", "Indexable", "Searchable"}
RANKING_TYPES = {"RootFuzzyRanking", "RootFuzzyIndex", "CombinedScoreVisitor", "FileNameScoreVisitor",
                 "FileContentTypeScoreVisitor", "FileDateScoreVisitor", "FilePathScoreVisitor",
                 "RankingRules", "ScoreRule", "PrefixRule", "FrecencyRule", "Trie", "TrieNode",
                 "Search", "FileSearch", "DataSourceLoader",
                 # core score/domain types recovered from __swift5_types
                 "SearchScore", "PrefixScore", "FuzzyScore", "TriggerScore", "Frecency",
                 "SearchMode", "SensitivityLevel", "FuzzySettings", "FuzzyAutoCompletion",
                 "Levenshtein", "TrieMatch", "RankElement", "ScoredSuggestion"}


def name_at(addr):
    if addr is None or addr < BASE or m.section_of(addr) == "?":
        return None
    try:
        name = m.cstring(addr + 8 + m.read_i32(addr + 8))
        if name and len(name) < 200 and all(ord(c) >= 32 for c in name):
            return name
    except Exception:
        pass
    return None


def rebased(addr):
    """Decode an 8-byte witness-table entry into a VM address."""
    lo = m.read_u32(addr)
    return BASE + lo


protos = {}
paddr, psize = m.section_range("__swift5_protos")
for i in range(psize // 4):
    f = paddr + i * 4
    d = f + m.read_i32(f)
    protos[d] = {"name": name_at(d), "reqs": m.read_u32(d + 12) if m.section_of(d) != "?" else 0}

types = {}
taddr, tsize = m.section_range("__swift5_types")
for i in range(tsize // 4):
    f = taddr + i * 4
    d = f + m.read_i32(f)
    types[d] = name_at(d)

# protocol descriptors can also live in __DATA_CONST; index those too
for sec in ("__const",):
    pass

conf = []
saddr, ssize = m.section_range("__swift5_proto")
for i in range(ssize // 4):
    f = saddr + i * 4
    d = f + m.read_i32(f)
    if m.section_of(d) == "?":
        continue
    try:
        proto = d + m.read_i32(d)
        tdelta = m.read_i32(d + 4)
        type_ = (d + 4 + tdelta) if tdelta else None
        wdelta = m.read_i32(d + 8)
        witness = (d + 8 + wdelta) if wdelta else None
    except Exception:
        continue
    pname = protos.get(proto, {}).get("name") or name_at(proto)
    tname = types.get(type_) or name_at(type_)
    conf.append({"desc": d, "proto": proto, "pname": pname, "type": type_, "tname": tname,
                 "witness": witness, "indirect_type": tdelta == 0})


def is_ranking(c):
    return (c["pname"] in RANKING_PROTOCOLS) or (c["tname"] in RANKING_TYPES)


def main():
    needle = sys.argv[1].lower() if len(sys.argv) > 1 else None
    rows = [c for c in conf if is_ranking(c)]
    if needle:
        rows = [c for c in rows if needle in (c["tname"] or "").lower() or needle in (c["pname"] or "").lower()]
    print(f"ranking conformances: {len(rows)}  (of {len(conf)} total)")
    for c in sorted(rows, key=lambda x: (x["tname"] or "zz", x["pname"] or "zz")):
        reqs = protos.get(c["proto"], {}).get("reqs", 0)
        kind = "indirect-type" if c["indirect_type"] else "direct"
        print(f"\n{(c['tname'] or '?')[:34]:34} : {(c['pname'] or '?')[:26]:26} reqs={reqs} {kind}")
        print(f"   conformance=0x{c['desc']:x} protocol=0x{c['proto']:x} witness=0x{c['witness'] or 0:x}")
        if not c["witness"]:
            continue
        for j in range(0, max(reqs, 2) + 2):
            ef = c["witness"] + j * 8
            try:
                target = rebased(ef)
            except Exception:
                break
            sec = m.section_of(target)
            mark = "IMPLEMENTATION" if sec == "__TEXT.__text" else sec
            print(f"   entry[{j}] @0x{ef:x} -> 0x{target:x}  {mark}")


if __name__ == "__main__":
    main()
