# oracle_dwarf

DWARF-based alignment oracle for ELF binaries.

## What it does

Reads debug-variant ELF binaries (compiled with `gcc -g`), extracts function-level alignment targets from DWARF metadata, and emits structured verdicts (`ACCEPT`/`WARN`/`REJECT`) with reasons.

See [LOCK.md](LOCK.md) for the v0 scope contract.

## Running via the central API

The oracle is integrated as a router in the main reforge API:

```bash
# From docker/
docker compose up api
```

The oracle endpoint is available at:

```
POST http://localhost:8080/oracle/run
Content-Type: application/json

{
  "optimization_level": "O0"
}
```

This scans all debug-variant binaries at the specified optimization level under `/files/artifacts/synthetic/` and returns per-binary verdicts with function counts.

API docs at: `http://localhost:8080/docs`

## Running tests

**Requirements**: Linux environment with GCC (tests require ELF binaries with DWARF debug info)

### Using Docker (recommended):

```bash
cd workers/oracle_dwarf
docker build -t oracle-dwarf-test .
docker run --rm oracle-dwarf-test
```

### On Linux:

```bash
cd workers/oracle_dwarf
pip install -r requirements.txt
pytest tests/ -v
```

Tests compile small C programs on-the-fly with `gcc` and verify invariant properties (valid ranges, non-empty line spans, correct verdicts). 

**Note**: Native Windows is not supported because the oracle requires ELF binaries with DWARF debug info. Windows gcc (MinGW/MSYS2) produces PE executables. Tests will skip automatically with instructions to use Docker.

