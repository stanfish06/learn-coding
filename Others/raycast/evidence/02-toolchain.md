# Analysis toolchain: what works, and the knobs that matter

Everything here was measured on this machine against Raycast.app (52 MB, arm64-only, stripped).

## REA + Hopper

- REA is `rea-agents@6.5.0`, normally launched by pi as `npx -y rea-agents@6.5.0 mcp`
  with `HOPPER_LAUNCHER_PATH=/Users/stan/Applications/Hopper Disassembler.app/Contents/MacOS/hopper`.
- Hopper is a **singleton GUI app**. REA leases it per session (`/tmp/rea-*/ownership.json` holds
  `run_id`/`pid`) and sets `REA_OWNS_PROCESS_LIFETIME=False`, so an abandoned analysis keeps running
  (observed: 100 % CPU, up to 5 GB RSS, indefinitely).
- REA injects a Python bootstrap into Hopper (`/tmp/rea-*/bootstrap.py` → `bridge/hopper_bridge.py`,
  socket in `/tmp/rea-hopper-501/`). **The bootstrap only runs after Hopper's initial analysis ends**, so
  REA's startup deadline is the binding constraint on large binaries — not the MCP timeout.

### Timeouts (both are real, both must be raised for a 52 MB target)

| Knob | Where | Default | Used here |
|---|---|---|---|
| per-call MCP timeout | pi `~/.pi/agent/mcp.json` → `mcpServers.rea.timeout` (seconds) | 60 s | `1800` (needs `/reload`) |
| Hopper launch/analysis/bridge/readiness deadline | env `REA_HOPPER_STARTUP_TIMEOUT_MS` | `120000` ms | `3600000` ms |

Measured cost of one full Hopper analysis of Raycast: **~12 min** (100 % CPU, ~4–5 GB RSS).
`open_binary` itself returns in ~0.5 s; the analysis is what blocks the next call.

### Loader args override

REA passes its own loader args (`-l Mach-O --aarch64`). They can be replaced wholesale with:

```
HOPPER_LOADER_ARGS_JSON='["-l","Mach-O","--aarch64","-f","-o"]'
```

(`-f` = read Swift metadata, `-o` = read Objective-C metadata). Verified accepted; **it does not make
Hopper name pure-Swift functions** for this stripped binary, so it is not a fix — recorded so nobody
retries it.

## Driving REA directly (bypasses the MCP timeout entirely)

`/tmp/rea-raycast/driver.js` keeps one REA session alive, opens the target once, then executes queued
tool calls with no per-call deadline:

```
queue/<n>-<id>.json    {"id":"...","tool":"search_procedures","args":{...}}
results/<id>.json      {tool, args, ms, isError, payload}
status.json            {state, current|last, done, failed}
touch STOP             stops the driver
```

Launch:

```
REA_HOPPER_STARTUP_TIMEOUT_MS=3600000 node /tmp/rea-raycast/driver.js
```

Keeping the driver alive matters: a new session re-opens the target and pays the full ~12 min analysis again.

## Swift metadata walk (how the ranking addresses were recovered)

Host-side Python in `tools/`, no decompiler needed for this part:

| Tool | Job |
|---|---|
| `macho.py` | Mach-O reader: VM↔file-offset mapping, relative-pointer resolution, string reads |
| `swiftmeta.py` | decodes `__swift5_types`, `__swift5_protos`, `__swift5_proto` |
| `witnesses.py` | resolves conformances → witness tables → implementation addresses |
| `report.py` | regenerates `evidence/03-ranking-addresses.md` |

Facts established by measurement, which the decoder depends on:

1. `__swift5_types` / `__swift5_protos` hold **4-byte relative pointers to context descriptors** which sit
   in `__TEXT.__constg_swiftt`. Descriptor layout: `Flags(0), Parent(4), Name(8), AccessFn(12), Fields(16)`.
   Names decode as plain strings (`RootFuzzyRanking`), not mangled `$s…` names.
2. `__swift5_proto` holds **4-byte relative pointers to conformance descriptors** (not inline records).
   A conformance descriptor is 16 bytes: `Protocol(0 rel), TypeRef(4 rel, 0 = indirect), WitnessTable(8 rel), Flags(12)`.
   Layout was confirmed empirically: with `Protocol@0` the conforming-type resolution hit 3627/4000 known type
   descriptors, versus 0 for the alternative orderings.
3. **Witness tables use 8-byte chained-rebase pointers**: `target = 0x100000000 + low32`. Entry 0 points back
   at the conformance descriptor — that self-reference is what proves the decoding rather than assuming it.
4. Static call edges are absent for protocol dispatch, so the pipeline is located by `xrefs` on the
   witness-table addresses, not by `procedure_callers`.

Sections used (file offsets are `vm - 0x100000000` inside `__TEXT`):

```
__swift5_types   0x102852ab8 size 0x6ee4    7097 type descriptors
__swift5_protos  0x102852364 size 0x754      469 protocol descriptors
__swift5_proto   0x10273e37c size 0xeca0   15144 conformance pointers
```

## Driver usage

```bash
REA_HOPPER_STARTUP_TIMEOUT_MS=3600000 node /tmp/rea-raycast/driver.js   # opens Raycast, keeps one session
cat /tmp/rea-raycast/status.json                                        # state, done, failed
touch /tmp/rea-raycast/STOP && pkill -f 'Hopper Disassembler'           # shut down, frees ~5 GB
```

`strings -t x` gives file offsets; `__TEXT` has `vmaddr=0x100000000, fileoff=0`, so
`vm = 0x100000000 + offset` is exact. `__DATA_CONST` is `vmaddr=0x102b84000, fileoff=45629440`,
`__DATA` is `vmaddr=0x102cfc000, fileoff=47169536`.

Available: `otool`, llvm `objdump`, `nm`, `lipo`, `swiftc`/`swift-demangle` (Swift 6.2.4), Python 3.
Absent: rizin/radare2, gdb, Ghidra, jadx, tshark, adb — so Hopper is the only decompiler.

## Failure modes seen (and their cause)

| Symptom | Cause | Fix |
|---|---|---|
| `provider_timeout … waiting for Hopper bridge readiness` | 120 s default deadline vs ~12 min analysis | raise `REA_HOPPER_STARTUP_TIMEOUT_MS` |
| `provider_unavailable … already open in REA session <id>` | a previous REA session still holds the Hopper lease | kill stale `rea mcp` processes and Hopper |
| `cleanup_incomplete` after a timeout | REA gives up, Hopper keeps running | `pkill -f 'Hopper Disassembler'` |
| `resource_constraint` on `list_procedures` | 180 840 procedures exceed the MCP stdio budget | use `export_evidence_bundle` instead |
| leftover `npx` REA servers | killing the parent `npx` leaves the child server alive | spawn detached and `kill(-pid)` |
