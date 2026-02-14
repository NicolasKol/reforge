# join_oracles_to_ghidra_decompile v1 — Scope Lock

> **Package name:** `join_oracles_to_ghidra_decompile`
> **Joiner version:** v1
> **Schema version:** 0.1
> **Profile ID:** `join-oracles-ghidra-v1`

---

## §1 Purpose

`join_oracles_to_ghidra_decompile` constructs the **experiment substrate**
for LLM-assisted reverse engineering by joining:

1. **Source-side oracle plane** — `oracle_dwarf` function inventory + DWARF
   extraction verdicts, and `join_dwarf_ts` alignment results (function
   mapping, ambiguity, overlap/gap evidence).

2. **Decompiler view plane** — `analyzer_ghidra_decompile` outputs
   (decompiled C, variables, calls, CFG, warnings).

The join produces a provenance-rich "what the model *actually sees*" view
plus diagnostic deltas indicating where the decompiler under-approximated,
merged, or distorted program structure.  No "truth" is claimed; the join
is read-only over all upstream outputs.

---

## §2 Support profile (v1)

| Dimension              | Value                                          |
|------------------------|-------------------------------------------------|
| DWARF oracle           | `oracle_dwarf` v0, schema ≥ 0.2               |
| Alignment joiner       | `join_dwarf_ts` v0, schema ≥ 0.1              |
| Ghidra analyzer        | `analyzer_ghidra_decompile` v1, schema ≥ 1.0  |
| Builder receipt        | v2                                              |
| Architecture           | linux-x86_64                                    |
| Optimization levels    | O0–O3 (tolerant; tags incomplete upstream data) |
| Languages              | C                                               |

---

## §3 Hard guarantees (v1)

1. **Binary provenance gate:** The join validates `binary_sha256` across
   all four input sources (build receipt, oracle report, alignment pairs,
   Ghidra report).  Mismatch is a hard failure.

2. **All DWARF functions preserved:** Every function from
   `oracle_functions.json` appears in the output, including REJECT and
   NON_TARGET entries.  Filtering is downstream.

3. **No fabrication for NO_RANGE:** Functions with missing/unusable DWARF
   address ranges receive `ghidra_match_kind = NO_RANGE` and are not
   force-joined to any Ghidra function.

4. **Many-to-one preservation:** When multiple DWARF functions map to the
   same Ghidra function (inlining/merging), all rows are kept and tagged
   with `fat_function_multi_dwarf = true` and the count
   `n_dwarf_funcs_per_ghidra_func`.

5. **Non-destructive tagging:** Noise classification (`is_aux_function`,
   `is_import_proxy`, `is_external_block`, `is_non_target`, `is_thunk`)
   is additive — no rows are deleted.

6. **Determinism:** Given identical inputs and profile, the outputs are
   byte-identical.  JSONL rows are sorted by `(dwarf_function_id,
   ghidra_entry_va)`.  JSON uses `sort_keys=True`.

7. **High-confidence gate:** The `is_high_confidence` flag identifies
   rows that are maximally suitable for LLM evaluation (ACCEPT oracle +
   unique MATCH alignment + JOINED_STRONG + no noise + no fatal warnings +
   cfg_completeness ≠ LOW).

---

## §4 Outputs

Three files per `<test_case>/<opt>/<variant>/join_oracles_ghidra/`:

| File                     | Format | Description                              |
|--------------------------|--------|------------------------------------------|
| `join_report.json`       | JSON   | Aggregated counts, yield, distributions  |
| `joined_functions.jsonl` | JSONL  | One row per DWARF function entry         |
| `joined_variables.jsonl` | JSONL  | Stub (v1); empty file with valid schema  |

---

## §5 Address-overlap join logic 

**Primary key:** `binary_sha256` (cross-validated across all sources).

**Mapping rule:** For each DWARF function with `[low_pc, high_pc)` ranges:

1. Find all Ghidra functions whose `[body_start_va, body_end_va)` overlaps
   any DWARF interval.
2. Sum `overlap_bytes` across fragmented DWARF ranges for each candidate.
3. `pc_overlap_ratio = overlap_bytes / dwarf_total_range_bytes`.
4. Select best candidate by: max overlap_bytes → min distance to low_pc →
   prefer non-thunk → prefer non-external.
5. Near-tie detection: candidates within 5% of best overlap_bytes.

| Match kind       | Condition                            |
|------------------|--------------------------------------|
| `JOINED_STRONG`  | `pc_overlap_ratio ≥ 0.9`           |
| `JOINED_WEAK`    | `0.3 ≤ pc_overlap_ratio < 0.9`     |
| `MULTI_MATCH`    | Near-ties detected                   |
| `NO_MATCH`       | No overlap or ratio < 0.3           |
| `NO_RANGE`       | DWARF ranges missing/unusable        |

Ghidra functions with `body_start_va = null` or `body_end_va = null` are
excluded from the interval index.

---

## §6 High-confidence gate

`is_high_confidence = true` iff ALL of:

- DWARF oracle verdict = `ACCEPT`
- Alignment: `MATCH`, `n_candidates == 1`, `overlap_ratio == 1.0`
- Function join: `JOINED_STRONG`
- Not noise: not external_block, not thunk, not aux, not import_proxy
- `cfg_completeness ≠ LOW`
- No fatal warnings (`DECOMPILE_TIMEOUT`, `UNRESOLVED_INDIRECT_JUMP`)

---

## §7 Variable join (v1 — stub)

Variable join requires per-variable DWARF storage evidence, which is not
available from `oracle_dwarf` schema ≤ 0.2.  In v1:

- `joined_variables.jsonl` is structurally valid but contains zero rows.
- `join_report.json` includes `variable_join.implemented = false` with
  a diagnostic reason.

---

## §8 Profile defaults (v1)

| Parameter                   | Default                          |
|-----------------------------|----------------------------------|
| `strong_overlap_threshold`  | 0.9                              |
| `weak_overlap_threshold`    | 0.3                              |
| `near_tie_epsilon`          | 0.05 (fraction of best bytes)    |
| `aux_function_names`        | 24-name frozen set (§9.2+§9.3 of analyzer LOCK) |
| `fatal_warnings`            | `DECOMPILE_TIMEOUT`, `UNRESOLVED_INDIRECT_JUMP` |

---

## §9 Non-goals (v1)

- No cross-binary matching (O0↔O3 transitions remain in `data/metrics`).
- No attempt to "repair" Ghidra output.
- No LLM invocation or heuristic matching.
- No inference of CFG ground-truth from DWARF beyond PC ranges.
- No variable join (deferred to v2 when oracle_dwarf schema gains variable extraction).
- API surface is a thin sweep endpoint (`POST /join-ghidra/run`) in the
  central Reforge FastAPI app; the runner remains a library function.

---

## §10 Dependencies

| Package                       | Version         | Purpose                         |
|-------------------------------|-----------------|----------------------------------|
| `oracle_dwarf`                | v0 schema ≥ 0.2 | DWARF function inventory + line evidence |
| `join_dwarf_ts`               | v0 schema ≥ 0.1 | DWARF↔TS alignment pairs         |
| `analyzer_ghidra_decompile`   | v1 schema ≥ 1.0 | Ghidra decompiler outputs        |
| `builder` (receipt)           | v2               | Build provenance                 |
| `pydantic`                    | ≥ 2.10           | Schema validation                |

---

## §11 Scope-creep refusal

If a requested feature is not listed in "Hard guarantees (v1)" and is
listed as a "Non-goal (v1)" (or not mentioned), it is out of scope for
`join_oracles_to_ghidra_decompile` v1 and must be refused or deferred
to a future version.

---

## §12 Extension points (future versions)

| Version | Capability                                        |
|---------|---------------------------------------------------|
| v1.1    | `joined_calls.jsonl` with caller/callee linkage   |
| v2      | Real DWARF variable join (requires oracle schema v0.3) |
| v2      | Name-based fallback for NO_RANGE functions        |
| v3      | Cross-decompiler join (IDA, Binary Ninja)         |
