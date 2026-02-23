# app

FastAPI orchestration layer providing HTTP interfaces to all pipeline workers.

## Purpose

Exposes unified REST endpoints for building, decompiling, joining, and analyzing binaries. Routes requests to domain-specific workers and coordinates workflow execution with n8n.

## Running

```bash
cd app
uvicorn main:app --reload --host 0.0.0.0 --port 8080
```

Or via Docker Compose:

```bash
cd docker
docker compose up -d
```

API documentation available at `http://localhost:8080/docs`.

## Routers

| Router | Workers/Functions |
|--------|-------------------|
| `builder.py` | Builder worker endpoints |
| `oracle.py` | Oracle DWARF endpoints |
| `oracle_ts.py` | Oracle tree-sitter endpoints |
| `ghidra.py` | Ghidra decompiler endpoints |
| `join.py` | join_dwarf_ts endpoints |
| `join_ghidra.py` | join_oracles_to_ghidra_decompile endpoints |
| `llm.py` | LLM experiment execution |
| `llm_data.py` | LLM result storage and retrieval |
| `data.py` | Data loader and metrics |
| `results.py` | Results aggregation and export |

## Configuration

See `config.py` for environment-based settings.
