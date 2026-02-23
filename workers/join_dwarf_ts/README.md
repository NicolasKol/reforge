# join_dwarf_ts

Aligns DWARF oracle function inventory with tree-sitter source structure using GCC preprocessor line directives as the bridge.

## Purpose

Maps each ACCEPT/WARN function from `oracle_dwarf` to the best-matching function node from `oracle_ts` by parsing `#line` directives in preprocessed `.i` files. Produces alignment JSON with overlap scores, ambiguity flags, and evidence counts.

## Usage

```python
from join_dwarf_ts.runner import run_join_dwarf_ts
from pathlib import Path

report, pairs = run_join_dwarf_ts(
    oracle_dwarf_dir=Path("output/oracle_dwarf"),
    oracle_ts_dir=Path("output/oracle_ts"),
    i_paths=[Path("main.i"), Path("utils.i")],
    output_dir=Path("output/join_dwarf_ts"),
)
```

## Outputs

- `alignment_report.json` — Summary statistics and verdicts
- `alignment_pairs.json` — Per-function alignments with scores and evidence

## Scope

See [LOCK.md](LOCK.md) for guarantees, thresholds, and non-goals.
