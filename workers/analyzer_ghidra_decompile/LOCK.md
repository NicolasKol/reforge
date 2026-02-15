# analyzer_ghidra_decompile v1 — Scope Lock

> **Package name:** `analyzer_ghidra_decompile`
> **Analyzer version:** v1
> **Schema version:** 1.0
> **Architecture:** Two-tier (Java raw extraction → Python reshape)

---

## §1 Purpose

`analyzer_ghidra_decompile` invokes Ghidra headless in Docker to decompile
stripped ELF binaries and produces five structured output files per binary.

The package provides the **decompiler-side observations** that downstream
evaluation stages compare against DWARF ground truth. It is designed for
academic reproducibility: deterministic output, stable identifiers, explicit
provenance, and frozen verdict/noise taxonomies.

---

## §2 Support profile (v1)

| Dimension           | Value                         |
|---------------------|-------------------------------|
| Target platform     | linux-x86_64                  |
| Binary format       | ELF (stripped)                |
| Decompiler          | Ghidra ≥ 11.0                 |
| Invocation          | `docker exec` (headless)      |
| Variants            | Configurable via `Profile`    |

---

## §3 Outputs

Five files per `<test_case>/<opt>/<variant>/ghidra_decompile/`:

| File               | Format      | Description                           |
|--------------------|-------------|---------------------------------------|
| `report.json`      | JSON        | Binary-level verdict + summary stats  |
| `functions.jsonl`  | JSONL       | Per-function metadata and decompiled C |
| `variables.jsonl`  | JSONL       | Per-variable storage + access info    |
| `cfg.jsonl`        | JSONL       | Per-function CFG (blocks + edges)     |
| `calls.jsonl`      | JSONL       | Per-callsite records                  |

---

## §4 Binary-level verdict

### Reject reasons

| Reason               | Condition                                  |
|----------------------|--------------------------------------------|
| `NOT_ELF`            | File is not a valid ELF binary             |
| `UNSUPPORTED_ARCH`   | Not x86-64                                 |
| `GHIDRA_CRASH`       | Ghidra process crashes                     |
| `GHIDRA_TIMEOUT`     | Ghidra exceeds analysis timeout            |
| `NO_FUNCTIONS_FOUND` | Ghidra finds zero functions                |
| `JSONL_PARSE_ERROR`  | Raw JSONL is malformed                     |

### Warn reasons

| Reason                     | Condition                                     |
|----------------------------|-----------------------------------------------|
| `HIGH_DECOMPILE_FAIL_RATE` | >20% of functions fail decompilation          |
| `GHIDRA_NONZERO_EXIT`      | Non-zero exit but output exists               |
| `MISSING_SECTIONS`         | Expected sections absent                      |
| `PARTIAL_ANALYSIS`         | Analysis incomplete                           |

---

## §5 Function-level verdict

### §5.1 Verdict enum

| Verdict | Meaning                                    |
|---------|--------------------------------------------|
| `OK`    | Successfully decompiled, no significant issues |
| `WARN`  | Decompiled but with warnings or noise flags |
| `FAIL`  | Decompilation failed or no body            |

### §5.2 Warning taxonomy (11 codes)

| Code                           | Trigger                              |
|--------------------------------|--------------------------------------|
| `DECOMPILE_TIMEOUT`            | Regex: timed out / timeout           |
| `UNKNOWN_CALLING_CONVENTION`   | Regex: calling convention            |
| `PARAM_STORAGE_LOCKED`         | Regex: param storage lock            |
| `UNREACHABLE_BLOCKS_REMOVED`   | Regex: unreachable block             |
| `BAD_INSTRUCTION_DATA`         | Regex: bad instruction / data        |
| `TRUNCATED_CONTROL_FLOW`       | Regex: truncated control flow        |
| `UNRESOLVED_INDIRECT_JUMP`     | Regex: indirect jump unresolved      |
| `NON_RETURNING_CALL_MISMODELED`| Regex: non-return                    |
| `SWITCH_RECOVERY_FAILED`       | Regex: switch recovery / could not recover |
| `DECOMPILER_INTERNAL_WARNING`  | Fallback for unmatched warnings      |
| `INLINE_LIKELY`                | Added in Pass 2 if fat+temp+bb thresholds met |

---

## §6 Variables

### §6.1 Variable kind classification

| Kind         | Rule                                              |
|--------------|---------------------------------------------------|
| `PARAM`      | `is_param=True`                                   |
| `GLOBAL_REF` | `!is_param` and `MEMORY` storage with `addr_va`   |
| `TEMP`       | `!is_param` and `UNIQUE` storage                  |
| `LOCAL`      | Everything else                                   |

### §6.2 Storage key format

| Storage class | Key format              | Example            |
|---------------|-------------------------|--------------------|
| `STACK`       | `stack:off:{sign}0x{n}` | `stack:off:-0x10`  |
| `REGISTER`    | `reg:{name}`            | `reg:RDI`          |
| `MEMORY`      | `mem:0x{addr}`          | `mem:0x404000`     |
| `UNIQUE`      | `uniq:{name}`           | `uniq:uVar1`       |
| `UNKNOWN`     | `unk:{name}`            | `unk:mystery`      |

### §6.3 Access signature

`access_sig` = `sha256(sorted(access_site_vas) + storage_key)[:16]`

If no access sites: `sha256(storage_key)[:16]`.

### §6.4 Variable ID

`{function_id}:{var_kind}:{storage_key}:{access_sig}`

---

## §7 CFG

### §7.1 Block model

One `GhidraCfgEntry` per function containing:
- `blocks[]`: each with `block_id`, `start_va`, `end_va`, `succ[]` (block_ids)
- `bb_count`, `edge_count`, `cyclomatic` ($E - N + 2$)

Block successors are resolved from VA → block_id within the function scope.

### §7.2 CFG completeness

| Level    | Condition                               |
|----------|-----------------------------------------|
| `HIGH`   | No CFG-affecting warnings               |
| `MEDIUM` | Unreachable blocks removed              |
| `LOW`    | Unresolved indirect jumps               |

---

## §8 Calls

One `GhidraCallEntry` per callsite:
- `caller_function_id`, `caller_entry_va`
- `callsite_va`, `callsite_hex`
- `callee_entry_va` (nullable for indirect), `callee_name`
- `call_kind`: `DIRECT` | `INDIRECT`
- `is_external_target`, `is_import_proxy_target`

Sorted by `(caller_entry_va, callsite_va)`.

---

## §9 Noise classification

### §9.1 PLT / stub

Function in `.plt` section or similar prefix.

### §9.2 Init / fini aux

Names: `_init`, `_fini`, `_start`, `__libc_start_main`,
`__libc_csu_init`, `__libc_csu_fini`.

### §9.3 Compiler aux

Names: `frame_dummy`, `register_tm_clones`, `deregister_tm_clones`,
`__do_global_dtors_aux`, `__do_global_ctors_aux`, etc. (18-name frozen set).

### §9.4 Library-like flag

`is_library_like` = any noise flag set **or** `is_external_block` **or** `is_thunk`.

---

## §10 Proxy metrics

Per function:
- `asm_insn_count`: from Ghidra raw record
- `c_line_count`: non-empty lines in `c_raw`
- `insn_to_c_ratio`: `asm_insn_count / c_line_count`
- `temp_name_count`: count of `[a-z]Var[0-9]+` names in variables
- `is_fat_function`: size or bb_count exceed p90 thresholds
- `inline_likely`: small size + low insn count + single caller heuristic

---

## §11 Determinism guarantee

Given the same raw JSONL input, the Python pipeline **must** produce
byte-identical JSONL outputs across runs. This is enforced by:
- Sorting all records by stable keys before emission
- Using `sort_keys=True` in JSON serialization
- Deterministic ID construction

`report.json` may have a differing `timestamp` field but all analysis
fields must be identical.

---

## §12 Provenance

`report.json` includes:
- `schema_version`, `analyzer_version`, `package_name`
- `ghidra_version`, `java_version` (from raw summary)
- `script_hash` (SHA256 of ExportDecompJsonl.java, for reproducibility)
- `binary_sha256`, `binary_path`
- `profile_id`
- `noise_list_version`
- `timestamp` (ISO 8601)

Binary provenance (compiler, optimization, build ID) is tracked externally
via build receipts and joined using `binary_sha256` as the key.

---

## §13 Acceptance tests

1. **Report exists**: `report.json` exists, `binary_verdict ≠ REJECT`
2. **Functions sorted**: `functions.jsonl` non-empty, sorted by `entry_va`
3. **Function records valid**: every record has `function_id`, `entry_va`,
   `decompile_status ∈ {OK, FAIL}`, `verdict ∈ {OK, WARN, FAIL}`
4. **Variables valid**: every variable references a valid `function_id`,
   has `storage_key` and 16-char `access_sig`
5. **CFG valid**: `bb_count`/`edge_count` are integers, block successor
   IDs reference declared `block_id`s within the same function
6. **Calls valid**: sorted by `(caller_entry_va, callsite_va)`,
   `caller_function_id` exists in functions
7. **Determinism**: two runs on same input → identical JSONL content

---

## §14 Non-goals (v1)

- No cross-decompiler comparison (IDA, Binary Ninja out of scope)
- No source-body alignment (that is a downstream stage)
- No type recovery beyond Ghidra's default analysis
- No DWARF consumption (this package only sees stripped binaries)
- No inter-procedural data-flow analysis
- No custom Ghidra analysis scripts beyond `ExportDecompJsonl.java`

---

## §15 Architecture

```
┌─────────────────────────────────────────────────┐
│  Tier 1: Java (ExportDecompJsonl.java)          │
│  Runs inside Ghidra headless via docker exec    │
│  Emits: raw JSONL (1 line/function + summary)   │
└──────────────────────┬──────────────────────────┘
                       │ raw .jsonl file
┌──────────────────────▼──────────────────────────┐
│  Tier 2: Python (analyzer_ghidra_decompile)     │
│  Parses raw JSONL                               │
│  Applies: schema, verdicts, noise, metrics      │
│  Writes: 5 output files                         │
└─────────────────────────────────────────────────┘
```

---

## §16 Version history

| Version | Date       | Changes               |
|---------|------------|-----------------------|
| v1      | 2025-06    | Initial specification |
| v1-fix1 | 2026-02    | §5.2 synced with implementation (review R13/R14): added DECOMPILE_TIMEOUT regex, updated taxonomy to 11 codes matching `_WARNING_PATTERNS`. P90 computation fixed (review R9). `_TEMP_NAME_RE` deduplicated (review R3). |
