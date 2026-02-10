# Reforge Quick Reference

## Docker Operations

Start/stop stack:
```powershell
cd docker
docker compose up -d
docker compose down
```

Rebuild after code changes:
```powershell
docker compose build api builder-worker
docker compose up -d
```

Execute commands in containers:
```powershell
docker exec -it reforge-postgres psql -U reforge_user -d reforge
docker exec -it reforge-redis redis-cli
docker exec -it reforge-builder-worker bash
```

## PostgreSQL Quick Access

Connect:
```powershell
docker exec -it reforge-postgres psql -U reforge_user -d reforge
```

Inside psql:
```sql
SET search_path TO reforge, public;
```

## Database Schema (builder_synth_v1)

Two tables:
- **synthetic_code**: Test programs (name, snapshot_sha256, file_count, source_files)
- **binaries**: Compiled artifacts (file_path, file_hash, optimization_level, variant_type)

Build matrix: 4 optimizations (O0/O1/O2/O3) x 3 variants (debug/release/stripped) = 12 cells per project

## Essential Queries

List all projects:
```sql
SELECT name, test_category, file_count, status, created_at 
FROM synthetic_code 
ORDER BY name;
```

Count binaries by variant:
```sql
SELECT variant_type, optimization_level, COUNT(*) 
FROM binaries 
GROUP BY variant_type, optimization_level 
ORDER BY optimization_level, variant_type;
```

Get all binaries for a project:
```sql
SELECT 
    sc.name,
    b.optimization_level,
    b.variant_type,
    b.file_size,
    b.file_path
FROM synthetic_code sc
JOIN binaries b ON sc.id = b.synthetic_code_id
WHERE sc.name = 't01_crossfile_calls'
ORDER BY b.optimization_level, b.variant_type;
```

Find incomplete builds:
```sql
SELECT 
    sc.name,
    COUNT(b.id) as binary_count
FROM synthetic_code sc
LEFT JOIN binaries b ON sc.id = b.synthetic_code_id
GROUP BY sc.id, sc.name
HAVING COUNT(b.id) < 12
ORDER BY binary_count;
```

## Reset Database

Nuke all reforge data (preserves n8n):
```powershell
Get-Content db/postgres/nuke_reforge.sql | docker exec -i reforge-postgres psql -U reforge_user -d reforge
```

Rebuild schema:
```powershell
Get-Content db/postgres/provenance.sql | docker exec -i reforge-postgres psql -U reforge_user -d reforge
```

## Redis Queue

Check queue:
```redis
LLEN builder:queue
LRANGE builder:queue 0 -1
DEL builder:queue
```

## Artifact Inspection

View artifacts:
```powershell
docker exec reforge-builder-worker ls -la /files/artifacts/synthetic/t01_crossfile_calls/
docker exec reforge-builder-worker cat /files/artifacts/synthetic/t01_crossfile_calls/manifest.json | jq .
```

Verify debug symbols:
```powershell
docker exec reforge-builder-worker readelf -S /files/artifacts/synthetic/t01_crossfile_calls/gcc_O0_debug | grep debug
docker exec reforge-builder-worker readelf -S /files/artifacts/synthetic/t01_crossfile_calls/gcc_O0_stripped | grep debug
```

---

**Focus**: builder_synth_v1 provenance tracking
