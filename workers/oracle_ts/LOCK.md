# oracle_ts v0 — Scope Lock

> **Package name:** `oracle_ts`
> **Oracle version:** v0
> **Profile:** `source-c-treesitter`
> **Schema version:** 0.1
> **Scope mantra:** "Parse preprocessed C (.i) with tree-sitter; index
>                    functions and structural nodes with stable IDs.
>                    No binary inspection, no semantic inference."

---

## Purpose

Deterministic source-structure oracle that produces syntactic ground truth
from compiler-emitted preprocessed C translation units (`.i`). Indexes
functions and selected structural nodes with stable identifiers and
extraction recipes, enabling later joining with `oracle_dwarf` outputs and
supporting LLM/decompiler evaluation that requires well-defined source units.

This oracle is orthogonal to `oracle_dwarf`: it does not inspect binaries,
does not infer optimization effects, and does not claim semantic "truth."
It strictly reports what is present syntactically in the `.i` input and
provides metadata needed for downstream mismatch detection.

---

## Inputs

- **Required:** one or more preprocessed C translation units (`*.i`).
- **Required provenance:** builder receipt fields sufficient to reproduce
  preprocessing (compiler version, flags affecting preprocessing, include
  paths, defines), or a `compile_commands.json` entry for each TU.
- **Optional:** raw `.c`/`.h` sources for human-facing views; not used as
  authoritative input in v0.

---

## Hard guarantees (v0)

### TU Parse Report
1. For each `.i` file, parse with tree-sitter C grammar.
2. Report `tu_path`, `tu_hash` (sha256 of raw text).
3. Report `parser` (tree-sitter runtime version + grammar repo/version/commit).
4. Report `parse_status`: OK | ERROR.
5. Report `parse_errors`: list with `(line, col, message)`.

### Function Index
6. For each `function_definition` node in the parse tree:
   - Extract `name` (as parsed), `start_line`/`end_line`, `start_byte`/`end_byte`.
   - Extract `signature_span` (byte/line) and `body_span` (byte/line).
   - Compute stable ID:
     - `span_id = tu_path:start_byte:end_byte`
     - `context_hash`: hash of normalized function text (see Normalization).
     - `ts_func_id = span_id + ":" + context_hash`
   - Compute `node_hash_raw`: hash of raw extracted function text.
   - Compute `preamble_span`: byte/line span of TU prefix (0 → start_byte).
   - Assign `verdict`: ACCEPT | WARN | REJECT with `reasons[]`.

### Structural Node Index
7. Within each function, index nodes for a fixed allowlist:
   `compound_statement`, `if_statement`, `for_statement`,
   `while_statement`, `do_statement`, `switch_statement`,
   `return_statement`, `goto_statement`, `labeled_statement`.
8. For each node:
   `node_type`, spans (byte/line), `node_hash_raw`, `depth`.
9. Set `uncertainty_flags: ["DEEP_NESTING"]` when depth ≥ threshold.

### Extraction Recipes
10. Support deterministic extraction outputs (slicing, not compilation):
    - `function_only`: exact function span.
    - `function_with_file_preamble`: TU prefix + function span.

---

## Outputs

oracle_ts v0 emits structured JSON artifacts per project:

```
synthetic/{name}/oracle_ts/
├── oracle_ts_report.json        # TU-level parse reports
├── oracle_ts_functions.json     # Per-function index + structural nodes
└── extraction_recipes.json      # Deterministic extraction recipes
```

### oracle_ts_report.json
Per-TU parse reports with parser version, parse status, error list.

### oracle_ts_functions.json
Per-function entries with stable IDs, spans, hashes, verdicts, and
nested structural node indexes.

### extraction_recipes.json
Per-function extraction instructions for `function_only` and
`function_with_file_preamble` modes.

---

## Verdict policy (v0)

Verdicts are strictly syntactic/structural:

### ACCEPT
TU parses and function node extracted with valid spans.

### WARN (reasons)
| Reason | Condition |
|--------|-----------|
| `DUPLICATE_FUNCTION_NAME` | Same name appears multiple times in TU |
| `DEEP_NESTING` | Node depth beyond threshold |
| `ANONYMOUS_AGGREGATE_PRESENT` | Anonymous structs/unions/enums in span |
| `NONSTANDARD_EXTENSION_PATTERN` | Best-effort detection |

### REJECT (reasons)
| Reason | Condition |
|--------|-----------|
| `TU_PARSE_ERROR` | Cannot reliably parse TU |
| `INVALID_SPAN` | Span ordering error, empty range |
| `MISSING_FUNCTION_NAME` | Parser cannot recover name |

oracle_ts v0 must not invent semantics; all verdict reasons must be
derived from parse-tree properties.

---

## Normalization for context_hash

Deterministic and explicitly documented. v0 normalization:
- Remove all whitespace (or canonicalize to single spaces).
- Strip C comments (`/* ... */` and `// ...`) if present.
- Do **not** rewrite tokens (no hex→decimal, no identifier renaming,
  no constant folding).
- Hash algorithm: SHA-256.

This prevents "normalization divergence" between oracle outputs and later
LLM/decompiler pipelines.

---

## Non-goals (v0)

- Does not resolve includes beyond what is already in `.i`.
- Does not perform dependency closure across TUs.
- Does not guarantee recompilability (only provides extraction modes).
- Does not map to binaries, RVAs, or DWARF (handled by join layer).
- Does not detect semantic loss (struct flattening, dead-branch removal).
- Does not deduplicate macro/template expansions across repeated `.i`
  content (only emits data needed for later dedup: `context_hash`, spans).
- Does not inspect binaries or ELF metadata.

---

## Required for join-phase compatibility

oracle_ts v0 must provide sufficient metadata for later join/mismatch
detection:
- Per-function line spans, per-node line spans.
- `context_hash` and raw hash.
- Nesting depth and uncertainty flags.

---

## Scope-creep refusal

If a requested feature is not listed in this lock document, or is listed
as a "Non-goal (v0)", it is **out of scope** for `oracle_ts` v0 and must
be refused or deferred to a future package with its own lock.

---

## Extension points (future packages)

| Package (tentative) | Capability |
|---------------------|------------|
| `oracle_ts_v1`      | Multi-TU dedup, cross-reference, macro tracking |
| `oracle_align`      | Join oracle_ts + oracle_dwarf for mismatch detection |
| `oracle_vars`       | Variable/type extraction from source |
| `oracle_types`      | Type recovery and matching |

Each future package must define its own lock before implementation begins.

---

## Changelog

### v0.1.1 (2025-02-15)

**Structural-node allowlist expansion (non-breaking).** Added
`do_statement`, `goto_statement`, and `labeled_statement` to
`STRUCTURAL_NODE_TYPES`. Existing indexed node types are unchanged; new
types are additive — downstream consumers that filter by type are
unaffected. No schema version bump required (output shape is unchanged;
only new `node_type` string values may appear).

**`_find_func_node` fallback fix.** When the helper could not locate the
`function_definition` node (returns `None`), the runner fell back to
passing the entire TU root to `judge_function`, causing
`_has_anonymous_aggregate` to scan the whole translation unit and produce
false `ANONYMOUS_AGGREGATE_PRESENT` warnings on unrelated functions. The
runner now passes `None`, and `judge_function` skips the anonymous-
aggregate check when the node is unavailable.

**Parameter rename.** `all_names` → `duplicate_names` in
`judge_function()` for clarity; callers already passed the duplicate-name
set.

**Test coverage.** Added `test_normalizer.py` (19 tests),
`test_node_index.py` (~20 tests) covering per-type detection, depth
tracking, deep-nesting flags, and determinism. Added `DO_WHILE_I` and
`GOTO_I` fixtures to `conftest.py`.
