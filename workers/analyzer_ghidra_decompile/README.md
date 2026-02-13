# analyzer_ghidra_decompile

Deterministic, provenance-rich extraction of Ghidra's decompiler view for
stripped ELF binaries.

## Architecture

Two-tier pipeline:

1. **Java script** (`ExportDecompJsonl.java`) — runs inside Ghidra headless,
   exports rich raw JSONL with functions, variables, CFG, and callsites.
2. **Python worker** (this package) — parses raw JSONL, applies schema
   validation, policy verdicts, noise classification, and proxy metrics.



## Outputs (per binary)

| File | Content |
|------|---------|
| `report.json` | Binary-level verdict, provenance, summary stats |
| `functions.jsonl` | One line per function (sorted by entry_va) |
| `variables.jsonl` | One line per decompiler-visible variable (sorted) |
| `cfg.jsonl` | One line per function CFG (sorted by entry_va) |
| `calls.jsonl` | One line per callsite (sorted) |

## Usage

Copy script to local files mount
```bash
cp ghidra_scripts/ExportDecompJsonl.java docker/local-files/ghidra/scripts/
```

```python
from analyzer_ghidra_decompile.runner import run_ghidra_decompile
from pathlib import Path

report, funcs, vars, cfg, calls = run_ghidra_decompile(
    binary_path="/files/artifacts/synthetic/t01/O0/stripped/bin/t01",
    output_dir=Path("/files/artifacts/synthetic/t01/O0/stripped/ghidra_decompile"),
)
```

## Running tests

```bash
pytest tests/ -v
```

## See also

- `LOCK.md` — v1 scope contract
- `../../ghidra_scripts/ExportDecompJsonl.java` — Ghidra Java script

