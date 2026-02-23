# C-Programs

Synthetic C programs designed for controlled reverse engineering experiments.

## Structure

### simple_programs/

Single-file C programs of varying complexity. Used for initial pipeline not part of experiment

- Calculator.c
- ContactManagementSystem.c
- HangmanGame.c
- LibraryManagementSystem.c
- NumberGuess.c
- StudentGradeBook.c
- s1_basic.c through s5_computed_goto.c — Targeted test cases for recursion, function pointers, switch statements, and computed gotos
- neg_inline_user.c — Inline function behavior tests

### test/

Multi-file test programs (t01-t15) exercising specific compiler and decompiler challenges:

- `t01_crossfile_calls` — Cross-file function calls
- `t02_shared_header_macros` — Macro expansion across headers
- `t03_header_dominant` — Header-heavy builds
- `t04_static_dup_names` — Static name collisions
- `t05_fptr_callbacks` — Function pointer callbacks
- `t06_recursion_inline` — Recursion and inline interplay
- `t07_switch_parser` — Switch statement complexity
- `t08_loop_heavy` — Loop-intensive code
- `t09_string_format` — String formatting functions
- `t10_math_libm` — Math library usage
- `t11_mixed_stress` — Combined stressors
- `t12_state_machine` — State machine patterns
- `t13_goto_labels` — Goto and label usage
- `t14_anon_aggregates` — Anonymous structures
- `t15_deep_nesting` — Deep nesting levels

Each test directory contains a `manifest.json` describing source files, expected functions, and test metadata.
