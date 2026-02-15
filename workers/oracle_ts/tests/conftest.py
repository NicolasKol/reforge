"""
Test fixtures for oracle_ts.

Provides sample .i files (preprocessed C) for testing.
"""
from __future__ import annotations

import pytest
import textwrap
from pathlib import Path


# ── Sample preprocessed C content (mimics gcc -E output) ────────────────────

SIMPLE_I = textwrap.dedent("""\
    # 1 "main.c"
    # 1 "<built-in>"
    # 1 "<command-line>"
    # 1 "main.c"

    typedef unsigned long size_t;
    typedef int int32_t;

    int add(int a, int b) {
        return a + b;
    }

    int multiply(int a, int b) {
        int result = 0;
        for (int i = 0; i < b; i++) {
            result = result + a;
        }
        return result;
    }

    int main(int argc, char **argv) {
        int x = add(3, 4);
        int y = multiply(x, 2);
        if (y > 10) {
            return 0;
        } else {
            return 1;
        }
    }
""")

MULTI_FUNC_I = textwrap.dedent("""\
    # 1 "utils.c"
    # 1 "<built-in>"
    # 1 "<command-line>"
    # 1 "utils.c"

    typedef struct {
        int x;
        int y;
    } Point;

    int distance_sq(Point a, Point b) {
        int dx = a.x - b.x;
        int dy = a.y - b.y;
        return dx * dx + dy * dy;
    }

    int factorial(int n) {
        if (n <= 1) {
            return 1;
        }
        return n * factorial(n - 1);
    }

    int fibonacci(int n) {
        if (n <= 0) return 0;
        if (n == 1) return 1;
        int a = 0, b = 1;
        for (int i = 2; i <= n; i++) {
            int tmp = a + b;
            a = b;
            b = tmp;
        }
        return b;
    }
""")

PARSE_ERROR_I = textwrap.dedent("""\
    # 1 "broken.c"

    int broken_func(int a, int b {
        return a + b;
    }

    int ok_func(int x) {
        return x * 2;
    }
""")

DUPLICATE_NAMES_I = textwrap.dedent("""\
    # 1 "dupes.c"

    int compute(int a) {
        return a + 1;
    }

    int compute(int a, int b) {
        return a + b;
    }
""")

DEEP_NESTING_I = textwrap.dedent("""\
    # 1 "deep.c"

    int deeply_nested(int n) {
        if (n > 0) {
            if (n > 1) {
                if (n > 2) {
                    if (n > 3) {
                        if (n > 4) {
                            if (n > 5) {
                                if (n > 6) {
                                    if (n > 7) {
                                        if (n > 8) {
                                            return n;
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        return 0;
    }
""")

ANONYMOUS_STRUCT_I = textwrap.dedent("""\
    # 1 "anon.c"

    int use_anon(int x) {
        struct {
            int val;
        } tmp;
        tmp.val = x;
        return tmp.val;
    }
""")

EXTENSION_I = textwrap.dedent("""\
    # 1 "ext.c"

    __attribute__((noinline))
    int ext_func(int x) {
        return x + 1;
    }
""")

EMPTY_I = ""

DO_WHILE_I = textwrap.dedent("""\
    # 1 "dowhile.c"

    int sum_until(int n) {
        int s = 0, i = 1;
        do {
            s += i;
            i++;
        } while (i <= n);
        return s;
    }
""")

GOTO_I = textwrap.dedent("""\
    # 1 "goto.c"

    int goto_example(int x) {
        if (x < 0)
            goto negative;
        return x;
    negative:
        return -x;
    }
""")


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_i_dir(tmp_path: Path) -> Path:
    """Return a temporary directory for .i files."""
    return tmp_path


@pytest.fixture
def simple_i_file(tmp_i_dir: Path) -> Path:
    """Write SIMPLE_I to a .i file and return the path."""
    p = tmp_i_dir / "main.i"
    p.write_text(SIMPLE_I)
    return p


@pytest.fixture
def multi_func_i_file(tmp_i_dir: Path) -> Path:
    p = tmp_i_dir / "utils.i"
    p.write_text(MULTI_FUNC_I)
    return p


@pytest.fixture
def parse_error_i_file(tmp_i_dir: Path) -> Path:
    p = tmp_i_dir / "broken.i"
    p.write_text(PARSE_ERROR_I)
    return p


@pytest.fixture
def duplicate_names_i_file(tmp_i_dir: Path) -> Path:
    p = tmp_i_dir / "dupes.i"
    p.write_text(DUPLICATE_NAMES_I)
    return p


@pytest.fixture
def deep_nesting_i_file(tmp_i_dir: Path) -> Path:
    p = tmp_i_dir / "deep.i"
    p.write_text(DEEP_NESTING_I)
    return p


@pytest.fixture
def anonymous_struct_i_file(tmp_i_dir: Path) -> Path:
    p = tmp_i_dir / "anon.i"
    p.write_text(ANONYMOUS_STRUCT_I)
    return p


@pytest.fixture
def extension_i_file(tmp_i_dir: Path) -> Path:
    p = tmp_i_dir / "ext.i"
    p.write_text(EXTENSION_I)
    return p


@pytest.fixture
def empty_i_file(tmp_i_dir: Path) -> Path:
    p = tmp_i_dir / "empty.i"
    p.write_text(EMPTY_I)
    return p


@pytest.fixture
def do_while_i_file(tmp_i_dir: Path) -> Path:
    p = tmp_i_dir / "dowhile.i"
    p.write_text(DO_WHILE_I)
    return p


@pytest.fixture
def goto_i_file(tmp_i_dir: Path) -> Path:
    p = tmp_i_dir / "goto.i"
    p.write_text(GOTO_I)
    return p
