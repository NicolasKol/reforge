# Reforge Synthetic Data Storage Guide

## Overview

This guide explains how to organize and store synthetic C/C++ programs for building a high-quality testing corpus for reverse engineering and LLM evaluation.

## Storage Philosophy

### Three-Variant System

Each source file is compiled into **three variants** at each optimization level:

1. **debug** - Full debug symbols (`-g -g3`, not stripped)
   - **Purpose**: Ground truth for evaluation
   - **Contains**: Function names, variable names, type information, line numbers
   - **Use**: Extract correct answers for LLM evaluation metrics

2. **release** - Standard debug symbols (`-g`, not stripped)
   - **Purpose**: Intermediate reference point
   - **Contains**: Standard debug info without DWARF extensions
   - **Use**: Compare optimization effects while preserving provenance

3. **stripped** - No debug symbols (`strip --strip-all`)
   - **Purpose**: The actual challenge for the LLM
   - **Contains**: Only machine code, no symbol tables
   - **Use**: What you feed to Ghidra → LLM for analysis

### Why This Matters

- **Ground Truth**: The debug variant lets you know what *should* be found
- **Evaluation**: Compare LLM output against debug symbols to measure accuracy
- **Realistic Testing**: Stripped binaries mirror real-world reverse engineering scenarios

## Directory Structure

```
/files/artifacts/synthetic/
├── fibonacci_recursive/          # Test case name
│   ├── manifest.json             # Metadata about all builds
│   ├── gcc_O0/                   # Compiler + optimization
│   │   ├── debug                 # Ground truth binary
│   │   ├── release               # Standard optimized
│   │   └── stripped              # Challenge binary
│   ├── gcc_O2/
│   │   ├── debug
│   │   ├── release
│   │   └── stripped
│   └── gcc_O3/
│       ├── debug
│       ├── release
│       └── stripped
├── bubble_sort_array/
│   └── ... (same structure)
└── linked_list_reverse/
    └── ... (same structure)
```

## Naming Conventions

### Test Case Names

Use descriptive, lowercase, underscore-separated names that indicate functionality:

**Good:**
- `fibonacci_recursive`
- `bubble_sort_array`
- `linked_list_reverse`
- `binary_search_tree`
- `quicksort_partition`
- `string_palindrome_check`

**Bad:**
- `test1`
- `program`
- `fibonacci` (ambiguous - iterative or recursive?)
- `sort` (which algorithm?)

### Category Organization

Align with the C-Programs repository structure:

| Category | Examples |
|----------|----------|
| `arrays` | Sorting, searching, matrix operations |
| `loops` | For/while/do-while patterns, nested loops |
| `strings` | String manipulation, parsing, formatting |
| `functions` | Function calls, parameter passing, recursion |
| `pointers` | Pointer arithmetic, dereferencing, arrays via pointers |
| `structures` | Struct definitions, nested structs, linked data |
| `conditionals` | If/else chains, switch statements, ternary operators |
| `file_handling` | File I/O, reading/writing, buffering |
| `operators` | Bitwise ops, arithmetic, logical operators |
| `input_output` | scanf/printf, formatted I/O |

## Database Schema Mapping

### synthetic_code Table

```sql
INSERT INTO synthetic_code (
    name,                    -- 'fibonacci_recursive'
    source_code,             -- Full C/C++ source text
    source_hash,             -- SHA256 of source_code
    language,                -- 'c' or 'cpp'
    test_category,           -- 'functions' (for recursion)
    ground_truth             -- JSONB with known-good analysis
) VALUES (...);
```

### binaries Table

For each variant (debug/release/stripped) at each optimization level:

```sql
INSERT INTO binaries (
    synthetic_code_id,       -- FK to synthetic_code
    file_path,               -- '/files/artifacts/synthetic/fibonacci_recursive/gcc_O0/debug'
    file_hash,               -- SHA256 of binary file
    file_size,               -- Bytes
    compiler,                -- 'gcc' or 'clang'
    optimization_level,      -- 'O0', 'O2', 'O3'
    has_debug_info,          -- TRUE for debug/release, FALSE for stripped
    is_stripped,             -- FALSE for debug/release, TRUE for stripped
    variant_type             -- 'debug', 'release', or 'stripped'
) VALUES (...);
```

## Ground Truth Storage

The `ground_truth` JSONB field stores known-correct information for evaluation:

```json
{
  "functions": [
    {
      "name": "fibonacci",
      "return_type": "int",
      "parameters": [
        {"name": "n", "type": "int"}
      ],
      "local_variables": [],
      "calls": ["fibonacci"]  // recursive
    },
    {
      "name": "main",
      "return_type": "int",
      "parameters": [],
      "local_variables": [
        {"name": "n", "type": "int"},
        {"name": "result", "type": "int"}
      ],
      "calls": ["fibonacci", "printf"]
    }
  ],
  "complexity": "simple",
  "features": ["recursion", "base_case", "arithmetic"]
}
```

This allows automated evaluation:
1. Extract function names from stripped binary using LLM
2. Compare against `ground_truth.functions[].name`
3. Calculate precision, recall, F1 score

## Corpus Quality Guidelines

### Program Size

- **Ideal**: 10-50 lines of code
- **Maximum**: 100 lines
- **Minimum**: 5 lines (needs to be non-trivial)

**Why?** Small programs are easier to verify manually and provide focused test cases for specific features.

### Program Complexity

Start simple, increase gradually:

1. **Simple** (10-20 lines)
   - Single function
   - One control structure (loop OR conditional)
   - Basic data types (int, char, float)
   - Example: Linear search in array

2. **Medium** (20-50 lines)
   - 2-3 functions
   - Multiple control structures
   - Arrays or simple structs
   - Example: Bubble sort with swap function

3. **Complex** (50-100 lines)
   - 4+ functions
   - Recursion or nested loops
   - Pointers, linked structures
   - Example: Binary search tree insertion/traversal

### Diversity

Ensure corpus covers:

- **Control Flow**: loops, conditionals, recursion, gotos
- **Data Structures**: arrays, structs, unions, pointers
- **Operations**: arithmetic, bitwise, logical, comparisons
- **Functions**: calls, returns, parameters, recursion
- **Memory**: stack variables, heap (malloc/free), static

## Optimization Level Strategy

### Core Set (Always Build)

- **O0**: No optimization, maximum debug info, closest to source
- **O2**: Standard optimization, real-world release builds
- **O3**: Aggressive optimization, hardest for analysis

### Extended Set (Optional)

- **O1**: Light optimization
- **Os**: Size optimization (embedded systems)

### Rationale

- **O0** is easiest - test if LLM can handle basic reverse engineering
- **O2** is realistic - most software ships with this
- **O3** is challenging - inlining, loop unrolling, dead code elimination
- Testing across levels measures LLM robustness to compiler transformations

## Manifest Files

Each test case gets a `manifest.json`:

```json
{
  "name": "fibonacci_recursive",
  "test_category": "functions",
  "language": "c",
  "source_code": "#include <stdio.h>\n...",
  "artifacts": [
    {
      "compiler": "gcc",
      "optimization": "O0",
      "variant": "debug",
      "binary_path": "/files/artifacts/synthetic/fibonacci_recursive/gcc_O0/debug",
      "source_hash": "abc123...",
      "file_size": 16384,
      "has_debug_info": true,
      "is_stripped": false,
      "compile_flags": "-std=c11 -O0 -g -g3 -fno-omit-frame-pointer"
    },
    // ... more artifacts
  ],
  "errors": [],
  "success_count": 9,
  "error_count": 0
}
```

## Recommended Workflow

### 1. Source Preparation

```powershell
# Clone test repository
git clone https://github.com/Ruban2205/C-Programs.git

# Organize by category
cd C-Programs
ls 01_Input_and_output/
ls 02_Operators/
# etc.
```

### 2. Batch Submission

Create `load_corpus.py`:

```python
import os
import requests
from pathlib import Path

API_URL = "http://localhost:8080/builder/synthetic"

def submit_program(name, source_code, category):
    payload = {
        "name": name,
        "source_code": source_code,
        "test_category": category,
        "language": "c",
        "compilers": ["gcc"],
        "optimizations": ["O0", "O2", "O3"]
    }
    response = requests.post(API_URL, json=payload)
    return response.json()

# Process directory
category = "arrays"
source_dir = Path("C-Programs/05_Arrays")

for c_file in source_dir.glob("*.c"):
    name = c_file.stem  # filename without .c
    source_code = c_file.read_text()
    
    print(f"Submitting {name}...")
    result = submit_program(name, source_code, category)
    print(f"  Job ID: {result['job_id']}")
```

### 3. Verification

After builds complete:

```sql
-- Count by category
SELECT test_category, COUNT(*) 
FROM synthetic_code 
GROUP BY test_category;

-- Verify all variants exist
SELECT 
    sc.name,
    COUNT(CASE WHEN b.variant_type = 'debug' THEN 1 END) as debug_count,
    COUNT(CASE WHEN b.variant_type = 'release' THEN 1 END) as release_count,
    COUNT(CASE WHEN b.variant_type = 'stripped' THEN 1 END) as stripped_count
FROM synthetic_code sc
LEFT JOIN binaries b ON sc.id = b.synthetic_code_id
GROUP BY sc.name
HAVING 
    COUNT(CASE WHEN b.variant_type = 'debug' THEN 1 END) != 
    COUNT(CASE WHEN b.variant_type = 'stripped' THEN 1 END);
-- Returns programs with missing variants
```

### 4. Ground Truth Extraction

```powershell
# Extract function names from debug binary
docker exec reforge-builder-worker readelf -s /files/artifacts/synthetic/fibonacci_recursive/gcc_O0/debug | grep FUNC

# Extract DWARF debug info
docker exec reforge-builder-worker readelf -wi /files/artifacts/synthetic/fibonacci_recursive/gcc_O0/debug

# Save to ground_truth field
```

```sql
UPDATE synthetic_code 
SET ground_truth = '{
    "functions": [
        {"name": "fibonacci", "type": "int", "params": ["int n"]},
        {"name": "main", "type": "int", "params": []}
    ]
}'::jsonb
WHERE name = 'fibonacci_recursive';
```

## Corpus Metrics

Track corpus quality:

```sql
-- Total programs
SELECT COUNT(*) FROM synthetic_code;

-- Programs per category
SELECT test_category, COUNT(*) 
FROM synthetic_code 
GROUP BY test_category 
ORDER BY COUNT(*) DESC;

-- Total binaries
SELECT COUNT(*) FROM binaries WHERE synthetic_code_id IS NOT NULL;

-- Storage used
SELECT 
    pg_size_pretty(SUM(file_size)) as total_size,
    COUNT(*) as binary_count
FROM binaries 
WHERE synthetic_code_id IS NOT NULL;

-- Average binaries per program
SELECT AVG(binary_count) FROM (
    SELECT COUNT(*) as binary_count 
    FROM binaries 
    GROUP BY synthetic_code_id
) sub;
```

## Backup and Export

### Export Corpus

```powershell
# Export source code
docker exec reforge-postgres psql -U reforge -d reforge -c "
COPY (SELECT name, source_code, test_category FROM synthetic_code) 
TO STDOUT CSV HEADER
" > corpus_source.csv

# Export metadata
docker exec reforge-postgres psql -U reforge -d reforge -c "
COPY (
    SELECT 
        sc.name,
        b.compiler,
        b.optimization_level,
        b.variant_type,
        b.file_size,
        b.has_debug_info,
        b.is_stripped
    FROM synthetic_code sc
    JOIN binaries b ON sc.id = b.synthetic_code_id
) TO STDOUT CSV HEADER
" > corpus_binaries.csv
```

### Backup Artifacts

```powershell
# Archive all synthetic artifacts
docker exec reforge-builder-worker tar -czf /files/corpus_backup.tar.gz /files/artifacts/synthetic/

# Copy to host
docker cp reforge-builder-worker:/files/corpus_backup.tar.gz ./corpus_backup_$(Get-Date -Format yyyy-MM-dd).tar.gz
```

---

**Key Takeaways:**

1. **Always generate all three variants** - you need ground truth (debug) and challenge data (stripped)
2. **Organize by category** - makes corpus manageable and enables targeted testing
3. **Use descriptive names** - helps with manual verification and debugging
4. **Extract ground truth** - store known-correct information for automated evaluation
5. **Verify completeness** - ensure all expected binaries were created successfully
6. **Document provenance** - manifest.json + database = full traceability

This systematic approach ensures a high-quality testing corpus for reproducible reverse engineering research.
