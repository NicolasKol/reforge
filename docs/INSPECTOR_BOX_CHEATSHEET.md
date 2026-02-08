# Inspector Box Cheatsheet
Purpose: **Manually inspect Assemblage artifacts (ELF/DWARF) inside Docker**, learn what the artifacts contain, and validate whether they are suitable for ground-truth alignment.

This is a **learning + validation tool**, not automation yet.

---

## 0. When to use this
Use the inspector box when you want to:
- Understand what debug info *actually* exists in artifacts
- Verify whether alignment is possible
- Manually inspect binaries before automating anything
- Debug MinIO access and artifact integrity

---

## 1. Inspector Box Setup 

### 1.1 Start it
```bash
docker compose up -d inspector-box
docker exec -it reforge-inspector-box bash
```

### 1.2 Install required tools inside container
```bash
apt update
apt install -y \
  curl ca-certificates \
  file \
  binutils \
  llvm \
  python3 python3-pip
```
Optional but recommended:
```bash
apt install -y less jq
```

---


## 3. Core Inspection Commands (MOST IMPORTANT)

### 3.1 Identify binary format
```bash
file ascii_engine
```

Expected:
- ELF 64-bit executable
- Not stripped (for debug build)

If this fails → artifact is invalid.

### 3.2 Check for DWARF debug sections (ground-truth oracle)
```bash
readelf -S ascii_engine | grep -E '\.debug|\.zdebug'
```

Expected (debug build):
- `.debug_info`
- `.debug_line`
- `.debug_abbrev`

If nothing appears → no embedded DWARF → cannot align.

### 3.3 Check for split debug info
```bash
readelf -S ascii_engine | grep gnu_debuglink
```

If present:
```bash
readelf --string-dump=.gnu_debuglink ascii_engine
ls *.debug
```

Split debug still counts as valid oracle.

### 3.4 Inspect debug line tables (CRITICAL)
```bash
llvm-dwarfdump --debug-line ascii_engine | head -n 40
```

You should see:
- source filenames
- address → line mappings

If empty → alignment impossible even if .debug_info exists.

### 3.5 Inspect function debug entries
```bash
llvm-dwarfdump --debug-info ascii_engine | grep DW_TAG_subprogram | head
```

Confirms:
- functions exist
- they have source references

---

## 4. Stripped Binary Check (leakage prevention)

### 4.1 Create stripped version
```bash
strip ascii_engine -o ascii_engine.stripped
```

### 4.2 Verify debug info is gone
```bash
readelf -S ascii_engine.stripped | grep debug
```

Expected:
- no output

This proves your dual-binary strategy works.

---

## 5. Quick Alignment Sanity Checks (manual learning)

### 5.1 Count functions with debug info
```bash
llvm-dwarfdump --debug-info ascii_engine | grep -c DW_TAG_subprogram
```

### 5.2 Check how many lines are attributed
```bash
llvm-dwarfdump --debug-line ascii_engine | grep -c is_stmt
```

If many functions but few lines → heavy optimization / inlining.

---

## 6. Python Parity Checks (mirror the manual steps)

### 6.1 Check ELF + DWARF
```python
import subprocess

out = subprocess.check_output(["readelf", "-S", "ascii_engine"], text=True)
has_dwarf = any(s in out for s in [".debug_info", ".debug_line", ".zdebug"])
print("has_dwarf:", has_dwarf)
```

### 6.2 Check debug lines
```python
out = subprocess.check_output(
    ["llvm-dwarfdump", "--debug-line", "ascii_engine"],
    text=True, errors="ignore"
)
print("has_debug_lines:", "is_stmt" in out)
```

---

## 7. Definition of "ALIGNABLE FOR TRUTH"

A build is alignable iff:
1. ELF binary exists
2. AND debug oracle exists:
   - `.debug_*` sections OR split debug
3. AND debug line tables exist

Formal rule:
```
alignable_for_truth = has_dwarf AND has_debug_lines
```

**Note:** `.s`, `.bc`, `.ii` do NOT qualify as oracles.