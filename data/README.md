# data

Evaluation schemas, metrics, and reproducible analysis notebooks for pipeline outputs.

## Purpose

Provides read-only Pydantic models for deserializing oracle artifacts, scoring functions for LLM predictions, and a suite of Jupyter notebooks that quantify pipeline behavior across multiple dimensions.

## Notebooks

| Notebook | Purpose |
|----------|---------|
| `PIPELINE_candidate_ambiguity.ipynb` | Measures alignment ambiguity (1:1, 1:N mappings) |
| `PIPELINE_counts.ipynb` | Function counts and verdict distributions across optimization levels |
| `PIPELINE_data_quality.ipynb` | Data completeness, missing fields, schema validation |
| `PIPELINE_decompiler_quality.ipynb` | Ghidra output quality metrics and proxy indicators |
| `PIPELINE_ghidra_yield.ipynb` | Decompiler yield (functions recovered vs expected) |
| `PIPELINE_opt_induced_uncertainty.ipynb` | Examines how optimization level affects ambiguity and verdict stability |
| `PIPELINE_transitions.ipynb` | Verdict transitions across build variants |

## Modules

- `schema.py` — Lightweight Pydantic models for oracle outputs
- `loader.py` — Loads experiment data from filesystem or API
- `scoring.py` — Token-based precision/recall/F1 for function name predictions
- `metrics.py` — Aggregated metrics and summary statistics
- `reporting.py` — Report generation helpers
- `binning.py` — Binning and grouping utilities
- `enums.py` — Shared enumerations
- `experiments.py` — Experiment configuration helpers
- `noise_lists.py` — Known noise patterns and exclusion lists
- `paths.py` — Path resolution utilities

## Usage

```python
from data.loader import load_experiment
from data.scoring import score_experiment

exp = load_experiment("exp01_funcnaming_gpt4omini_gold_O0")
scored = score_experiment(exp.rows)
```
