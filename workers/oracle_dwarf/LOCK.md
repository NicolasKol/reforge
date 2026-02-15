# oracle_dwarf v0.1 — Scope Lock

> **Package name:** `oracle_dwarf`
> **Oracle version:** v0.1
> **Support profile:** `linux-x86_64-gcc-O0O1O2O3`
> **Schema version:** 0.3

---

## Purpose

`oracle_dwarf` is a DWARF-based alignment oracle. Its job is to extract function-level alignment targets and quality/verdict metadata from Linux ELF binaries compiled with GCC, and to do so in a way that is stable, versioned, and resistant to scope creep.

This package is **not** a ground-truth reconstructor. It emits behavioral alignment targets that are consistent with available debug metadata and observed address ranges, plus explicit uncertainty flags. It makes no claim of recovering "the original source truth" beyond the fields it emits.

---

## Support profile (v0.1)

| Dimension          | Value                     |
|-----------------------|---------------------------|
| Target platform    | linux-x86_64              |
| Binary format      | ELF                       |
| Toolchain          | gcc                       |
| Optimization levels| `-O0`, `-O1`, `-O2`, `-O3`|

Anything outside the profile is best-effort at most and may be REJECT.

---

## Hard guarantees (v0)

1. Extract non-library function candidates from DWARF `.debug_info` (`DW_TAG_subprogram` DIEs).
2. Normalize each function's code range into a canonical list of `[low, high)` segments using `DW_AT_low_pc` / `DW_AT_high_pc` and/or `DW_AT_ranges`.
3. For each function range, compute:
   - **Dominant source file** and **dominant-file ratio**
   - **Line span** (`line_min`, `line_max`) and `n_line_rows`
   using DWARF `.debug_line` row intersection against the normalized ranges.
4. Emit structured per-binary and per-function verdicts: `ACCEPT`, `WARN`, or `REJECT` with reason enums.

---

## Non-goals (v0)

- No AST parsing or source-body reconstruction.
- No variable extraction, type recovery, or symbol recovery beyond optional DWARF names.
- No inline chain resolution.
- No cross-compiler guarantees (clang and others are explicitly out of scope).
- No claims of correctness beyond emitted fields and their explicit caveats.

---

## Source-body extraction accommodation (v0)

v0 does **not** require Tree-sitter (or any parser) and remains usable without any source checkout.

v0 **does** include schema hooks for future source-body extraction:
- Nullable `source_extract` field on each function entry.
- Independent `source_ready` verdict (`YES` | `NO` | `WARN`), always `NO` in v0.

Complete function-body extraction is a later package and must not be coupled as a hard dependency.

---

## Verdict policy (v0)

### Binary-level hard rejects

| Reason               | Condition                                  |
|----------------------|--------------------------------------------|
| `NO_DEBUG_INFO`      | `.debug_info` section missing              |
| `NO_DEBUG_LINE`      | `.debug_line` section missing              |
| `UNSUPPORTED_ARCH`   | Not ELF x86-64                             |
| `SPLIT_DWARF`        | `.dwo`-style or `.gnu_debugaltlink` found  |
| `DWARF_PARSE_ERROR`  | pyelftools cannot parse                    |

### Function-level rejects

| Reason                  | Condition                                    |
|-------------------------|----------------------------------------------|
| `DECLARATION_ONLY`      | `DW_AT_declaration = true`                   |
| `MISSING_RANGE`         | No `low_pc`/`high_pc` and no `DW_AT_ranges`  |
| `NO_LINE_ROWS_IN_RANGE` | Zero `.debug_line` rows intersect the ranges |

### Function-level warnings

| Reason                    | Condition                                        |
|---------------------------|--------------------------------------------------|
| `MULTI_FILE_RANGE`        | Dominant-file ratio below profile threshold (0.7)|
| `SYSTEM_HEADER_DOMINANT`  | Dominant file under excluded paths               |
| `RANGES_FRAGMENTED`       | More than `max_fragments_warn` range segments    |
| `NAME_MISSING`            | No `DW_AT_name`; function keyed by DIE/range     |

---

## Output schema (v0)

Two JSON files per binary:

### `oracle_report.json`

Binary-level summary with runtime contract fields (`package_name`, `oracle_version`, `profile_id`, `schema_version`), binary metadata (path, SHA-256, build-id), verdict + reasons, and function counts.

### `oracle_functions.json`

Array of per-function entries with: `function_id`, `die_offset`, `cu_offset`, `name`, `linkage_name`, `ranges`, `dominant_file`, `dominant_file_ratio`, `line_min`, `line_max`, `n_line_rows`, `verdict`, `reasons`, `source_extract` (null), `source_ready` ("NO").

---

## Scope-creep refusal

If a requested feature is not listed in "Hard guarantees (v0)" and is listed as a "Non-goal (v0)" (or not mentioned), it is out of scope for `oracle_dwarf` v0 and must be refused or deferred to a future package.

---

## Extension points (future packages)

The following are explicitly identified as future work and are **not** part of v0:

| Package (tentative)   | Capability                                          |
|-----------------------|-----------------------------------------------------|
| `oracle_source`       | Tree-sitter AST parsing, source-body extraction     |
| `oracle_vars`         | Variable extraction (DW_TAG_variable, DW_AT_location)|
| `oracle_types`        | Type graph resolution (DW_TAG_base_type, structs)   |
| `oracle_inline`       | Inline chain resolution (DW_TAG_inlined_subroutine) |
| `oracle_align`        | Full source-binary alignment engine (joins all)      |
| Profile: clang        | Cross-compiler support                               |

Each future package must define its own lock before implementation begins.

---

## Version History

### v0.1.1 (February 2026)
- **Overlapping range merge**: `_normalize_ranges` now merges overlapping and
  adjacent `[low, high)` segments via `_merge_ranges`.  Prevents inflated
  `total_range_bytes` in downstream `join_oracles_to_ghidra_decompile`.
  Line evidence (`n_line_rows`, `line_rows`, `dominant_file_ratio`) was
  already safe — `_in_ranges` is a boolean per-row check — but byte-range
  totals improve for binaries with overlapping range-list entries.
- **CU line-table caching**: `compute_line_span` accepts an optional
  `line_table` parameter.  `runner.py` now builds the line table once per
  CU and reuses it for all functions, avoiding redundant state-machine
  replays.  Outputs are numerically identical; this is a performance
  improvement only.
- **O2/O3 test coverage**: Added `MULTI_FUNC_C` fixture with
  `__attribute__((noinline))` functions and O2/O3 compilation fixtures.
  New `test_higher_opts.py` validates binary gate, function enumeration,
  range validity, line-span invariants, and overlap safety at higher
  optimization levels — substantiating the v0.1 O2/O3 support claim.
- No schema version bump — output format is unchanged.

### v0.1 (February 2026)
- **Expanded optimization level support**: Added O2 and O3 to supported optimization levels
- Profile ID changed from `linux-x86_64-gcc-O0O1` to `linux-x86_64-gcc-O0O1O2O3`
- No schema changes; core oracle logic already handles higher optimization levels
- Removed "Profile: O2/O3" from future work (now supported)

### v0 (Initial)
- Initial locked scope: linux-x86_64-gcc with O0 and O1 support
- DWARF-based function extraction and verdict system
- Schema version 0.3 with source declaration identity fields
