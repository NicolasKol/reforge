# join_dwarf_ts v0 — Scope Lock

> **Package name:** `join_dwarf_ts`
> **Joiner version:** v0
> **Schema version:** 0.1
> **Profile ID:** `join-dwarf-ts-v0`

---

## Purpose

`join_dwarf_ts` is a deterministic DWARF ↔ Tree-sitter alignment joiner.
It maps each ACCEPT/WARN function from `oracle_dwarf` (v0, schema ≥ 0.2)
to the best-matching function node from `oracle_ts` (v0, schema ≥ 0.1),
using GCC `#line` directives in preprocessed `.i` files as the bridge.

The joiner is **read-only** over oracle outputs — it never re-runs
`dwarfdump`, `pyelftools`, or `tree-sitter`.  It consumes JSON files
and `.i` files, produces alignment JSON files.

---

## Support profile (v0)

| Dimension              | Value                                       |
|------------------------|---------------------------------------------|
| DWARF oracle           | `oracle_dwarf` v0, schema ≥ 0.2            |
| Tree-sitter oracle     | `oracle_ts` v0, schema ≥ 0.1               |
| Preprocessor           | GCC `-E` output (`.i` files with `#line`)   |
| Languages              | C                                            |
| Optimization levels    | `-O0`, `-O1`                                |

---

## Hard guarantees (v0)

1. **Origin map**: Parse GCC `#line` directives from `.i` files to build
   a forward map: `.i` line → `(original_path, original_line)`.
   Synthetic/system paths (`<built-in>`, `<command-line>`, paths starting
   with excluded prefixes) are mapped to `None`.

2. **Forward-map scoring**: For each DWARF target function, scan each
   TS function's `.i` line span `[start_line, end_line]` through the
   origin map.  Count how many origin `(file, line)` pairs appear in
   the DWARF evidence multiset.  Denominator = `Σ counts` in the DWARF
   multiset (i.e. `n_line_rows`).

3. **Candidate selection**: Sort candidates by `(-overlap_ratio,
   -overlap_count, span_size, tu_path, start_byte)`.  Apply thresholds:
   - `overlap_ratio ≥ overlap_threshold` (default 0.7)
   - `overlap_count ≥ min_overlap_lines` (default 1)
   - Near-tie detection: runner-up within `epsilon` (default 0.02)

4. **Header replication detection**: If the best candidate and any
   near-tie share the same `context_hash` but differ in `tu_path`,
   flag `HEADER_REPLICATION_COLLISION`.

5. **Verdict assignment**: Each DWARF target receives exactly one of:
   - `MATCH` — unique best candidate above thresholds
   - `AMBIGUOUS` — near-tie or header replication collision
   - `NO_MATCH` — no candidates, below thresholds, or missing origin map

6. **Non-targets**: DWARF functions with verdict `REJECT` are passed
   through as `non_targets` with their original verdict and reasons.

7. **Determinism**: Given identical inputs and profile, the outputs are
   byte-identical (sorted keys, stable tie-break order).

---

## Non-goals (v0)

- No re-running of `dwarfdump`, `pyelftools`, or `tree-sitter`.
- No source-body extraction (downstream concern).
- No cross-compiler support (clang `.i` format may differ).
- No macro expansion reconstruction.
- No inline function resolution beyond what DWARF oracle emits.
- No LLM / heuristic / fuzzy matching.

---

## Verdict policy (v0)

### MATCH reasons

| Reason        | Condition                    |
|---------------|------------------------------|
| `UNIQUE_BEST` | Single best above thresholds |

### AMBIGUOUS reasons

| Reason                          | Condition                                         |
|---------------------------------|---------------------------------------------------|
| `NEAR_TIE`                      | Runner-up within `epsilon` of best                |
| `HEADER_REPLICATION_COLLISION`   | Best and tie share `context_hash`, differ `tu_path`|
| `MULTI_FILE_RANGE_PROPAGATED`   | Propagated from DWARF WARN reason                 |

### NO_MATCH reasons

| Reason               | Condition                                        |
|----------------------|--------------------------------------------------|
| `NO_CANDIDATES`      | No TS functions found in any TU for this DWARF fn|
| `NO_OVERLAP`         | All candidates had zero overlap                  |
| `LOW_OVERLAP_RATIO`  | Best candidate below `overlap_threshold`         |
| `BELOW_MIN_OVERLAP`  | Best candidate below `min_overlap_lines`         |
| `ORIGIN_MAP_MISSING` | `.i` file not found or has no `#line` directives |

---

## Output schema (v0)

Two JSON files per binary variant:

### `alignment_pairs.json`

Per-function alignment results with runtime contract fields
(`package_name`, `joiner_version`, `schema_version`, `profile_id`),
provenance anchors (`binary_sha256`, `build_id`,
`dwarf_profile_id`, `ts_profile_id`), and arrays of `pairs` and
`non_targets`.

Each pair contains: `dwarf_function_id`, `dwarf_function_name`,
`dwarf_verdict`, `best_ts_func_id`, `best_tu_path`,
`best_ts_function_name`, `overlap_count`, `total_count`,
`overlap_ratio`, `gap_count`, `verdict`, `reasons`, `candidates`.

### `alignment_report.json`

Summary metrics: `pair_counts` (`match`, `ambiguous`, `no_match`,
`non_target`), `reason_counts`, `thresholds`,
`excluded_path_prefixes`, `tu_hashes`, `timestamp`.

---

## Filesystem layout

Inputs:
```
synthetic/<name>/preprocess/*.i              # .i files (project-level)
synthetic/<name>/<Ox>/<variant>/oracle/      # oracle_dwarf outputs
synthetic/<name>/oracle_ts/                  # oracle_ts outputs
```

Outputs:
```
synthetic/<name>/<Ox>/<variant>/join_dwarf_ts/alignment_pairs.json
synthetic/<name>/<Ox>/<variant>/join_dwarf_ts/alignment_report.json
```

---

## API

- **Endpoint:** `POST /join/run`
- **Parameters:** `optimization_level` (required), `variant` (default `"debug"`),
  `test_cases` (optional filter), `artifacts_root` (optional override),
  `write_outputs` (default `true`)
- **Behaviour:** Sweeps all test cases under `artifacts_root`, joins
  each that has all three inputs (DWARF oracle, TS oracle, .i files).

---

## Profile defaults (v0)

| Parameter                 | Default value                                      |
|---------------------------|----------------------------------------------------|
| `overlap_threshold`       | 0.7                                                |
| `epsilon`                 | 0.02                                               |
| `min_overlap_lines`       | 1                                                  |
| `excluded_path_prefixes`  | `/usr/include`, `/usr/lib/gcc`, `<built-in>`, `<command-line>` |

---

## Dependencies

| Package        | Version        | Purpose                       |
|----------------|----------------|-------------------------------|
| `oracle_dwarf` | v0 schema ≥0.2 | DWARF function targets        |
| `oracle_ts`    | v0 schema ≥0.1 | Tree-sitter function nodes    |
| `pydantic`     | ≥ 2.10         | Schema validation             |

---

## Scope-creep refusal

If a requested feature is not listed in "Hard guarantees (v0)" and is
listed as a "Non-goal (v0)" (or not mentioned), it is out of scope for
`join_dwarf_ts` v0 and must be refused or deferred to a future version.

---

## Extension points (future versions)

| Version   | Capability                                            |
|-----------|-------------------------------------------------------|
| v0.1      | Multi-file range heuristic improvements               |
| v0.2      | Clang `.i` format support                             |
| v1        | Inline function resolution integration                |
| v1        | LLM-assisted fuzzy matching for NO_MATCH fallback     |
