# Reforge

**Reverse Engineering Pipeline with Modular Architecture**

Clean, simplified build system for controlled reverse engineering experiments. FastAPI orchestration layer with separated worker domains (builder, ghidra, llm).

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  n8n Orchestration                                          │
│  (Workflows, Scheduling, Provenance)                        │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  Reforge API (FastAPI) - http://localhost:8080              │
│  ├── /builder  → Build C/C++ projects                       │
│  ├── /ghidra   → Decompile binaries                         │
│  └── /llm      → AI-powered analysis                        │
└────────────────┬────────────────────────────────────────────┘
                 │
        ┌────────┴────────┬────────────────┐
        ▼                 ▼                ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Builder      │  │ Ghidra       │  │ LLM          │
│ Worker       │  │ Worker       │  │ Worker       │
│ (GCC/Clang)  │  │ (Headless)   │  │ (GPT/Claude) │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                 │
       └─────────────────┴─────────────────┘
                         │
                ┌────────┴─────────┐
                ▼                  ▼
        ┌──────────────┐   ┌──────────────┐
        │ PostgreSQL   │   │ Redis Queue  │
        │ (Provenance) │   │ (Job Queue)  │
        └──────────────┘   └──────────────┘
```

## Directory Structure

```
reforge/
├── app/                      # FastAPI application (orchestration layer)
│   ├── main.py              # Main app with router registration
│   ├── config.py            # Centralized configuration
│   └── routers/             # Domain-separated endpoints
│       ├── builder.py       # Build job submission/status
│       ├── ghidra.py        # Decompilation endpoints (placeholder)
│       └── llm.py           # AI analysis endpoints (placeholder)
│
├── workers/                  # Heavy lifting workers
│   ├── builder/             # C/C++ build worker (IMPLEMENTED)
│   │   ├── build_logic.py   # Core build implementation
│   │   └── worker.py        # Redis consumer (placeholder)
│   ├── ghidra/              # Ghidra decompilation (TODO)
│   └── llm/                 # LLM-based analysis (TODO)
│
├── db/postgres/             # Database schemas
│   ├── init.sql
│   └── provenance.sql       # build_jobs, binaries, functions, llm_interactions
│
└── docker/                   # Deployment
    ├── docker-compose.yml
    └── local-files/         # Mounted artifacts
```

## Services

| Service | Port | Purpose |
|---------|------|---------|
| **reforge-api** | 8080 | Unified HTTP interface for n8n |
| **builder-worker** | - | Builds C/C++ projects (GCC 11, Clang 14) |
| **n8n** | 5678 | Workflow orchestration |
| **postgres** | 5432 | Provenance tracking |
| **redis** | 6379 | Job queue |

## Quick Start

```bash
cd docker

# Start services
docker compose up -d

# Check API health
curl http://localhost:8080/health

# View API documentation
open http://localhost:8080/docs

# Submit build job
curl -X POST http://localhost:8080/builder/build \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/DaveGamble/cJSON",
    "commit_ref": "master",
    "compiler": "gcc",
    "optimizations": ["O0", "O2", "O3"]
  }'
```

## Current Status

**✅ Implemented:**
- Clean separation: API layer (app/) ↔ Workers (workers/)
- Modular routers for builder, ghidra, llm domains
- Builder worker with comprehensive build logic (clone, detect, compile, discover binaries)
- Database schema for provenance tracking (build_jobs, synthetic_code, binaries)
- Docker Compose orchestration

**⏳ TODO (Placeholders exist):**
- Redis queue integration for builder worker
- PostgreSQL client for job/artifact tracking
- Artifact storage to local filesystem
- Ghidra worker implementation
- LLM worker implementation

## Database Schema

Key tables in the `reforge` schema:

- **`build_jobs`** - Git build tracking (repo, commit, compiler, optimizations, status)
- **`synthetic_code`** - Hand-crafted test cases with ground truth
- **`binaries`** - Build artifacts with provenance (linked to build_jobs OR synthetic_code)
- **`functions`** - Extracted functions with decompiled code
- **`llm_interactions`** - Full provenance of every LLM call
- **`decompilation_results`** - Generated code with validation status
- **`experiments`** - Experiment runs with aggregated metrics


## Documentation

- [Orchestration Design](../docs/Orchestration_reverse_engineering_LLM.md) - Architecture rationale
- [n8n Docker Cheatsheet](../docs/cheatsheets/n8n-docker.md) - Quick reference

## License

[TBD]

## Acknowledgments

Part of thesis research on LLM-assisted binary analysis.
