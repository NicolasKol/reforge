# oracle_dwarf v0 — Schema v0.2 Delta Lock

> **Package name:** `oracle_dwarf`
> **Oracle version:** v0 (unchanged)
> **Schema version:** 0.1 → **0.2**
> **Profile:** `linux-x86_64-gcc-O0O1` (unchanged)

---

## Purpose of this delta

Schema v0.2 is a **backward-compatible, additive-only** extension to
`oracle_functions.json`. It serializes per-function DWARF line evidence
that was previously computed internally (in `line_mapper.py`) but
discarded before output. This evidence is required by the downstream
`join_dwarf_ts` package to perform deterministic DWARF↔tree-sitter
alignment without re-parsing ELF binaries.

No existing fields are removed or renamed. Consumers of v0.1 outputs
that ignore unknown fields will continue to work.

---

## Changes from v0.1

### New field: `line_rows` on `OracleFunctionEntry`

```json
"line_rows": [
  {"file": "/build/src/math_recurse.c", "line": 10, "count": 2},
  {"file": "/build/src/recurse.h",      "line": 8,  "count": 1}
]
```

- **Type:** `List[LineRowEntry]` where each entry has `{file: str, line: int, count: int}`.
- **Semantics:** multiset of `(file_path, line_number)` pairs from DWARF `.debug_line` rows that intersect the function's address ranges. `count` is the number of distinct state-machine rows mapping to that `(file, line)` pair.
- **Populated when:** function verdict is `ACCEPT` or `WARN`. Functions with verdict `REJECT` get an empty list (they have no address ranges to intersect).
- **Invariant:** `sum(row.count for row in line_rows) == n_line_rows`.
- **Path format:** paths are as resolved from DWARF file tables — no normalization applied. `#line` mapping is the joiner's responsibility.

### New field: `file_row_counts` on `OracleFunctionEntry`

```json
"file_row_counts": {
  "/build/src/math_recurse.c": 8,
  "/build/src/recurse.h": 3
}
```

- **Type:** `Dict[str, int]` — per-file total line row counts.
- **Semantics:** aggregation of `line_rows` by file path. Equivalent to `{f: sum(r.count for r in line_rows if r.file == f)}`.
- **Note:** this data was already computed internally in `LineSpan.file_row_counts` but not serialized in v0.1.

### `SCHEMA_VERSION` bump

`__init__.py` constant `SCHEMA_VERSION` changes from `"0.1"` to `"0.2"`.
All output JSON files will carry `"schema_version": "0.2"`.

---

## Non-goals of v0.2

- No path normalization or `#line` directive parsing.
- No changes to binary-level gating or function-level verdict logic.
- No new verdict reasons.
- No changes to `oracle_report.json` structure.

---

## Scope-creep refusal

This delta adds exactly two serialization fields. Any request beyond
what is listed here belongs to a future schema version or a separate
package.
