# oracle_ts — Tree-sitter Source Oracle

Deterministic source-structure oracle that produces syntactic ground truth
from compiler-emitted preprocessed C translation units (`.i`).

## Usage

### As a library (embedded in API)

```python
from oracle_ts.runner import run_oracle_ts
from pathlib import Path

report, functions, recipes = run_oracle_ts(
    i_paths=[Path("main.i"), Path("utils.i")],
    output_dir=Path("output/"),
)
```

### As a CLI

```bash
python -m oracle_ts.runner main.i utils.i -o output/ -v
```

### Run tests

```bash
pytest oracle_ts/tests/ -v
```

## Scope

See [LOCK.md](LOCK.md) for the v0 scope contract, guarantees, and non-goals.

## Outputs

- `oracle_ts_report.json` — TU-level parse reports
- `oracle_ts_functions.json` — Per-function index with structural nodes
- `extraction_recipes.json` — Deterministic extraction recipes
