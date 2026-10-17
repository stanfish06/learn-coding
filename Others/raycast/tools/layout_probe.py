from macho import MachO
m = MachO("/Applications/Raycast.app/Contents/MacOS/Raycast")

# ground truth: protocol descriptor addresses
proto_addr, proto_size = m.section_range("__swift5_protos")
known_protocols = set()
for i in range(proto_size // 4):
    f = proto_addr + i*4
    known_protocols.add(f + m.read_i32(f))

# type descriptor addresses
type_addr, type_size = m.section_range("__swift5_types")
known_types = set()
for i in range(type_size // 4):
    f = type_addr + i*4
    known_types.add(f + m.read_i32(f))

sec, size = m.section_range("__swift5_proto")
descs = set()
for i in range(size // 4):
    f = sec + i*4
    t = f + m.read_i32(f)
    if m.section_of(t) != "?":
        descs.add(t)
print("candidate conformance descriptors:", len(descs), "| known protocols:", len(known_protocols), "| known types:", len(known_types))

layouts = {
    "P,T,W,F": (0, 4, 8, 12),
    "T,W,P,F": (0, 4, 8, 12),
    "P,W,T,F": (0, 4, 8, 12),
}
for label, order in layouts.items():
    hits_proto = hits_type = 0
    for d in list(descs)[:4000]:
        def rel(off):
            try:
                delta = m.read_i32(d + off)
                return (d + off + delta) if delta else None
            except Exception:
                return None
        if label == "P,T,W,F":
            p, t = rel(0), rel(4)
        elif label == "T,W,P,F":
            t, p = rel(0), rel(8)
        else:
            p, t = rel(0), rel(8)
        if p in known_protocols: hits_proto += 1
        if t in known_types: hits_type += 1
    print(f"  layout {label}: protocol-hits={hits_proto} type-hits={hits_type}")
