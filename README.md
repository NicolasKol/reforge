# Reforge

A modular pipeline for controlled reverse engineering experiments. Reforge compiles synthetic C programs into ELF binaries under a defined build matrix, extracts DWARF-based ground truth, decompiles stripped variants, and evaluates LLM-generated source recovery against that ground truth.

## Overview

The system is composed of domain-specific workers coordinated through a FastAPI orchestration layer, with n8n providing workflow automation:

| Component | Role |
|-----------|------|
| **API** (`app/`) | HTTP interface; routes requests to workers |
| **Builder** (`workers/builder/`) | Compiles C source to ELF across optimization levels and variants (debug, release, stripped) |
| **Oracle TS** (`workers/oracle_ts/`) | Parses preprocessed C translation units with tree-sitter; indexes functions and structural nodes with stable identifiers |
| **Oracle DWARF** (`workers/oracle_dwarf/`) | Extracts function boundaries, line mappings, and per-function verdicts from debug DWARF info |
| **Ghidra** (`workers/ghidra/`) | Headless decompilation of stripped binaries |
| **LLM** (`workers/llm/`) | LLM-assisted source recovery and analysis |
| **Join Oracle** (`workers/oracle_align/`) | Joins the syntactic (`oracle_ts`) and binary (`oracle_dwarf`) oracles to surface alignment mismatches and provenance discrepancies |
| **Data Module** (`data/`) | Bundles evaluation schemas, metrics helpers, and reproducible notebooks that quantify ambiguity, counts, quality, uncertainty, and transition behavior |

Infrastructure: PostgreSQL (provenance), Redis (job queue), n8n (orchestration).

## Quick Start

```bash
cd docker
docker compose up -d
curl http://localhost:8080/health
```

API documentation is available at `http://localhost:8080/docs`.

## Evaluation Notebooks

The data module drives a series of notebooks — `candidate_ambiguity`, `counts`, `data_quality`, `opt_induced_uncertainty`, and `transitions` — that walk through evaluator-friendly metrics for ambiguity, match counts, key stability, optimization-induced uncertainty, and transition behavior between verdicts.

## Scope and Contracts

Each worker defines its own scope lock (`LOCK.md`) specifying supported inputs, outputs, non-goals, and extension points. Refer to those files and per-worker READMEs for implementation details.

## License

TBD

## Acknowledgements

Part of thesis research on LLM-assisted binary analysis.
