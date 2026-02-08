# Reforge Builder Worker

Heavy lifting worker for building Linux C/C++ projects. Consumes jobs from Redis queue.

## Features

- **Git clone** with submodule support
- **Build system detection**: CMake, Make, Autoconf, Bootstrap
- **Compiler support**: GCC 11, Clang 14
- **Optimization levels**: O0, O1, O2, O3
- **Debug symbols**: Configurable debug info and frame pointers
- **Binary discovery**: Automatic ELF executable detection
- **Provenance tracking**: SHA256 hashes, debug section analysis, build manifests

## Architecture

```
FastAPI (reforge/app/) → Redis Queue → BuildWorker (worker.py)
                                              ↓
                                    BuildJob (build_logic.py)
                                              ↓
                                    Local Filesystem (/files/artifacts)
                                              ↓
                                    PostgreSQL (build_jobs, binaries tables)
```

## Current Status

**Implemented:**
- ✅ Core build logic (`build_logic.py`)
- ✅ Build system detection
- ✅ Compiler flag injection
- ✅ Binary discovery and filtering
- ✅ Debug info verification
- ✅ Manifest generation
- ✅ Worker scaffold (`worker.py`)

**TODO (Placeholders only):**
- ⏳ Redis queue consumption (scaffold exists)
- ⏳ PostgreSQL integration (update job status, insert binaries)
- ⏳ Artifact storage to local filesystem
- ⏳ Full build execution pipeline

## Usage (When Implemented)

Submit jobs via the main API (not this worker directly):

```bash
# Submit build job (via reforge API)
curl -X POST http://localhost:8080/builder/build \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/DaveGamble/cJSON",
    "commit_ref": "master",
    "compiler": "gcc",
    "optimizations": ["O0", "O2", "O3"]
  }'

# Worker picks up job from Redis and builds
```

## Development

```bash
# Build Docker image
docker build -t reforge-builder .

# Run locally (for testing build logic)
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
python main.py
```

## Compiler Versions

- **GCC**: 11.4.0
- **Clang**: 14.0.0

Pinned for reproducibility in experiments.
