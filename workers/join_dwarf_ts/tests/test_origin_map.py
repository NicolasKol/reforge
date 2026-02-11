"""
Tests for join_dwarf_ts.core.origin_map — #line directive parsing.
"""
import textwrap

from join_dwarf_ts.core.origin_map import OriginMap, build_origin_map, query_forward


class TestBuildOriginMap:
    """build_origin_map() contract tests."""

    def test_simple_directives(self):
        content = textwrap.dedent("""\
            # 1 "hello.c"
            int main() {
                return 0;
            }
        """)
        om = build_origin_map(content, "hello.c.i")
        assert om.tu_path == "hello.c.i"
        assert om.origin_available is True
        # Line 0 is the directive itself → None (directives don't map)
        assert query_forward(om, 0) is None
        # Lines after directive map to incrementing origin lines
        assert query_forward(om, 1) == ("hello.c", 1)
        assert query_forward(om, 2) == ("hello.c", 2)

    def test_alternate_line_syntax(self):
        content = textwrap.dedent("""\
            #line 10 "alt.c"
            int foo() { return 1; }
        """)
        om = build_origin_map(content, "alt.c.i")
        assert query_forward(om, 0) is None  # directive line
        assert query_forward(om, 1) == ("alt.c", 10)

    def test_builtin_excluded(self):
        content = textwrap.dedent("""\
            # 1 "<built-in>"
            # 1 "<command-line>"
            # 1 "real.c"
            int x;
        """)
        om = build_origin_map(content, "test.i")
        assert query_forward(om, 0) is None
        assert query_forward(om, 1) is None
        assert query_forward(om, 2) is None  # directive line
        assert query_forward(om, 3) == ("real.c", 1)

    def test_system_header_excluded(self):
        """Flag 3 in #line directive marks system headers → excluded."""
        content = textwrap.dedent("""\
            # 1 "main.c"
            # 1 "/usr/include/stdio.h" 1 3
            extern int printf(const char *, ...);
            # 3 "main.c" 2
            int main(void) { return 0; }
        """)
        om = build_origin_map(content, "main.c.i")
        # Line 0 → directive → None
        assert query_forward(om, 0) is None
        # Line 1 → directive for /usr/include/stdio.h (flag 3) → None
        assert query_forward(om, 1) is None
        # Line 2 → content under flag-3 system header → None
        assert query_forward(om, 2) is None
        # Line 3 → directive back to main.c → None
        assert query_forward(om, 3) is None
        # Line 4 → content at main.c:3
        assert query_forward(om, 4) == ("main.c", 3)

    def test_escaped_quotes_in_path(self):
        content = '# 1 "path\\"with\\"quotes.c"\nint x;\n'
        om = build_origin_map(content, "test.i")
        result = query_forward(om, 0)
        # Line 0 is the directive itself → None
        assert result is None
        result = query_forward(om, 1)
        assert result is not None
        assert 'path"with"quotes.c' in result[0]

    def test_out_of_range_returns_none(self):
        om = build_origin_map("# 1 \"a.c\"\nint x;\n", "test.i")
        assert query_forward(om, 999) is None
        assert query_forward(om, -1) is None

    def test_no_directives(self):
        om = build_origin_map("int x = 1;\n", "plain.i")
        assert om.origin_available is False
        assert query_forward(om, 0) is None

    def test_flags_preserved(self):
        """Flags after the path should not break parsing."""
        content = '# 1 "file.c" 1 3 4\nint x;\n'
        om = build_origin_map(content, "test.i")
        # flag 3 = system header → excluded; line 0 = directive → None
        assert query_forward(om, 0) is None
        # line 1 = content under system header → None
        assert query_forward(om, 1) is None

    def test_custom_excluded_prefixes(self):
        content = textwrap.dedent("""\
            # 1 "/my/custom/path/header.h"
            int x;
            # 3 "real.c"
            int y;
        """)
        om = build_origin_map(
            content, "test.i",
            excluded_prefixes=("/my/custom/path",),
        )
        assert query_forward(om, 0) is None  # directive
        assert query_forward(om, 1) is None  # excluded content
        assert query_forward(om, 2) is None  # directive
        assert query_forward(om, 3) == ("real.c", 3)

    def test_multiple_file_switches(self):
        content = textwrap.dedent("""\
            # 1 "a.c"
            int a;
            # 1 "b.c"
            int b;
            # 5 "a.c"
            int c;
        """)
        om = build_origin_map(content, "test.i")
        assert query_forward(om, 0) is None   # directive # 1 "a.c"
        assert query_forward(om, 1) == ("a.c", 1)  # int a;
        assert query_forward(om, 2) is None   # directive # 1 "b.c"
        assert query_forward(om, 3) == ("b.c", 1)  # int b;
        assert query_forward(om, 4) is None   # directive # 5 "a.c"
        assert query_forward(om, 5) == ("a.c", 5)  # int c;
