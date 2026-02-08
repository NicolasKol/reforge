# oracle_dwarf

DWARF-based alignment oracle for ELF binaries.

## What it does

Reads debug-variant ELF binaries (compiled with `gcc -g`), extracts function-level alignment targets from DWARF metadata, and emits structured verdicts (`ACCEPT`/`WARN`/`REJECT`) with reasons.

See [LOCK.md](LOCK.md) for the v0 scope contract.

## Running as a service

```bash
# From docker/
docker compose up oracle-dwarf
```

The service exposes a single endpoint:

```
POST http://localhost:8081/oracle/run
Content-Type: application/json

{
  "optimization_level": "O0"
}
```

This scans all debug-variant binaries at the specified optimization level under `/files/artifacts/synthetic/` and returns per-binary verdicts with function counts.

API docs at: `http://localhost:8081/docs`

## Running tests

```bash
cd workers/oracle_dwarf
pip install -r requirements.txt
pytest tests/ -v
```

Tests compile small C programs on-the-fly with `gcc` and verify invariant properties (valid ranges, non-empty line spans, correct verdicts).

## Package structure

```
oracle_dwarf/
├── __init__.py          # Version constants
├── runner.py            # Top-level orchestration
├── LOCK.md              # v0 scope contract
├── core/
│   ├── elf_reader.py    # ELF validation + metadata
│   ├── dwarf_loader.py  # DWARFInfo + CU iteration
│   ├── function_index.py # Subprogram DIE enumeration + range normalization
│   └── line_mapper.py   # .debug_line intersection + dominant file
├── policy/
│   ├── profile.py       # Support profile descriptor
│   └── verdict.py       # ACCEPT/WARN/REJECT logic
├── io/
│   ├── schema.py        # Pydantic output models
│   └── writer.py        # JSON serialization
├── api/
│   ├── app.py           # Standalone FastAPI app
│   └── router.py        # /oracle/run endpoint
└── tests/
    ├── conftest.py       # gcc fixture compilation
    ├── test_gate.py      # Binary-level gate tests
    ├── test_functions.py # Function enumeration invariants
    └── test_linespan.py  # Line span invariants
```
