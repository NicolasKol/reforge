# Data Module Audit — `oracle_decl_identity_v1`

**Date:** 2026-02-12
**Scope:** `reforge/data/`, `reforge/workers/oracle_dwarf/`, `reforge/workers/join_dwarf_ts/`
**Status:** PATCH APPLIED

---

## 1. Findings summary

| # | Location | Severity | Category | Description |
|---|----------|----------|----------|-------------|
| **BUG-1** | `metrics.compute_transitions` | **CRITICAL** | Data loss | Name-based dedup/join on `(test_case, dwarf_function_name)` silently drops 35–55 % of pairs per test case. Static functions, header-inlined functions, and any same-named functions across compilation units are collapsed to a single row. |
| **BUG-2** | `metrics.enrich_pairs` | **MODERATE** | Off-by-one | `n_candidates = 1 + len(candidates)` overcounts by 1 because the best match is already inside the candidates list. |
| **BUG-3** | Loader + data | **MODERATE** | Null safety | `t10_math_libm/O1` contains a DWARF function with `dwarf_function_name: null`. This causes silent row dropping in any `groupby/drop_duplicates` that touches the name column. |
| DES-4 | `metrics.compute_reason_shift` | LOW | Semantics | Share denominator sums reason-tag events (not pair counts). Multi-reason pairs inflate the total. Not wrong, but must be documented. |
| DES-5 | `metrics.compute_reason_shift` | LOW | Bias | Cross-test-case `groupby("opt").sum()` gives more weight to test cases with more functions. |

### Root-cause evidence

- **BUG-1:** `dwarf_function_name` is not unique within `(test_case, opt)`. Confirmed in `t04_static_dup_names` (3 × `report`, 3 × `process`, 3 × `validate`), `t01_crossfile_calls` (2 × `clamp_int`), and every other test case (header-inlined duplicates). The upstream data carries `dwarf_function_id` (`cu<hex>:die<hex>`) which is unique within an opt level, but DWARF byte offsets are **not stable across optimization levels** (86 % shift between O0 and O1). No stable cross-opt identifier existed prior to this patch.

- **BUG-2:** Verified across all 336 pairs: `best_ts_func_id` is always present inside the `candidates` array (100 %). Adding 1 double-counts the best match.

- **BUG-3:** `cu0xc70:die0xfc5` in `t10_math_libm/O1` has `dwarf_function_name: null`. Pandas `groupby(dropna=True)` silently excludes it.

### Source data integrity

The upstream JSON artifacts are internally consistent:
- `alignment_report.json` pair_counts match actual row counts in `alignment_pairs.json` (verified across all 24 combos).
- `oracle_report.json` function_counts always satisfy `total == accept + warn + reject`.
- `_flatten_*` functions in the loader faithfully transcribe the JSON; no data corruption during loading.

---

## 2. Patch: `oracle_decl_identity_v1`

### Goal

Emit **source declaration identity** (`decl_file`, `decl_line`, `decl_column`, `comp_dir`, `cu_id`) for every DWARF subprogram — including REJECT/NON_TARGET functions. This provides a stable cross-optimization join key that eliminates name-collision ambiguity.

### Changes applied

#### 2.1 Oracle DWARF extraction (`workers/oracle_dwarf/`)

| File | Change |
|------|--------|
| `core/function_index.py` | Read `DW_AT_decl_file` (file index), `DW_AT_decl_line`, `DW_AT_decl_column` from DIE. Add `decl_column` field. Resolve `decl_file` from raw index to path via line program file entries using `_resolve_file`. |
| `core/line_mapper.py` | Export `resolve_file_index()` — public wrapper around `_resolve_file` for use by `function_index`. |
| `io/schema.py` | Add `decl_file`, `decl_line`, `decl_column`, `comp_dir`, `cu_id`, `decl_missing_reason` to `OracleFunctionEntry`. |
| `runner.py` | Propagate new fields from `FunctionEntry` → `OracleFunctionEntry`. |
| `__init__.py` | Bump `SCHEMA_VERSION` to `"0.3"`. |

#### 2.2 Joiner (`workers/join_dwarf_ts/`)

| File | Change |
|------|--------|
| `core/join.py` | Read `decl_file`, `decl_line`, `decl_column`, `comp_dir` from DWARF function dicts. Propagate onto `AlignmentPair` and `NonTargetEntry`. |
| `io/schema.py` | Add `decl_file`, `decl_line`, `decl_column`, `comp_dir` to `AlignmentPair` and `NonTargetEntry`. |
| `__init__.py` | Bump `SCHEMA_VERSION` to `"0.2"`. |

#### 2.3 Data module (`data/`)

| File | Change |
|------|--------|
| `schema.py` | Add `decl_file`, `decl_line`, `decl_column`, `comp_dir` to `AlignmentPair`, `NonTargetEntry`. |
| `loader.py` | Flatten new fields into pairs and non_targets DataFrames. Add `dwarf_function_name_norm` (null → `<anon@{id}>`). |
| `metrics.py` | Fix `n_candidates` (remove +1). `compute_transitions` uses `dwarf_function_id` within each opt level (no dedup by name). Cross-opt merge uses stable key `(test_case, decl_file, decl_line, dwarf_function_name_norm)` with explicit fallback/unresolved handling. |
| `enums.py` | Add `DeclMissingReason` enum. Add `StableKeyQuality` enum. |

#### 2.4 Tests (`data/tests/`)

New test module `test_data_integrity.py` covering:
- Test A: No silent collapse within opt
- Test B: Stable key completeness
- Test C: Cross-opt transition multiplicity
- Test D: Dropped counting correctness
- Test E: `n_candidates` correctness
- Test F: Null name does not disappear

---

## 3. Stable identity contract

**Primary stable key:** `(test_case, decl_file, decl_line, decl_column, dwarf_function_name_norm)`

**Fallback (no column):** `(test_case, decl_file, decl_line, dwarf_function_name_norm)` → `stable_key_quality = MEDIUM`

**Fallback (no line):** `(test_case, decl_file, dwarf_function_name_norm)` → `stable_key_quality = LOW`

**Unresolved (no decl_file):** `(test_case, "<decl_missing>", dwarf_function_id)` → `stable_key_quality = UNRESOLVED`. These rows must not be merged across opt levels.

---

## 4. Acceptance criteria

- [ ] `compute_transitions` produces 3 transition rows for `report`/`process`/`validate` in `t04_static_dup_names` (not 1).
- [ ] No silent NA drops in any groupby/join operation.
- [ ] All unresolved identity cases are explicitly labeled (never silently merged).
- [ ] All integrity tests pass.
