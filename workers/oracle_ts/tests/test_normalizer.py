"""Tests for text normalizer and hashing."""
from oracle_ts.core.normalizer import normalize_text, normalize_and_hash, raw_hash


class TestNormalizeText:
    """Unit tests for normalize_text()."""

    def test_strip_block_comment(self):
        raw = b"int x = 1; /* comment */ int y = 2;"
        assert normalize_text(raw) == b"int x = 1; int y = 2;"

    def test_strip_line_comment(self):
        raw = b"int x = 1; // comment\nint y = 2;"
        assert normalize_text(raw) == b"int x = 1; int y = 2;"

    def test_strip_multiline_block_comment(self):
        raw = b"int x = 1; /* multi\nline\ncomment */ int y = 2;"
        assert normalize_text(raw) == b"int x = 1; int y = 2;"

    def test_whitespace_collapse(self):
        raw = b"int   x  =   1 ;"
        assert normalize_text(raw) == b"int x = 1 ;"

    def test_newlines_collapsed(self):
        raw = b"int x;\n\n\nint y;"
        assert normalize_text(raw) == b"int x; int y;"

    def test_tabs_collapsed(self):
        raw = b"int\tx\t=\t1;"
        assert normalize_text(raw) == b"int x = 1;"

    def test_strip_leading_trailing(self):
        raw = b"  \n  int x;  \n  "
        assert normalize_text(raw) == b"int x;"

    def test_preserves_tokens(self):
        """No token rewriting -- hex stays hex, names unchanged."""
        raw = b"int x = 0xFF; float pi = 3.14;"
        assert normalize_text(raw) == b"int x = 0xFF; float pi = 3.14;"

    def test_empty_input(self):
        assert normalize_text(b"") == b""

    def test_only_whitespace(self):
        assert normalize_text(b"   \n\t   ") == b""

    def test_only_comment(self):
        assert normalize_text(b"/* just a comment */") == b""

    def test_utf8_replacement(self):
        """Invalid UTF-8 bytes replaced, not crash."""
        raw = b"int x = 1;\xff\xfe"
        result = normalize_text(raw)
        assert b"int x = 1;" in result

    def test_comment_inside_string_known_limitation(self):
        """Known limitation: comment-like substrings inside string
        literals ARE stripped by the naive regex.  This test documents
        the behaviour rather than asserting 'correct' output."""
        raw = b'char *s = "/* not a comment */";'
        result = normalize_text(raw)
        # The regex strips the comment-like substring, leaving
        # a spliced string literal -- document, not fix, in v0.
        assert b"/* not a comment */" not in result


class TestNormalizeAndHash:
    """Unit tests for normalize_and_hash()."""

    def test_deterministic(self):
        raw = b"int add(int a, int b) { return a + b; }"
        h1 = normalize_and_hash(raw)
        h2 = normalize_and_hash(raw)
        assert h1 == h2

    def test_sha256_length(self):
        h = normalize_and_hash(b"int x;")
        assert len(h) == 64  # SHA-256 hex digest

    def test_whitespace_invariant(self):
        """Different whitespace, same tokens -> same hash."""
        r1 = b"int x = 1;"
        r2 = b"int   x   =   1;"
        assert normalize_and_hash(r1) == normalize_and_hash(r2)

    def test_comment_invariant(self):
        """With/without comments -> same hash."""
        r1 = b"int x = 1;"
        r2 = b"int x /* val */ = 1; // assign"
        assert normalize_and_hash(r1) == normalize_and_hash(r2)


class TestRawHash:
    """Unit tests for raw_hash()."""

    def test_deterministic(self):
        raw = b"int x = 1;"
        assert raw_hash(raw) == raw_hash(raw)

    def test_sha256_length(self):
        h = raw_hash(b"int x;")
        assert len(h) == 64

    def test_raw_differs_from_normalized(self):
        """Raw hash differs when input has whitespace/comments."""
        raw = b"int x  =  1; /* comment */"
        assert raw_hash(raw) != normalize_and_hash(raw)

    def test_same_content_same_hash(self):
        assert raw_hash(b"abc") == raw_hash(b"abc")

    def test_different_content_different_hash(self):
        assert raw_hash(b"abc") != raw_hash(b"def")
