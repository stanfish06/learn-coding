#!/usr/bin/env python3
"""Dump Swift field descriptors (stored properties / enum cases) for given type descriptors.

__swift5_fieldmd is a table of 4-byte relative pointers to TargetFieldDescriptor records:

    MangledTypeName : rel32   (points at the type's mangled name string)
    Superclass      : rel32
    Kind            : uint16  (0 = struct, 1 = class, 2 = enum)
    FieldRecordSize : uint16
    NumFields       : uint32
    FieldRecord[NumFields]:
        Flags           : uint32
        MangledTypeName : rel32   (field type)
        FieldName       : rel32   (cstring)

Usage:
    python3 fields.py                 # all types in the ranking module
    python3 fields.py <substr>        # filter by type name
"""
import struct
import sys

from macho import MachO

BASE = 0x100000000
m = MachO("/Applications/Raycast.app/Contents/MacOS/Raycast")

RANKING_TYPES = {
    "SearchScore": 0x10272C51C, "PrefixScore": 0x10272C5D8, "FuzzyScore": 0x10272C5F4,
    "TriggerScore": 0x10272C610, "RootFuzzyRanking": 0x10272C62C, "RootFuzzyIndex": 0x10272C500,
    "Levenshtein": 0x10272C0BC, "Trie": 0x10272C184, "TrieNode": 0x10272C1C0,
    "TrieMatch": 0x10272C1FC, "Frecency": 0x10272C89C, "SearchMode": 0x10272C584,
    "SensitivityLevel": 0x10272C5BC, "FuzzySettings": 0x10272C840,
    "RankElement": 0x10272C650, "RankingRules": 0x10272C6F4, "ScoreRule": 0x10272C7CC,
    "PrefixRule": 0x10272C6D8, "FrecencyRule": 0x10272C6BC, "FuzzyAutoCompletion": 0x10272C008,
}


def field_descriptor_for_type(desc):
    delta = m.read_i32(desc + 16)
    if delta == 0:
        return None
    return desc + 16 + delta


def read_fields(fd):
    mangled = m.relative(fd)
    superclass_delta = m.read_i32(fd + 4)
    kind, record_size = struct.unpack_from("<HH", m.bytes_at(fd + 8, 4))
    num_fields = m.read_u32(fd + 12)
    fields = []
    pos = fd + 16
    for _ in range(num_fields):
        try:
            flags = m.read_u32(pos)
            type_name = m.cstring(pos + 4 + m.read_i32(pos + 4))
            field_name = m.cstring(pos + 8 + m.read_i32(pos + 8))
        except Exception:
            break
        fields.append((field_name, type_name, flags))
        pos += record_size
    return {"kind": kind, "record_size": record_size, "num_fields": num_fields,
            "mangled_type": mangled, "fields": fields}


KIND = {0: "struct", 1: "class", 2: "enum"}


def demangle(name):
    """Light demangling: enough to read field types such as SaySiG -> [Int]. """
    import subprocess
    try:
        out = subprocess.run(["xcrun", "swift-demangle", "-compact", "--", name],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or name
    except Exception:
        return name


def main():
    needle = sys.argv[1].lower() if len(sys.argv) > 1 else None
    for name, desc in RANKING_TYPES.items():
        if needle and needle not in name.lower():
            continue
        fd = field_descriptor_for_type(desc)
        if fd is None or m.section_of(fd) == "?":
            print(f"\n{name} (0x{desc:x}): no field descriptor")
            continue
        info = read_fields(fd)
        print(f"\n{name} (0x{desc:x})  kind={KIND.get(info['kind'], info['kind'])}  fields={info['num_fields']}")
        for fname, ftype, flags in info["fields"]:
            t = demangle(ftype) if ftype.startswith("$s") else ftype
            print(f"    {fname:28} : {t[:70]}   (flags=0x{flags:x})")


if __name__ == "__main__":
    main()
