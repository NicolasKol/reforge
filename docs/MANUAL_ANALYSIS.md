# Manual DWARF-Based Source–Binary Alignment (Step-by-Step)

This document describes how to manually verify **source–binary alignment** and **ground-truth variable information** for a small C program compiled with debug symbols (`-g`) at `-O0`.
The goal is to understand and validate the exact information later used for automated evaluation.

---

## Preconditions

* Binary compiled with:

  * `-g`
  * `-O0` (or `-O1`)
* Binary is **unstripped**
* Corresponding source files are available
* Tools available:

  * `readelf`
  * `llvm-dwarfdump`
  * `addr2line` (optional)
  * Ghidra (for visualization / sanity checks)

---

## 1. Verify presence of DWARF sections

### Command

```bash
readelf -S debug | grep -E '\.debug|\.zdebug'
```

### Purpose

Confirms that the binary contains the required DWARF sections:

* `.debug_info` → functions, variables, types
* `.debug_line` → address → source line mapping
* `.debug_str`, `.debug_abbrev` → supporting metadata

### Expected result

Presence of at least:

* `.debug_info`
* `.debug_line`
* `.debug_str`

---

## 2. Inspect the DWARF line table (address → source mapping)

### Command

```bash
llvm-dwarfdump --debug-line debug
```

(Optional: restrict output)

```bash
llvm-dwarfdump --debug-line debug | sed -n '40,140p'
```

### Purpose

Extracts the **line table**, which maps machine-code addresses to:

* source file index
* source line number
* column number

This is the foundation for function-to-source alignment.

---

## 3. Identify the source file index

From the line table header:

```
file_names[1]: "Calculator.c"
```

### Meaning

All line rows with:

```
File = 1
```

correspond to `Calculator.c`.

Header files (`stdio.h`, etc.) can be ignored for function alignment.

---

## 4. Extract function ground truth (`main`)

### Command

```bash
llvm-dwarfdump --debug-info debug | grep -A60 'DW_AT_name ("main")'
```

### Purpose

Find the **DW_TAG_subprogram** entry for `main`, which defines:

* function name
* source declaration location
* binary address range

### Example result

```
DW_TAG_subprogram
  DW_AT_name        ("main")
  DW_AT_decl_file  (Calculator.c)
  DW_AT_decl_line  (4)
  DW_AT_low_pc     (0x1159)
  DW_AT_high_pc    (0x132a)
```

### Interpretation

* `main` occupies addresses `[0x1159, 0x132a)`
* All line-table rows within this range belong to `main`

---

## 5. Extract variable ground truth (stack variables)

### Command

```bash
llvm-dwarfdump --debug-info debug | grep -A80 'DW_AT_name    ("num1")'
```

Repeat for other variables (`num2`, `operator`, etc.).

### Example result

```
DW_TAG_variable
  DW_AT_name      ("num1")
  DW_AT_type      ("double")
  DW_AT_decl_line (5)
  DW_AT_location  (DW_OP_fbreg -24)
```

### Interpretation

* Variable name: `num1`
* Type: `double`
* Location: stack offset **−24 bytes** relative to frame base

  * Decimal `-24` = Hex `-0x18`
* Physical meaning: `num1` lives at `[rbp - 0x18]`

This offset is the **true variable identity** for evaluation.

---

## 6. Cross-check with assembly (sanity check)

### Method

In Ghidra or via `objdump`, find instructions accessing:

```
[RBP - 0x18]
```

Example:

```
LEA RAX, [RBP + -0x18]
```

### Purpose

Confirms:

* DWARF variable location
* actual machine-code usage
* stack offset consistency

---

## 7. Cross-check with Ghidra (visual validation)

In Ghidra:

* Open `main`
* Observe:

  * Local Variables panel
  * Stack offsets (e.g. `Stack[-0x18]`)
  * Source line annotations (`Calculator.c:12`)

This confirms that:

* Ghidra is faithfully rendering DWARF
* No heuristic guessing is involved at `-O0`

---

## 8. Manual function–source alignment result

Using:

* `DW_AT_low_pc / high_pc`
* `.debug_line` rows within that range

We derive:

* **Source file:** `Calculator.c`
* **Source line span:** approx. lines `4–31`
* **Aligned function:** `main`

This is the **manual version of Source-Trace alignment**.

---

## 9. What this enables later (automation)

This manual process validates that automated extraction can rely on:

* `.debug_info` → function + variable ground truth
* `.debug_line` → address → source alignment
* stack offsets (`DW_OP_fbreg`) → variable identity
* names are secondary; offsets + scope are primary

This procedure is **deterministic at O0/O1** and forms a valid evaluation oracle.

---

## Final takeaway

What was proven manually:

* DWARF encodes **complete semantic ground truth**
* Ghidra visualizes, but does not invent, this information
* Stack offsets are the stable anchor for variable matching
* Source alignment is address-range based, not heuristic

This justifies:

* limiting evaluation to `-O0 / -O1`
* excluding optimized/inlined cases
* automating extraction using DWARF parsers (`pyelftools`) or Ghidra APIs

