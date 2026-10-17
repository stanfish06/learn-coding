#!/usr/bin/env python3
"""Swift metadata walker for stripped Mach-O images.

Decodes, from section tables that survive stripping:
  * type context descriptors   (__swift5_types)
  * protocol descriptors       (__swift5_protos)
  * protocol conformance records (__swift5_proto)

and resolves each conformance to its witness table, whose entries are the concrete
implementations of the protocol requirements — i.e. function addresses that the stripped
symbol table no longer names.

Usage:
    python3 swiftmeta.py protocols                 # list protocol descriptors
    python3 swiftmeta.py types [substr]            # list type descriptors
    python3 swiftmeta.py conformances [proto]      # list conformance records
    python3 swiftmeta.py witnesses <proto-substr>  # witness tables + implementation addresses
"""
import struct
import sys

from macho import MachO

TEXT_BASE = 0x100000000
SECTIONS = ["__TEXT", "__DATA_CONST", "__DATA"]


class Meta:
    def __init__(self, path):
        self.m = MachO(path)

    # --- descriptors ---------------------------------------------------------
    def context_name(self, descriptor):
        """Name of a TargetContextDescriptor."""
        name = self.m.cstring(self.m.relative(descriptor + 8))
        if not name or len(name) > 300 or any(ord(c) < 32 for c in name):
            raise ValueError(f"implausible context name at 0x{descriptor:x}: {name[:40]!r}")
        return name

    def parent_name(self, descriptor):
        parent_field = descriptor + 4
        try:
            delta = self.m.read_i32(parent_field)
            if delta == 0:
                return None
            return self.context_name(parent_field + delta)
        except Exception:
            return None

    def type_descriptor(self, descriptor):
        return {
            "address": descriptor,
            "flags": self.m.read_u32(descriptor),
            "parent": self.parent_name(descriptor),
            "name": self.context_name(descriptor),
            "access_function": self.m.relative(descriptor + 12),
            "field_descriptor": self.m.relative(descriptor + 16),
        }

    def protocol_descriptor(self, descriptor):
        flags = self.m.read_u32(descriptor)
        num_requirements = self.m.read_u32(descriptor + 12)
        return {
            "address": descriptor,
            "flags": flags,
            "parent": self.parent_name(descriptor),
            "name": self.context_name(descriptor),
            "num_requirements": num_requirements,
        }

    # --- tables --------------------------------------------------------------
    def type_descriptors(self):
        addr, size = self.m.section_range("__swift5_types")
        out = []
        for i in range(size // 4):
            field = addr + i * 4
            target = field + self.m.read_i32(field)
            if self.m.section_of(target) == "?":
                continue
            try:
                out.append(self.type_descriptor(target))
            except Exception:
                continue
        return out

    def protocol_descriptors(self):
        addr, size = self.m.section_range("__swift5_protos")
        out = []
        for i in range(size // 4):
            field = addr + i * 4
            target = field + self.m.read_i32(field)
            if self.m.section_of(target) == "?":
                continue
            out.append(self.protocol_descriptor(target))
        return out

    # --- conformances --------------------------------------------------------
    def conformances(self):
        """Decode every conformance referenced by __swift5_proto.

        The section holds 4-byte *relative pointers* to 16-byte conformance descriptors living in
        __const/__DATA_CONST (validated: resolving 4000 of them hit 3627 known type descriptors with
        Protocol@+0, versus 0 with the alternative orderings). Each descriptor is:
            +0 Protocol     rel32 -> protocol descriptor (may live in another dylib)
            +4 TypeRef      rel32 -> conforming type descriptor (0 = indirect)
            +8 WitnessTable rel32 -> witness table in __DATA_CONST
            +12 Flags       u32
        Witness-table entries are 8-byte chained-rebase pointers (target = 0x100000000 + low32).
        """
        addr, size = self.m.section_range("__swift5_proto")
        out = []
        for i in range(size // 4):
            field = addr + i * 4
            try:
                base = field + self.m.read_i32(field)
            except Exception:
                continue
            if self.m.section_of(base) == "?":
                continue
            try:
                proto_field = base
                type_field = base + 4
                witness_field = base + 8
                proto_target = proto_field + self.m.read_i32(proto_field)
                type_delta = self.m.read_i32(type_field)
                type_target = type_field + type_delta if type_delta else None
                witness_delta = self.m.read_i32(witness_field)
                witness_target = witness_field + witness_delta if witness_delta else None
                flags = self.m.read_u32(base + 12)
            except Exception:
                continue
            def name_or_none(a):
                if not a or self.m.section_of(a) == "?":
                    return None
                try:
                    return self.context_name(a)
                except Exception:
                    return None

            proto_name = name_or_none(proto_target)
            type_name = name_or_none(type_target)
            out.append({
                "address": base,
                "protocol": proto_name,
                "protocol_address": proto_target,
                "type": type_name,
                "type_address": type_target,
                "witness_table": witness_target,
                "flags": flags,
                "metadata_kind": flags & 0x7,
            })
        return out

    def witness_table(self, table_address, count, limit=64):
        """Witness table entries are relative pointers to implementations."""
        entries = []
        for i in range(min(count, limit)):
            field = table_address + i * 4
            try:
                target = field + self.m.read_i32(field)
            except Exception:
                break
            entries.append((field, target))
        return entries


def main():
    path = sys.argv[1] if sys.argv[1].startswith("/") else "/Applications/Raycast.app/Contents/MacOS/Raycast"
    argv = sys.argv[1:] if sys.argv[1].startswith("/") else sys.argv[1:]
    argv = sys.argv[2:] if sys.argv[1].startswith("/") else sys.argv[1:]
    cmd = argv[0] if argv else "protocols"
    needle = argv[1].lower() if len(argv) > 1 else None
    meta = Meta(path)

    if cmd == "protocols":
        protos = meta.protocol_descriptors()
        print(f"protocol descriptors: {len(protos)}")
        for p in protos:
            if needle and needle not in p["name"].lower():
                continue
            print(f"  0x{p['address']:x} reqs={p['num_requirements']:3} {p['name'][:100]}")
    elif cmd == "types":
        types = meta.type_descriptors()
        print(f"type descriptors: {len(types)}")
        shown = 0
        for t in types:
            if needle and needle not in t["name"].lower():
                continue
            print(f"  0x{t['address']:x} {t['name'][:110]}")
            shown += 1
            if shown > 60:
                break
    elif cmd == "conformances":
        confs = meta.conformances()
        print(f"conformance records: {len(confs)}")
        shown = 0
        for c in confs:
            if needle and needle not in (c["protocol"] or "").lower() and needle not in (c["type"] or "").lower():
                continue
            print(f"  0x{c['address']:x} kind={c['metadata_kind']} witness=0x{c['witness_table'] or 0:x} "
                  f"{(c['type'] or '?')[:60]} : {(c['protocol'] or '?')[:60]}")
            shown += 1
            if shown > 60:
                break
    elif cmd == "witnesses":
        confs = meta.conformances()
        protos = {p["address"]: p for p in meta.protocol_descriptors()}
        shown = 0
        for c in confs:
            if not c["witness_table"] or not c["protocol"]:
                continue
            if needle and needle not in c["protocol"].lower():
                continue
            proto = protos.get(c["protocol_address"])
            count = proto["num_requirements"] if proto else 8
            print(f"\n{c['type']} : {c['protocol']}  (reqs={count}) witness=0x{c['witness_table']:x}")
            for field, target in meta.witness_table(c["witness_table"], count):
                print(f"    [{field-self.m.section_of and 0:>2}] entry@0x{field:x} -> 0x{target:x} ({meta.m.section_of(target)})")
            shown += 1
            if shown > 8:
                break
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
