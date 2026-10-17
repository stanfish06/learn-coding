#!/usr/bin/env python3
"""Minimal Mach-O reader for the Raycast metadata walk.

Provides VM<->file-offset mapping, relative-pointer resolution and string reads.
Only what the Swift metadata parser needs; no dependencies.
"""
import struct

MAGIC_64 = 0xFEEDFACF
LC_SEGMENT_64 = 0x19


class MachO:
    def __init__(self, path):
        self.path = path
        self.data = open(path, "rb").read()
        magic = struct.unpack_from("<I", self.data, 0)[0]
        if magic != MAGIC_64:
            raise ValueError(f"not a thin little-endian 64-bit Mach-O: magic=0x{magic:08x}")
        self.ncmds = struct.unpack_from("<I", self.data, 16)[0]
        self.segments = []      # (name, vmaddr, vmsize, fileoff, filesize)
        self.sections = []      # (seg, name, addr, size, offset)
        off = 32
        for _ in range(self.ncmds):
            cmd, cmdsize = struct.unpack_from("<II", self.data, off)
            if cmd == LC_SEGMENT_64:
                segname = self.data[off + 8:off + 24].rstrip(b"\0").decode()
                vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<QQQQ", self.data, off + 24)
                nsects = struct.unpack_from("<I", self.data, off + 64)[0]
                self.segments.append((segname, vmaddr, vmsize, fileoff, filesize))
                soff = off + 72
                for _ in range(nsects):
                    sname = self.data[soff:soff + 16].rstrip(b"\0").decode()
                    saddr, ssize = struct.unpack_from("<QQ", self.data, soff + 32)
                    sfoff = struct.unpack_from("<I", self.data, soff + 48)[0]
                    self.sections.append((segname, sname, saddr, ssize, sfoff))
                    soff += 80
            off += cmdsize

    # --- address translation -------------------------------------------------
    def file_offset(self, vm):
        for name, vmaddr, vmsize, fileoff, filesize in self.segments:
            if vmaddr <= vm < vmaddr + vmsize:
                delta = vm - vmaddr
                if delta < filesize:
                    return fileoff + delta
                raise ValueError(f"address 0x{vm:x} is in {name} beyond its file data (bss)")
        raise ValueError(f"address 0x{vm:x} not in any segment")

    def section_of(self, vm):
        for seg, name, addr, size, _ in self.sections:
            if addr <= vm < addr + size:
                return f"{seg}.{name}"
        return "?"

    def bytes_at(self, vm, length):
        return self.data[self.file_offset(vm):self.file_offset(vm) + length]

    # --- primitives ----------------------------------------------------------
    def read_i32(self, vm):
        return struct.unpack("<i", self.bytes_at(vm, 4))[0]

    def read_u32(self, vm):
        return struct.unpack("<I", self.bytes_at(vm, 4))[0]

    def read_u64(self, vm):
        return struct.unpack("<Q", self.bytes_at(vm, 8))[0]

    def relative(self, vm, kind="direct"):
        """Swift relative pointer: value at `vm` is a signed 32-bit delta.

        kind='direct'      -> target = vm + delta
        kind='indirect'    -> target = vm + delta, then read a 64-bit pointer there
        kind='context'     -> same as direct but the target is a context descriptor
        """
        delta = self.read_i32(vm)
        target = vm + delta
        if kind == "indirect":
            return self.read_u64(target)
        return target

    def cstring(self, vm, limit=512):
        out = bytearray()
        off = self.file_offset(vm)
        while len(out) < limit:
            b = self.data[off + len(out)]
            if b == 0:
                break
            out.append(b)
        return out.decode("utf-8", "replace")

    def find_bytes(self, needle):
        """All VM addresses where `needle` appears in file-backed data."""
        hits = []
        start = 0
        while True:
            idx = self.data.find(needle, start)
            if idx < 0:
                break
            for name, vmaddr, vmsize, fileoff, filesize in self.segments:
                if fileoff <= idx < fileoff + filesize:
                    hits.append(vmaddr + (idx - fileoff))
                    break
            start = idx + 1
        return hits

    def section_range(self, section_name):
        for seg, name, addr, size, _ in self.sections:
            if name == section_name:
                return addr, size
        raise KeyError(section_name)


if __name__ == "__main__":
    m = MachO("/Applications/Raycast.app/Contents/MacOS/Raycast")
    print(f"segments: {len(m.segments)}  sections: {len(m.sections)}")
    for seg, name, addr, size, _ in m.sections:
        if "swift" in name or name == "__const":
            print(f"  {seg}.{name:16} 0x{addr:x} size=0x{size:x}  ({m.section_of(addr)})")
