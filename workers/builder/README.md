# builder\_synth\_v1

**Version:** 1.0.0  
**Profile:** `linux-x86_64-elf-gcc-c`  
**Scope contract:** See [LOCK.md](LOCK.md)

## Purpose

Compiles synthetic C source files into ELF binaries across a controlled build matrix, emitting a typed `build_receipt.json` as the single authoritative provenance record per job. Designed for academic benchmarking of reverse-engineering tasks (function boundary detection, decompiler evaluation, LLM-assisted analysis).

## Build Matrix

| Axis         | Values                           |
|--------------|----------------------------------|
| Optimization | O0, O1, O2, O3                   |
| Variant      | debug (`-g`), release, stripped   |
| **Cells**    | **4 × 3 = 12 per job**           |

Each cell goes through three phases:

1. **Compile** — `gcc -c` per `.c` file → `.o` objects
2. **Link** — `gcc *.o` → single ELF executable
3. **Strip** — `strip` on the linked binary (stripped variant only)

## Toolchain (locked)

| Tool     | Version  | Source               |
|----------|----------|----------------------|
| GCC      | 12.2.0   | Debian Bookworm apt  |
| binutils | system   | Debian Bookworm apt  |
| strip    | system   | (from binutils)      |

Base cflags: `-std=c11 -Wno-error -fno-omit-frame-pointer -mno-omit-leaf-frame-pointer`

Link-flag allowlist: `["-lm"]`

## Artifact Layout

```
/files/synthetic/{name}/
├── src/                          # frozen source snapshot
│   ├── *.c
│   └── *.h
├── build_receipt.json            # THE receipt
├── O0/
│   ├── debug/
│   │   ├── obj/    (*.o)
│   │   ├── bin/    (ELF)
│   │   └── logs/   (compile.log, link.log)
│   ├── release/
│   │   ├── obj/ bin/ logs/
│   └── stripped/
│       ├── obj/ bin/ logs/ strip.log
├── O1/ ...
├── O2/ ...
└── O3/ ...
```

## BuildReceipt Schema

Defined in `receipt.py`. Key models:

- **BuildReceipt** — top-level envelope
- **SourceIdentity** — file list, snapshot SHA-256, entry type
- **ToolchainIdentity** — gcc/binutils/strip versions, OS, kernel, arch
- **ProfileV1** — base cflags, variant deltas, link libs
- **BuildCell** — per optimization×variant result
- **CompilePhase / LinkPhase / StripPhase** — command, status, duration
- **ArtifactMeta** — path, SHA-256, size, ELF metadata, debug presence
- **BuildFlag** — 9 flags (BUILD_FAILED, TIMEOUT, NO_ARTIFACT, etc.)

## Architecture

```
┌─────────────┐        ┌──────────────┐       ┌────────────┐
│  API router  │──push──│  Redis queue  │──pop──│   Worker   │
│ builder.py   │        │ builder:queue │       │ worker.py  │
└─────────────┘        └──────────────┘       └─────┬──────┘
                                                     │
                                            SyntheticBuildJob
                                          (synthetic_builder.py)
                                                     │
                                              build_receipt.json
                                                     │
                                              ┌──────▼──────┐
                                              │  PostgreSQL  │
                                              │ provenance   │
                                              └─────────────┘
```

## Files

| File                   | Role                                    |
|------------------------|-----------------------------------------|
| `__init__.py`          | Version, builder name, profile ID       |
| `receipt.py`           | Pydantic schema (20+ models)            |
| `synthetic_builder.py` | Core build logic (3-phase, 12-cell)     |
| `worker.py`            | Redis consumer + DB persistence         |
| `Dockerfile`           | python:3.11-slim + gcc + binutils       |
| `requirements.txt`     | pydantic, redis, psycopg2, pyelftools   |
| `LOCK.md`              | Scope contract — what v1 does and doesn't do |

## Non-Goals (v1)

- No Clang, Rust, or cross-compilation
- No git/repo builds (synthetic multi-file only)
- No DWARF interpretation (builder checks presence only)
- No decompiler integration
- No Windows or macOS targets
