# join_oracles_to_ghidra_decompile

Constructs the experiment substrate by joining source-side oracles with Ghidra decompiler output.

## Purpose

Merges `oracle_dwarf`, `join_dwarf_ts` alignment results, and `analyzer_ghidra_decompile` outputs into a unified provenance-rich view. Surfaces function-level deltas (missing, merged, extra, aligned) and diagnostics for downstream LLM-assisted analysis.

## Usage

```python
from join_oracles_to_ghidra_decompile.runner import run_join_oracles_ghidra
from pathlib import Path

report, joined = run_join_oracles_ghidra(
    oracle_dwarf_dir=Path("output/oracle_dwarf"),
    join_dwarf_ts_dir=Path("output/join_dwarf_ts"),
    ghidra_dir=Path("output/ghidra_decompile"),
    build_receipt_path=Path("build_receipt.json"),
    output_dir=Path("output/joined"),
)
```

## Outputs

- `joined_report.json` — Binary-level summary, verdicts, function delta counts
- `joined_functions.jsonl` — One line per function with oracle provenance, decompiler view, and alignment metadata

## Scope

See [LOCK.md](LOCK.md) for guarantees, delta classification, and non-goals.
