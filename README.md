# Reforge

A modular pipeline for controlled reverse engineering experiments. Reforge compiles synthetic C programs into ELF binaries under a defined build matrix, extracts DWARF-based ground truth, decompiles stripped variants, and evaluates LLM-generated source recovery against that ground truth.

## Overview

The system is composed of domain-specific workers coordinated through a FastAPI orchestration layer:

| Component | Role |
|-----------|------|
| **API** (`app/`) | HTTP interface; routes requests to workers |
| **Builder** (`workers/builder/`) | Compiles C source to ELF across optimization levels and variants (debug, release, stripped) |
| **Oracle TS** (`workers/oracle_ts/`) | Parses preprocessed C translation units with tree-sitter; indexes functions and structural nodes |
| **Oracle DWARF** (`workers/oracle_dwarf/`) | Extracts function boundaries, line mappings, and per-function verdicts from debug DWARF info |
| **Join DWARF-TS** (`workers/join_dwarf_ts/`) | Aligns DWARF and tree-sitter function inventories using GCC line directives |
| **Analyzer Ghidra Decompile** (`workers/analyzer_ghidra_decompile/`) | Headless decompilation of stripped binaries; extracts CFG, calls, variables, and function metadata |
| **Join Oracles to Ghidra** (`workers/join_oracles_to_ghidra_decompile/`) | Merges oracle outputs with Ghidra decompilation to construct experiment substrate |
| **LLM** (`workers/llm/`) | Async experiment runner for LLM-assisted function naming and source recovery |
| **Data Module** (`data/`) | Evaluation schemas, scoring functions, and reproducible analysis notebooks |


## Quick Start

```bash
cd docker
docker compose up -d
curl http://localhost:8080/health
```

API documentation is available at `http://localhost:8080/docs`.

## Structure

- `app/` — FastAPI orchestration layer ([README](app/README.md))
- `workers/` — Domain-specific processing workers (each with README and LOCK.md)
- `data/` — Evaluation module with notebooks ([README](data/README.md))
- `C-Programs/` — Synthetic test programs ([README](C-Programs/README.md))
- `scripts/` — Notebooks to help run the pipeline and Experimental notebooks ([README](scripts/README.md))
- `docker/` — Docker Compose configuration

## Evaluation Notebooks

The `data/results/` directory contains reproducible pipeline evaluation notebooks:

- **PIPELINE_candidate_ambiguity** — Alignment ambiguity 
- **PIPELINE_counts** — Function counts and verdict distributions
- **PIPELINE_data_quality** — Data completeness and schema validation
- **PIPELINE_decompiler_quality** — Ghidra output quality metrics
- **PIPELINE_ghidra_yield** — Decompiler yield analysis
- **PIPELINE_opt_induced_uncertainty** — Optimization effects on ambiguity and stability
- **PIPELINE_transitions** — Verdict transitions across build variants

Test notebooks to investigate join criteria: `data/results/join_health`


Notebook with selected Thesis Figures: `data/results/THESIS_FINAL`


See [data/README.md](data/README.md) for details.

## Scope and Contracts

Each worker defines its own scope lock (`LOCK.md`) specifying supported inputs, outputs, non-goals, and extension points. Refer to those files and per-worker READMEs for implementation details.

## License

TBD

## Acknowledgements

Part of thesis research on LLM-assisted binary analysis.
