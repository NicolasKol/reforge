# builder_synth_v2 — Scope Lock
> **Package name:** `builder_synth_v2`
> **Version:** v2
> **Profile:** `linux-x86_64-elf-gcc-c`
> **Supersedes:** `builder_synth_v1` (LOCK.md)
> **Scope mantra:** "Compile synthetic C to ELF with GCC; emit artifacts, preprocessed TUs, and receipt.
>                    No DWARF semantics, no alignment, no repo builds."
---

## Purpose

Build synthetic C programs (single- or multi-file, no external deps or build
systems) into ELF binaries across multiple optimization levels and three
variants (debug / release / stripped). Additionally, emit preprocessed
translation units (`.i` files) for downstream source-structure oracles. Emit:

- Binaries stored on disk in a stable layout
- Preprocessed `.i` files (one per TU, optimization-independent)
- Hashes and basic ELF metadata
- A single `build_receipt.json` per job for full provenance

---

## Changes from v1

| Area | v1 | v2 |
|------|----|----|
| Preprocessing | Not supported (`-save-temps` listed as non-goal) | `gcc -E` pass per TU, output stored in `preprocess/` |
| Receipt schema | No `preprocess` field | `preprocess: PreprocessPhase` at top level |
| Builder identity | `builder_synth_v1 / v1` | `builder_synth_v2 / v2` |
| LOCK reference | `LOCK.md` | `LOCK_v2.md` |

All other v1 guarantees, non-goals, and extension points remain unchanged.

---

## Hard guarantees (v2, additive to v1)

### Inherited from v1 (unchanged)
1. Receive synthetic C source files (no git, no build system).
2. Build a matrix of (optimization × variant) cells.
3. For each cell: compile → link → (strip if stripped).
4. Record full provenance in `build_receipt.json`.
5. Validate ELF output; check `.debug_*` section presence for debug variant.
6. Hash all inputs and outputs (SHA-256).

### New in v2
7. **Preprocess phase**: for each `.c` translation unit, run `gcc -E` with
   base cflags (no `-O`, no `-g`) to produce a `.i` file.
8. Preserve `#line` directives in `.i` output (GCC `-E` default behavior).
9. Store `.i` files under `synthetic/{name}/preprocess/{stem}.i`.
10. Store preprocessing logs under `synthetic/{name}/preprocess/logs/`.
11. Record a `PreprocessPhase` in `build_receipt.json` (top-level, not
    per-cell — preprocessing is optimization-independent).
12. Hash each `.i` output (SHA-256) and record in the receipt.

This is **not** `-save-temps`. Only the preprocessor pass (`-E`) is run;
no assembly (`.s`) or other intermediate files are produced.

---

## Preprocess phase details

### Command template
```
gcc -std=c11 -I src -E <source> -o preprocess/<stem>.i
```

### Preprocess cflags
- Base language standard and include paths only: `-std=c11 -I src`
- No optimization flags (`-O*`)
- No debug flags (`-g`)
- No frame-pointer flags (irrelevant to preprocessing)
- Rationale: the preprocessed output is optimization-independent and
  identical across all cells. Running once saves time and avoids redundancy.

### Non-fatal
Preprocessing failure does **not** abort the build. The builder:
1. Logs the failure in `preprocess/logs/`.
2. Sets `preprocess.status = FAILED` in the receipt.
3. Continues to the build matrix as normal.

---

## Outputs — Artifact layout (v2)

```
synthetic/{name}/
├── build_receipt.json          # v2 receipt with preprocess field
├── src/                        # Source snapshot
├── preprocess/                 # NEW — one .i per TU
│   ├── main.i
│   ├── utils.i
│   └── logs/
│       ├── preprocess.main.stdout
│       ├── preprocess.main.stderr
│       └── ...
├── O0/
│   ├── debug/
│   │   ├── obj/ bin/ logs/
│   ├── release/
│   └── stripped/
├── O1/ ...
├── O2/ ...
└── O3/ ...
```

### BuildReceipt additions (v2)

New top-level field in `build_receipt.json`:

```json
{
  "builder": {
    "name": "builder_synth_v2",
    "version": "v2",
    "profile_id": "linux-x86_64-elf-gcc-c",
    "lock_text_hash": "<sha256 of LOCK_v2.md>"
  },
  "preprocess": {
    "command_template": "gcc -std=c11 -I src -E <source> -o preprocess/<stem>.i",
    "units": [
      {
        "source_path_rel": "main.c",
        "output_path_rel": "preprocess/main.i",
        "output_sha256": "<sha256>",
        "exit_code": 0,
        "stdout_path_rel": null,
        "stderr_path_rel": null,
        "duration_ms": 12
      }
    ],
    "status": "SUCCESS"
  }
}
```

---

## Non-goals (v2, same as v1 except preprocessing)

- No git clone or repository builds
- No Clang support
- No C++ support
- No DWARF semantic parsing (that's `oracle_dwarf`)
- No inline resolution, variable extraction, type recovery
- No alignment or ground-truth generation
- No CMake / Make / Autoconf project builds
- No automatic dependency discovery
- No artifact download API
- ~~No assembly output (`-save-temps`)~~ Replaced: targeted `gcc -E` only,
  no `.s` files, no full `-save-temps`

---

## Scope-creep refusal

If a requested feature is not listed in this lock document, or is listed as a
"Non-goal (v2)", it is **out of scope** for `builder_synth_v2` and must be
refused or deferred to a future package with its own lock.

---

## Extension points (future packages)

| Package (tentative)    | Capability                                      |
|------------------------|-------------------------------------------------|
| `builder_repo_v1`      | Git clone + project builds (CMake/Make/etc.)    |
| `builder_clang_v1`     | Clang compiler profile                          |
| `builder_cpp_v1`       | C++ language support                            |
| Profile: multi-arch    | ARM, RISC-V cross-compilation                   |
| `oracle_ts`            | Tree-sitter source oracle (consumes `.i` files) |

Each future package must define its own lock before implementation begins.
