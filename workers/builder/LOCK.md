# builder_synth_v1 — Scope Lock

> **Package name:** `builder_synth_v1`
> **Version:** v1
> **Profile:** `linux-x86_64-elf-gcc-c`
> **Scope mantra:** "Compile synthetic C to ELF with GCC; emit artifacts + receipt. No DWARF semantics, no alignment, no repo builds."

---

## Purpose

Build synthetic C programs from local source inputs into ELF binaries across multiple optimization levels and three variants (debug / release / stripped). Emit:

- **Binaries** stored on disk in a stable layout
- **Hashes and basic ELF metadata** (type, arch, build-id)
- **A single `build_receipt.json`** per job for full provenance

Later provenance, oracle, and linking happen elsewhere. This package only produces build outputs + receipt.

---

## Profile (v1)

| Dimension        | Value                      |
|------------------|----------------------------|
| Profile ID       | `linux-x86_64-elf-gcc-c`   |
| Compiler         | GCC only                   |
| Output format    | ELF                        |
| Architecture     | x86_64 only (in container) |
| Language         | C only                     |
| Link libraries   | `-lm` (allowlist, baked)   |

Not user-selectable. The profile is hard-locked in v1.

---

## Build matrix

### Optimization levels

| Level | Exact string |
|-------|-------------|
| O0    | `-O0`       |
| O1    | `-O1`       |
| O2    | `-O2`       |
| O3    | `-O3`       |

### Variants

| Variant   | Semantics                                         |
|-----------|---------------------------------------------------|
| `debug`   | Includes `-g`. DWARF presence check (sections only). |
| `release` | Optimized, not stripped. No DWARF requirement.    |
| `stripped` | Optimized + `strip --strip-all`. Best-effort verify. |

### Base compile flags (v1 defaults)

```
-std=c11 -Wno-error -fno-omit-frame-pointer -mno-omit-leaf-frame-pointer
```

### Variant deltas

| Variant   | Additional flags | Post-processing |
|-----------|-----------------|-----------------|
| `debug`   | `-g`            | —               |
| `release` | (none)          | —               |
| `stripped` | (none)          | `strip --strip-all` |

---

## Inputs

### API surface

One FastAPI router with:

| Endpoint                | Method | Purpose                              |
|-------------------------|--------|--------------------------------------|
| `/builder/synthetic`    | POST   | Submit synthetic build job           |
| `/builder/job/{job_id}` | GET    | Job status by UUID                   |
| `/builder/synthetic/{name}` | GET | Status by test case name           |
| `/builder/synthetic/{name}` | DELETE | Delete a synthetic build          |
| `/builder/synthetic`    | DELETE | Delete all synthetic builds          |

### Request model

| Field          | Type                     | Required | Notes                                  |
|----------------|--------------------------|----------|----------------------------------------|
| `name`         | string                   | yes      | Unique test case identifier            |
| `files`        | `[{filename, content}]`  | *        | Multi-file input                       |
| `source_code`  | string                   | *        | Single-file convenience (auto-wrapped) |
| `test_category`| string                   | yes      | Category tag                           |
| `language`     | string                   | no       | Only `"c"` accepted                    |
| `optimizations`| string[]                 | no       | Default `["O0","O1","O2","O3"]`        |
| `target`       | `{optimization, variant}`| no       | Single-cell rebuild override           |

\* Exactly one of `files` or `source_code` must be provided.

---

## Outputs

### Artifact layout

```
synthetic/{name}/
├── build_receipt.json          # Single authoritative receipt
├── src/                        # Source snapshot (for reproducibility)
│   ├── main.c
│   ├── utils.c
│   └── utils.h
├── O0/
│   ├── debug/
│   │   ├── obj/                # .o files
│   │   ├── bin/{name}          # Linked ELF
│   │   └── logs/               # compile.*.stdout/stderr, link.*, strip.*
│   ├── release/
│   │   ├── obj/ bin/ logs/
│   └── stripped/
│       ├── obj/ bin/ logs/
├── O1/ ...
├── O2/ ...
└── O3/ ...
```

### BuildReceipt (`build_receipt.json`)

Single JSON per job containing:

1. **`builder`**: name, version, profile_id, lock_text_hash
2. **`job`**: job_id, name, created_at, finished_at, status
3. **`source`**: kind, entry_type (single/multi), files[], snapshot_sha256
4. **`toolchain`**: container_id, gcc_version, binutils_version, strip_version, os_release, kernel, arch
5. **`profile`**: profile_id, compiler, output_format, arch, language, link_libs
6. **`requested`**: optimizations[], variants[], compile_policy (base_cflags, include_dirs, defines, link_libs, variant_deltas)
7. **`builds[]`**: Per-cell results with:
   - `optimization`, `variant`, `status`, `flags[]`
   - `compile`: command_template, units[], summary
   - `link`: command, exit_code, stdout/stderr paths, duration_ms
   - `strip` (stripped only): command, exit_code, paths, duration_ms
   - `artifact`: path_rel, sha256, size_bytes, elf (type, arch, build_id), debug_presence

---

## Build flags (per cell)

| Flag                      | Condition                                  |
|---------------------------|--------------------------------------------|
| `BUILD_FAILED`            | Cell did not produce a usable artifact     |
| `TIMEOUT`                 | Any phase timed out                        |
| `NO_ARTIFACT`             | Link didn't produce binary                 |
| `COMPILE_UNIT_FAILED`     | At least one TU failed compilation         |
| `LINK_FAILED`             | Link phase failed                          |
| `DEBUG_EXPECTED_MISSING`  | Debug variant missing .debug_* sections    |
| `STRIP_FAILED`            | Strip command failed                       |
| `STRIP_EXPECTED_MISSING`  | Stripped variant still has .debug_* sections|
| `NON_ELF_OUTPUT`          | Output is not valid ELF                    |

No inline/optimization alignment flags. Those are downstream/oracle.

---

## Checks (tight boundary)

Builder checks:
- ELF validation (is ELF + arch + type) via `pyelftools`
- SHA-256 hashing of all artifacts and source files
- `.debug_*` presence check **only for debug variant** (section names only)
- Stripped variant: record strip command, best-effort verify outcome
- No DWARF parsing, no `.debug_line` interpretation, no function extraction

---

## Non-goals (v1)

- No git clone or repository builds
- No Clang support
- No C++ support
- No DWARF semantic parsing (that's `oracle_dwarf`)
- No inline resolution, variable extraction, type recovery
- No alignment or ground-truth generation
- No CMake / Make / Autoconf project builds
- No automatic dependency discovery
- No artifact download API
- No assembly output (`-save-temps`)

---

## Database schema (v1 baseline)

### `reforge.synthetic_code`

| Column           | Type          | Notes                              |
|------------------|---------------|------------------------------------|
| `id`             | UUID PK       | Job ID from submission             |
| `name`           | VARCHAR UNIQUE| Test case identifier               |
| `test_category`  | VARCHAR       | Category tag                       |
| `language`       | VARCHAR       | Always `'c'` in v1                 |
| `snapshot_sha256` | VARCHAR(64)  | Hash of all source files           |
| `file_count`     | INT           | Number of source files             |
| `source_files`   | JSONB         | `[{path_rel, sha256, size, role}]` |
| `status`         | VARCHAR       | QUEUED/SUCCESS/PARTIAL/FAILED      |
| `metadata`       | JSONB         | Receipt summary, toolchain, etc.   |

### `reforge.binaries`

| Column              | Type     | Notes                           |
|---------------------|----------|---------------------------------|
| `id`                | UUID PK  |                                 |
| `synthetic_code_id` | UUID FK  | NOT NULL, CASCADE delete        |
| `file_path`         | TEXT     | Filesystem path                 |
| `file_hash`         | VARCHAR  | SHA-256, UNIQUE                 |
| `file_size`         | BIGINT   |                                 |
| `compiler`          | VARCHAR  | Always `'gcc'`                  |
| `optimization_level`| VARCHAR  | O0/O1/O2/O3                     |
| `variant_type`      | VARCHAR  | debug/release/stripped           |
| `architecture`      | VARCHAR  | Default `'x86_64'`              |
| `has_debug_info`    | BOOLEAN  |                                 |
| `is_stripped`        | BOOLEAN  |                                 |
| `elf_metadata`      | JSONB    | `{elf_type, arch, build_id}`    |
| `metadata`          | JSONB    | `{flags[], cell_status}`        |

---

## Scope-creep refusal

If a requested feature is not listed in this lock document, or is listed as a "Non-goal (v1)", it is **out of scope** for `builder_synth_v1` and must be refused or deferred to a future package with its own lock.

---

## Extension points (future packages)

| Package (tentative)    | Capability                                      |
|------------------------|-------------------------------------------------|
| `builder_repo_v1`      | Git clone + project builds (CMake/Make/etc.)    |
| `builder_clang_v1`     | Clang compiler profile                          |
| `builder_cpp_v1`       | C++ language support                            |
| Profile: multi-arch    | ARM, RISC-V cross-compilation                   |

Each future package must define its own lock before implementation begins.
