"""
Shared pytest fixtures for join_dwarf_ts tests.

All fixtures are pure-Python — no compiler, no ELF binaries, no tree-sitter.
The joiner operates on deserialized JSON dicts and .i file text.
"""
import textwrap

import pytest


# ── Minimal .i file content with GCC #line directives ────────────────────────

SIMPLE_I_CONTENT = textwrap.dedent("""\
    # 1 "simple.c"
    # 1 "<built-in>"
    # 1 "<command-line>"
    # 1 "simple.c"

    int add(int a, int b) {
        int result = a + b;
        return result;
    }

    # 10 "simple.c"
    int multiply(int x, int y) {
        return x * y;
    }

    # 14 "simple.c"
    int main(void) {
        int sum = add(3, 4);
        int prod = multiply(sum, 2);
        return 0;
    }
""")

# .i with #line (alternate syntax)
ALTERNATE_I_CONTENT = textwrap.dedent("""\
    #line 1 "alt.c"
    int foo(int x) {
        return x + 1;
    }
    #line 5 "alt.c"
    int bar(int y) {
        return y * 2;
    }
""")

# .i with system header includes
SYSTEM_HEADER_I_CONTENT = textwrap.dedent("""\
    # 1 "main.c"
    # 1 "<built-in>"
    # 1 "<command-line>"
    # 1 "/usr/include/stdio.h" 1 3
    # 50 "/usr/include/stdio.h" 3
    extern int printf(const char *, ...);
    # 2 "main.c" 2
    int main(void) {
        printf("hello\\n");
        return 0;
    }
""")


# ── DWARF oracle fixture data ───────────────────────────────────────────────

@pytest.fixture
def dwarf_report():
    """Minimal oracle_dwarf report dict."""
    return {
        "package_name": "oracle_dwarf",
        "oracle_version": "v0",
        "schema_version": "0.2",
        "profile_id": "linux-x86_64-gcc-O0O1",
        "binary_path": "/files/artifacts/synthetic/simple/O0/debug/bin/simple",
        "binary_sha256": "abc123",
        "build_id": "deadbeef",
        "verdict": "ACCEPT",
        "reasons": [],
        "function_counts": {
            "total": 3,
            "accept": 3,
            "warn": 0,
            "reject": 0,
        },
    }


@pytest.fixture
def dwarf_functions():
    """DWARF functions with line_rows (schema 0.2)."""
    return [
        {
            "function_id": "0x1000:0x0-0x20",
            "name": "add",
            "verdict": "ACCEPT",
            "reasons": [],
            "dominant_file": "simple.c",
            "dominant_file_ratio": 1.0,
            "line_min": 3,
            "line_max": 5,
            "n_line_rows": 4,
            "line_rows": [
                {"file": "simple.c", "line": 3, "count": 1},
                {"file": "simple.c", "line": 4, "count": 2},
                {"file": "simple.c", "line": 5, "count": 1},
            ],
            "file_row_counts": {"simple.c": 4},
        },
        {
            "function_id": "0x1000:0x20-0x40",
            "name": "multiply",
            "verdict": "ACCEPT",
            "reasons": [],
            "dominant_file": "simple.c",
            "dominant_file_ratio": 1.0,
            "line_min": 10,
            "line_max": 12,
            "n_line_rows": 3,
            "line_rows": [
                {"file": "simple.c", "line": 10, "count": 1},
                {"file": "simple.c", "line": 11, "count": 1},
                {"file": "simple.c", "line": 12, "count": 1},
            ],
            "file_row_counts": {"simple.c": 3},
        },
        {
            "function_id": "0x1000:0x40-0x80",
            "name": "main",
            "verdict": "ACCEPT",
            "reasons": [],
            "dominant_file": "simple.c",
            "dominant_file_ratio": 1.0,
            "line_min": 14,
            "line_max": 18,
            "n_line_rows": 5,
            "line_rows": [
                {"file": "simple.c", "line": 14, "count": 1},
                {"file": "simple.c", "line": 15, "count": 1},
                {"file": "simple.c", "line": 16, "count": 1},
                {"file": "simple.c", "line": 17, "count": 1},
                {"file": "simple.c", "line": 18, "count": 1},
            ],
            "file_row_counts": {"simple.c": 5},
        },
    ]


@pytest.fixture
def dwarf_functions_with_reject(dwarf_functions):
    """DWARF functions including a REJECT entry."""
    reject = {
        "function_id": "0x1000:0x80-0x90",
        "name": "__libc_csu_init",
        "verdict": "REJECT",
        "reasons": ["DECLARATION_ONLY"],
        "dominant_file": None,
        "dominant_file_ratio": 0.0,
        "line_min": 0,
        "line_max": 0,
        "n_line_rows": 0,
        "line_rows": [],
        "file_row_counts": {},
    }
    return dwarf_functions + [reject]


# ── Tree-sitter oracle fixture data ─────────────────────────────────────────

@pytest.fixture
def ts_report():
    """Minimal oracle_ts report dict."""
    return {
        "package_name": "oracle_ts",
        "oracle_version": "v0",
        "schema_version": "0.1",
        "profile_id": "ts-c-v0",
        "tu_reports": [
            {
                "tu_path": "simple.c.i",
                "tu_hash": "sha256:aaa111",
                "function_count": 3,
            },
        ],
        "function_counts": {
            "total": 3,
            "accept": 3,
            "warn": 0,
            "reject": 0,
        },
    }


@pytest.fixture
def ts_functions():
    """TS function entries matching the .i file structure."""
    return [
        {
            "ts_func_id": "simple.c.i:5:8:hash_add",
            "name": "add",
            "context_hash": "ctx_add",
            "start_line": 5,
            "end_line": 8,
            "start_byte": 80,
            "end_byte": 140,
            "verdict": "ACCEPT",
        },
        {
            "ts_func_id": "simple.c.i:11:13:hash_mul",
            "name": "multiply",
            "context_hash": "ctx_mul",
            "start_line": 11,
            "end_line": 13,
            "start_byte": 150,
            "end_byte": 200,
            "verdict": "ACCEPT",
        },
        {
            "ts_func_id": "simple.c.i:16:19:hash_main",
            "name": "main",
            "context_hash": "ctx_main",
            "start_line": 16,
            "end_line": 19,
            "start_byte": 210,
            "end_byte": 300,
            "verdict": "ACCEPT",
        },
    ]


@pytest.fixture
def i_contents():
    """Dict of tu_path → .i file content."""
    return {"simple.c.i": SIMPLE_I_CONTENT}
