# Target: Raycast.app launcher — scope and static inventory

## Subject

| Field | Value |
|---|---|
| Bundle | `/Applications/Raycast.app` |
| Main binary | `Contents/MacOS/Raycast` |
| SHA-256 | `c8ff6219fa4122ca35c646fa23638a219c69abcc6d2db81bf6931a92cbec1e95` |
| Size | 52,710,128 bytes |
| Format | Mach-O, arm64 only (no fat slice, so no slicing shortcut) |
| Symbols | 7019 total, 532 `T` — heavily stripped |

## Bundle layout (launcher-relevant)

```
Contents/MacOS/Raycast                  52,710,128 B   main app (launcher UI + core)
Contents/Helpers/server                  9,373,600 B   Rust + V8 extension host — OUT OF SCOPE
Contents/Frameworks/SoulverCore.framework              calculator engine — OUT OF SCOPE
Contents/Frameworks/SplineRuntime.framework            3D runtime — OUT OF SCOPE
Contents/Extensions/RaycastAppIntents.appex            App Intents — OUT OF SCOPE
Contents/Library/LoginItems/RaycastLauncher.app        login item shim — OUT OF SCOPE
```

Scope per user: **root search pipeline + ranking, launcher backend core**. Excluded: extensions (incl. the
Rust `server` host and its RPC layer), clipboard, color picker, dictation, snippets, window management,
calendar, notes, emoji, store, cloud sync, onboarding, AI extensions.

## Swift modules in the main binary (metadata occurrence counts)

| Module | ObjC-visible classes | Role |
|---|---|---|
| `RaycastApp` | 1772 (1302 + 470 private) | launcher core (UI + services) |
| `RaycastUI` | 504 | shared UI |
| `RaycastData` | 84 | data layer (`SearchEntity`, `SearchStorageReader/Writer`) |
| `RaycastSearch` | 28 | **ranking protocol family** |
| `RaycastKit` | 18 | kit |
| `RaycastRPC` | 16 | RPC boundary — ignored per scope |
| third-party | — | GRDB, Sentry, Starscream, Nuke, PostHog, Yams, MathJaxSwift, SWXMLHash |

## Launcher entry points (ObjC-visible Swift classes, addresses in the arm64 image)

```
0x102757d90  _TtC10RaycastApp17RootSearchService
0x102757e60  _TtC10RaycastApp24RootSearchViewController
             ├─ nested: StateForSearchTerm, StateForEmptySearch,
             │           ListItemsForSearchTerm, ListItemsForEmptySearch
0x102757d30  _TtC10RaycastApp...41RootSearchExportableConfigurationProvider
0x102757f10  _TtC10RaycastAppP33_EDCC...13SearchBarView
0x10275fc70  _TtC10RaycastApp23SearchBarViewController
0x10275fca0  _TtC10RaycastApp26SearchBarArgumentInputView
0x10275fcd0  _TtC10RaycastApp30SearchBarArgumentTextInputView
0x10275fd10  _TtC10RaycastApp35SearchBarArgumentPlainTextInputView
0x10275fd50  _TtC10RaycastApp36SearchBarArgumentSecureTextInputView
0x10275fd90  _TtC10RaycastApp34SearchBarArgumentDropdownInputView
0x10275fdd0  _TtC10RaycastApp...26SearchBarHistoryController
0x102754350  _TtC10RaycastApp36CommandPaletteMenuListViewController
0x102754990  _TtC10RaycastApp27AICommandRootSearchListItem
```

`RootSearchService` and `RootSearchViewController` expose **no ObjC methods** (`baseMethods` is null), i.e.
they are pure Swift — their methods exist only in Swift metadata. This is why the analysis must use a
Swift-metadata-aware analyzer (Hopper) rather than ObjC-only dumps.

## Analysis toolchain and its constraints (measured)

- REA (rea-agents 6.5.0) drives Hopper Disassembler 4 headlessly.
- REA's MCP tools have a **60 s** per-call cap in pi (`mcp.json`), raisable via `"timeout": 1800`.
- REA has an **internal** Hopper launch/analysis/bridge/readiness deadline, default **120 s**, settable via
  the env var **`REA_HOPPER_STARTUP_TIMEOUT_MS`**. On this 52 MB binary the 120 s default always expires
  before Hopper's initial analysis ends, so REA reports `provider_timeout` / `cleanup_incomplete` unless the
  env var is raised. Analysis is driven with `REA_HOPPER_STARTUP_TIMEOUT_MS=1800000`.
- Hopper is a singleton: it is leased per REA session (`/tmp/rea-*/ownership.json`, run_id + pid), and
  `REA_OWNS_PROCESS_LIFETIME=False`, so an abandoned analysis keeps running (measured: 100 % CPU, 3–4 GB RSS).
- REA defers its Python bridge bootstrap until Hopper's initial analysis ends; that is the reason the
  readiness deadline is the binding constraint.
- Observed cost: Hopper analysis of a 10 MB Swift app ≈ 40 s; 19 MB > 60 s; 52 MB ≫ 120 s (minutes).

## Host tooling available

`otool`, `objdump` (llvm), `swiftc`/`swift-demangle` (Swift 6.2.4), `nm`, `lipo`.
Absent: rizin/radare2, gdb, Ghidra, jadx, apktool, tshark, adb.
Hopper Disassembler 4 at `/Users/stan/Applications/Hopper Disassembler.app` (CLI `hopper` v1.6.0; the CLI
does not work standalone — it needs REA's injected bootstrap).
