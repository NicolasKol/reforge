# Reforge Quick Reference

## System Status

Check all services:
```powershell
cd docker
docker compose ps
```

View logs:
```powershell
docker compose logs api --tail=50
docker compose logs builder-worker --tail=50
docker compose logs postgres --tail=20
docker compose logs redis --tail=20
```

Restart services:
```powershell
docker compose restart api
docker compose restart builder-worker
```

## Synthetic Data Build Pipeline (PRIORITY 1)

### Overview

The synthetic data pipeline compiles single C/C++ source files for testing purposes. It creates three variants for each optimization level:

- **debug**: Full debug symbols (ground truth for evaluation)
- **release**: Optimized with debug info (intermediate)
- **stripped**: Optimized and stripped (what LLM analyzes)

### API Usage

Submit a synthetic build:
```powershell
$headers = @{"Content-Type"="application/json"}
$body = @{
    name = "fibonacci_recursive"
    source_code = @"
#include <stdio.h>

int fibonacci(int n) {
    if (n <= 1) return n;
    return fibonacci(n-1) + fibonacci(n-2);
}

int main() {
    int n = 10;
    printf("Fibonacci(%d) = %d\n", n, fibonacci(n));
    return 0;
}
"@
    test_category = "recursion"
    language = "c"
    compilers = @("gcc")
    optimizations = @("O0", "O2", "O3")
} | ConvertTo-Json

Invoke-RestMethod -Method POST -Uri "http://localhost:8080/builder/synthetic" -Headers $headers -Body $body
```

Response:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "fibonacci_recursive",
  "status": "QUEUED",
  "message": "Synthetic build queued for fibonacci_recursive"
}
```

### Artifact Storage Structure

All synthetic builds are stored under `/files/artifacts/synthetic/`:

```
/files/artifacts/synthetic/
└── {name}/                          # e.g., fibonacci_recursive
    ├── manifest.json                # Build metadata
    ├── gcc_O0/
    │   ├── debug                    # Full debug symbols (GROUND TRUTH)
    │   ├── release                  # Optimized with debug
    │   └── stripped                 # Stripped for LLM analysis
    ├── gcc_O2/
    │   ├── debug
    │   ├── release
    │   └── stripped
    ├── gcc_O3/
    │   ├── debug
    │   ├── release
    │   └── stripped
    └── clang_O2/                    # If multiple compilers used
        ├── debug
        ├── release
        └── stripped
```

### Database Schema

**synthetic_code table:**
```sql
CREATE TABLE synthetic_code (
    id UUID PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,      -- Unique identifier
    source_code TEXT NOT NULL,              -- The C/C++ source
    source_hash VARCHAR(64) NOT NULL,       -- SHA256 of source
    language VARCHAR(50) DEFAULT 'c',       -- 'c' or 'cpp'
    test_category VARCHAR(100) NOT NULL,    -- Category for organization
    ground_truth JSONB DEFAULT '{}',        -- Known correct analysis
    created_at TIMESTAMP DEFAULT NOW()
);
```

**binaries table:**
```sql
CREATE TABLE binaries (
    id UUID PRIMARY KEY,
    file_path TEXT NOT NULL,                  -- Full path to binary
    file_hash VARCHAR(64) UNIQUE NOT NULL,    -- SHA256 of binary file
    file_size BIGINT,
    
    synthetic_code_id UUID REFERENCES synthetic_code(id),  -- Links to source
    
    compiler VARCHAR(50),                     -- gcc, clang
    optimization_level VARCHAR(10),           -- O0, O1, O2, O3, Os
    
    has_debug_info BOOLEAN DEFAULT FALSE,     -- True for debug/release
    is_stripped BOOLEAN DEFAULT FALSE,        -- True for stripped only
    variant_type VARCHAR(20),                 -- 'debug', 'release', 'stripped'
    
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Corpus Organization

Recommended categories for test programs (aligned with C-Programs repo):

1. **arrays** - Array manipulation, sorting, searching
2. **loops** - For/while/do-while patterns
3. **strings** - String operations, parsing
4. **functions** - Function calls, recursion
5. **pointers** - Pointer arithmetic, memory management
6. **structures** - Struct definitions and usage
7. **conditionals** - If/else/switch logic
8. **file_handling** - File I/O operations
9. **operators** - Bitwise, arithmetic operations
10. **input_output** - scanf/printf patterns

### Querying the Database

Connect to PostgreSQL:
```powershell
docker exec -it reforge-postgres psql -U reforge_user -d reforge
```

Set search path to reforge schema:
```sql
SET search_path TO reforge, public;
```

List all synthetic test cases:
```sql
SELECT name, test_category, language, created_at 
FROM reforge.synthetic_code 
ORDER BY test_category, name;
```

Count binaries per variant:
```sql
SELECT variant_type, COUNT(*) 
FROM reforge.binaries 
WHERE synthetic_code_id IS NOT NULL 
GROUP BY variant_type;
```

Get all artifacts for a specific test:
```sql
SELECT 
    sc.name,
    b.compiler,
    b.optimization_level,
    b.variant_type,
    b.has_debug_info,
    b.is_stripped,
    b.file_size
FROM reforge.synthetic_code sc
JOIN reforge.binaries b ON sc.id = b.synthetic_code_id
WHERE sc.name = 'fibonacci_recursive'
ORDER BY b.compiler, b.optimization_level, b.variant_type;
```

Find all debug variants (ground truth):
```sql
SELECT 
    sc.name,
    sc.test_category,
    b.compiler,
    b.optimization_level,
    b.file_path
FROM reforge.synthetic_code sc
JOIN reforge.binaries b ON sc.id = b.synthetic_code_id
WHERE b.variant_type = 'debug'
ORDER BY sc.test_category, sc.name;
```

Find all stripped variants (for LLM testing):
```sql
SELECT 
    sc.name,
    sc.test_category,
    b.compiler,
    b.optimization_level,
    b.file_path
FROM reforge.synthetic_code sc
JOIN reforge.binaries b ON sc.id = b.synthetic_code_id
WHERE b.variant_type = 'stripped'
ORDER BY sc.test_category, sc.name;
```

## Redis Queue Inspection

Connect to Redis CLI:
```powershell
docker exec -it reforge-redis redis-cli
```

Check queue length:
```redis
LLEN builder:queue
```

Peek at next job (without removing):
```redis
LRANGE builder:queue 0 0
```

View all queued jobs:
```redis
LRANGE builder:queue 0 -1
```

Clear queue:
```redis
DEL builder:queue
```

## Docker Container Management

Execute commands in containers:
```powershell
# API container
docker exec -it reforge-api bash

# Worker container
docker exec -it reforge-builder-worker bash

# Check if gcc/clang available
docker exec reforge-builder-worker gcc --version
docker exec reforge-builder-worker clang --version
```

Rebuild after code changes:
```powershell
# Rebuild API
docker compose build api
docker compose up -d api

# Rebuild worker
docker compose build builder-worker
docker compose up -d builder-worker
```

View container resource usage:
```powershell
docker stats reforge-api reforge-builder-worker reforge-postgres reforge-redis
```

## API Health Check

```powershell
Invoke-RestMethod http://localhost:8080/health
```

Response:
```json
{
  "status": "healthy",
  "service": "reforge-api",
  "version": "0.1.0"
}
```

## Filesystem Access

Check artifacts on host:
```powershell
ls C:\Users\nico_\Documents\UNI\Thesis\Source\reforge\docker\local-files\artifacts\synthetic
```

Inside container:
```powershell
docker exec reforge-builder-worker ls -la /files/artifacts/synthetic
docker exec reforge-builder-worker cat /files/artifacts/synthetic/fibonacci_recursive/manifest.json
```

## Testing Workflow

### 1. Submit Build Job
```powershell
# See API usage example above
$result = Invoke-RestMethod -Method POST -Uri "http://localhost:8080/builder/synthetic" -Headers $headers -Body $body
$jobId = $result.job_id
```

### 2. Monitor Worker Logs
```powershell
docker compose logs builder-worker -f
```

### 3. Check Database
```sql
-- Find your synthetic code
SELECT id, name, test_category FROM reforge.synthetic_code WHERE name = 'fibonacci_recursive';

-- Check generated binaries
SELECT compiler, optimization_level, variant_type, file_size, has_debug_info 
FROM reforge.binaries 
WHERE synthetic_code_id = '<id-from-above>';
```

### 4. Verify Artifacts
```powershell
docker exec reforge-builder-worker ls -lh /files/artifacts/synthetic/fibonacci_recursive/gcc_O0/
# Should show: debug, release, stripped
```

### 5. Verify Debug Symbols
```powershell
# Debug variant should have symbols
docker exec reforge-builder-worker readelf -S /files/artifacts/synthetic/fibonacci_recursive/gcc_O0/debug | grep debug

# Stripped variant should NOT
docker exec reforge-builder-worker readelf -S /files/artifacts/synthetic/fibonacci_recursive/gcc_O0/stripped | grep debug
```

## Common Issues

### Worker not processing jobs
```powershell
# Check worker is running
docker compose ps builder-worker

# Check logs for errors
docker compose logs builder-worker --tail=100

# Restart worker
docker compose restart builder-worker
```

### Database connection issues
```powershell
# Check PostgreSQL is healthy
docker compose ps postgres

# Test connection
docker exec -it reforge-postgres psql -U reforge_user -d reforge -c "SELECT version();"
```

### Redis connection issues
```powershell
# Check Redis is running
docker compose ps redis

# Test connection
docker exec -it reforge-redis redis-cli PING
# Should return: PONG
```

### Artifacts not appearing
```powershell
# Check mounted volume
docker volume inspect reforge-docker_shared-files

# Check permissions
docker exec reforge-builder-worker ls -la /files/artifacts/
```

## Next Steps for Implementation

### Completed ✅
- Synthetic build module (`synthetic_builder.py`)
- API endpoint (`POST /builder/synthetic`)
- Worker integration (handles both git and synthetic builds)
- Database schema (synthetic_code + binaries with variants)
- Artifact storage structure

### Ready for Testing ✅
1. Submit synthetic build via API
2. Worker compiles at multiple opt levels
3. Creates debug/release/stripped variants
4. Stores artifacts in organized structure
5. Inserts provenance to database

### Next Implementation Priorities 🔄

1. **Batch Loader Script**: Create Python script to load all C-Programs repo files
   - Read directory structure
   - Parse .c files
   - Bulk submit to API
   - Track results

2. **Git Build Pipeline**: Complete the git repository build workflow
   - Wire BuildJob from build_logic.py
   - Handle repository cloning
   - Detect build systems
   - Store multi-binary results

3. **Ghidra Worker**: Implement decompilation worker
   - Create Ghidra headless script
   - Process binaries → decompiled code
   - Store functions table
   - Extract P-code representations

4. **LLM Worker**: Implement analysis worker
   - Send decompiled code to LLM
   - Track prompts and responses
   - Store in llm_interactions table
   - Evaluate against ground truth

## Storage Best Practices

### For Testing Corpus
- Use descriptive names: `bubble_sort_array`, `recursive_factorial`, `linked_list_reverse`
- Match test_category to program functionality
- Keep programs simple and focused (10-50 lines ideal)
- Document ground_truth in database for evaluation

### For Debug vs Stripped
- **Always build debug first** - this is your source of truth
- Debug variant: Use for extracting correct function names, variable types
- Release variant: Intermediate reference (has symbols but optimized)
- Stripped variant: This is what the LLM sees (hardest challenge)

### Evaluation Strategy
1. Build synthetic program with debug symbols
2. Extract ground truth from debug binary (readelf, objdump, etc.)
3. Store ground truth in synthetic_code.ground_truth field
4. Give stripped binary to LLM for analysis
5. Compare LLM output against ground truth
6. Measure accuracy, compute metrics

## Example: Complete Workflow

```powershell
# 1. Submit a test case
$body = @{
    name = "array_sum"
    source_code = @"
#include <stdio.h>
int sum_array(int arr[], int size) {
    int total = 0;
    for(int i = 0; i < size; i++) {
        total += arr[i];
    }
    return total;
}
int main() {
    int numbers[] = {1,2,3,4,5};
    int result = sum_array(numbers, 5);
    printf("Sum: %d\n", result);
    return 0;
}
"@
    test_category = "arrays"
    language = "c"
    compilers = @("gcc")
    optimizations = @("O0", "O3")
} | ConvertTo-Json

$result = Invoke-RestMethod -Method POST -Uri "http://localhost:8080/builder/synthetic" `
    -Headers @{"Content-Type"="application/json"} -Body $body

# 2. Wait for build (watch logs)
docker compose logs builder-worker -f

# 3. Query results
docker exec -it reforge-postgres psql -U reforge_user -d reforge
```
```sql
SELECT b.compiler, b.optimization_level, b.variant_type, b.file_size, b.has_debug_info
FROM reforge.binaries b
JOIN reforge.synthetic_code sc ON b.synthetic_code_id = sc.id
WHERE sc.name = 'array_sum';
```

```powershell
# 4. Examine artifacts
docker exec reforge-builder-worker ls -lh /files/artifacts/synthetic/array_sum/

# 5. Verify debug symbols present in debug variant
docker exec reforge-builder-worker readelf -wi /files/artifacts/synthetic/array_sum/gcc_O0/debug | grep sum_array

# 6. Verify symbols absent in stripped variant
docker exec reforge-builder-worker nm /files/artifacts/synthetic/array_sum/gcc_O0/stripped
# Should show: "no symbols"

# 7. View manifest
docker exec reforge-builder-worker cat /files/artifacts/synthetic/array_sum/manifest.json | jq .
```

## API Reference

### POST /builder/synthetic
Submit synthetic C/C++ source for compilation.

**Request:**
```json
{
  "name": "test_name",
  "source_code": "int main() { return 0; }",
  "test_category": "simple",
  "language": "c",
  "compilers": ["gcc"],
  "optimizations": ["O0", "O2", "O3"]
}
```

**Response:**
```json
{
  "job_id": "uuid",
  "name": "test_name",
  "status": "QUEUED",
  "message": "Synthetic build queued for test_name"
}
```

### GET /health
Check API health.

**Response:**
```json
{
  "status": "healthy",
  "service": "reforge-api",
  "version": "0.1.0"
}
```

---

**Last Updated**: 2026-02-07
**System Version**: Reforge 0.1.0
**Focus**: Synthetic data build pipeline for testing corpus creation
