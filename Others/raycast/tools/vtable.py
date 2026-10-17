#!/usr/bin/env python3
"""Read Swift class vtables from class metadata.

For a Swift class, the metadata record's `Data` field points at the class descriptor.
Finding that pointer gives the metadata address; the vtable follows the class-specific
fields, and its entries are the method implementations.
"""
import struct
from macho import MachO

BASE = 0x100000000
m = MachO("/Applications/Raycast.app/Contents/MacOS/Raycast")

CLASS_DESCRIPTORS = {
    "FuzzyAutoCompletion": 0x10272C008,
    "RankingRules": 0x10272C6F4,
    "Trie": 0x10272C184,
    "TrieNode": 0x10272C1C0,
    "CombinedScoreVisitor": 0x10272C25C,
    "FileNameScoreVisitor": 0x10272C298,
    "FileContentTypeScoreVisitor": 0x10272C2D4,
    "FileDateScoreVisitor": 0x10272C310,
    "FilePathScoreVisitor": 0x10272C34C,
    "Search": 0x0,
}


def find_descriptor_ref(desc):
    """Locate chained-rebase references to the descriptor (low 32 bits of the target)."""
    needle = struct.pack("<I", desc - BASE)
    hits = []
    start = 0
    while True:
        i = m.data.find(needle, start)
        if i < 0:
            break
        for name, vmaddr, vmsize, fileoff, filesize in m.segments:
            if fileoff <= i < fileoff + filesize:
                hits.append(vmaddr + (i - fileoff))
                break
        start = i + 1
    return hits


def class_metadata(desc):
    """Prefer the runtime metadata record in __DATA; __DATA_CONST may hold a lazy pattern."""
    candidates = []
    for hit in find_descriptor_ref(desc):
        meta = hit - 0x28
        if meta < BASE:
            continue
        try:
            if m.read_u32(meta + 0x28) != (desc - BASE):
                continue
        except Exception:
            continue
        candidates.append(meta)
    if not candidates:
        return None
    candidates.sort(key=lambda a: (0 if m.section_of(a).startswith("__DATA.") else 1, a))
    return candidates[0]


def vtable(meta, count=24):
    """Vtable entries are 8-byte chained-rebase pointers starting at metadata + 0x38."""
    entries = []
    base = meta + 0x38
    for i in range(count):
        field = base + i * 8
        try:
            lo = m.read_u32(field)
        except Exception:
            break
        if lo == 0:
            continue
        target = BASE + lo
        entries.append((field, target, m.section_of(target)))
    return entries


if __name__ == "__main__":
    for name, desc in CLASS_DESCRIPTORS.items():
        if not desc:
            continue
        meta = class_metadata(desc)
        if not meta:
            print(f"{name}: class metadata not found")
            continue
        entries = vtable(meta)
        code = [(f, t) for f, t, sec in entries if sec == "__TEXT.__text"]
        print(f"\n{name}: descriptor=0x{desc:x} metadata=0x{meta:x} vtable entries={len(entries)} code={len(code)}")
        for f, t in code[:14]:
            print(f"    vtable@0x{f:x} -> 0x{t:x}")
