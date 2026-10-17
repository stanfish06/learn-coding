#!/usr/bin/env python3
"""Parse the dyld exports trie of a Mach-O image into (name, address) pairs.

The trie stores names as shared-prefix-compressed edges and each terminal node carries a
self-relative address, so this yields an exact symbol map even when the classic symbol table
has been stripped.

Usage:
    python3 exports.py /path/to/binary [substring ...]
"""
import struct
import sys

from macho import MachO

LC_DYLD_EXPORTS_TRIE = 0x80000033
LC_DYLD_INFO = 0x22
LC_DYLD_INFO_ONLY = 0x80000022

EXPORT_SYMBOL_FLAGS_REEXPORT = 0x08
EXPORT_SYMBOL_FLAGS_STUB_AND_RESOLVER = 0x10


def uleb(data, off):
    """Decode an unsigned LEB128 value; returns (value, next_offset)."""
    result = 0
    shift = 0
    while True:
        byte = data[off]
        off += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, off
        shift += 7


def find_exports_blob(m):
    """Return (file_offset, size) of the exports trie."""
    off = 32
    for _ in range(m.ncmds):
        cmd, cmdsize = struct.unpack_from("<II", m.data, off)
        if cmd in (LC_DYLD_EXPORTS_TRIE, LC_DYLD_INFO, LC_DYLD_INFO_ONLY):
            if cmd == LC_DYLD_EXPORTS_TRIE:
                doff, dsize = struct.unpack_from("<II", m.data, off + 8)
                return doff, dsize
            # LC_DYLD_INFO(_ONLY): export_off, export_size are the last two pairs
            vals = struct.unpack_from("<IIIIIIIIII", m.data, off + 8)
            return vals[8], vals[9]
        off += cmdsize
    raise KeyError("no exports trie in this image")


def parse_exports(m, blob_off, blob_size, image_base=None):
    """Yield (name, address, flags) for every terminal in the dyld exports trie.

    The trie starts at offset 0 (no node-count header); each node is
    terminalSize(uleb) [terminalData] childrenCount(byte) { edge(cstring) childOffset(uleb) }*.
    """
    if image_base is None:
        image_base = m.segments[1][1]  # __TEXT vmaddr
    data = m.data
    end = blob_off + blob_size
    results = []
    seen = set()

    def walk(node_offset, prefix):
        if node_offset in seen:
            return
        seen.add(node_offset)
        p = blob_off + node_offset
        if p >= end:
            return
        terminal_size, q = uleb(data, p)
        if terminal_size:
            tstart = q
            flags, r = uleb(data, tstart)
            address = None
            if flags & EXPORT_SYMBOL_FLAGS_REEXPORT:
                ordinal, r = uleb(data, r)
                name_end = data.index(b"\0", r)
                r = name_end + 1
            elif flags & EXPORT_SYMBOL_FLAGS_STUB_AND_RESOLVER:
                stub, r = uleb(data, r)
                resolver, r = uleb(data, r)
                address = image_base + stub
            else:
                offset, r = uleb(data, r)
                address = image_base + offset
            results.append((prefix, address, flags))
            q = tstart + terminal_size
        children_count = data[q]
        q += 1
        for _ in range(children_count):
            name_end = data.index(b"\0", q)
            edge = data[q:name_end].decode("utf-8", "replace")
            q = name_end + 1
            child, q = uleb(data, q)
            walk(child, prefix + edge)

    walk(0, "")
    return results


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "/Applications/Raycast.app/Contents/MacOS/Raycast"
    needles = [s.lower() for s in sys.argv[2:]]
    m = MachO(path)
    blob_off, blob_size = find_exports_blob(m)
    print(f"exports trie: file 0x{blob_off:x} size {blob_size}")
    entries = parse_exports(m, blob_off, blob_size)
    with_addr = [e for e in entries if e[1]]
    print(f"terminals: {len(entries)}  with address: {len(with_addr)}")
    for name, addr, flags in entries[:5]:
        print(f"   0x{addr or 0:x} flags={flags} {name[:110]}")
    if needles:
        print(f"\n--- matches for {needles} ---")
        for name, addr, flags in entries:
            low = name.lower()
            if any(n in low for n in needles):
                print(f"   0x{addr or 0:x} {name[:140]}")


if __name__ == "__main__":
    main()
