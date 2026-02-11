"""Tests for tree-sitter C parser wrapper."""
from pathlib import Path

from oracle_ts.core.ts_parser import parse_tu


class TestParseTu:
    """Tests for parse_tu()."""

    def test_simple_parse_ok(self, simple_i_file: Path):
        """Simple .i file parses without errors."""
        result = parse_tu(simple_i_file)
        assert result.parse_status == "OK"
        assert len(result.parse_errors) == 0
        assert result.tu_hash  # non-empty sha256
        assert "tree-sitter" in result.parser_version

    def test_tu_hash_deterministic(self, simple_i_file: Path):
        """Parsing the same file twice gives the same tu_hash."""
        r1 = parse_tu(simple_i_file)
        r2 = parse_tu(simple_i_file)
        assert r1.tu_hash == r2.tu_hash

    def test_parse_error_detected(self, parse_error_i_file: Path):
        """Malformed C produces parse errors."""
        result = parse_tu(parse_error_i_file)
        assert result.parse_status == "ERROR"
        assert len(result.parse_errors) > 0

    def test_empty_file(self, empty_i_file: Path):
        """Empty file parses without errors (valid empty TU)."""
        result = parse_tu(empty_i_file)
        assert result.parse_status == "OK"
        assert result.source_bytes == b""

    def test_multi_func_parse(self, multi_func_i_file: Path):
        """Multi-function file parses OK."""
        result = parse_tu(multi_func_i_file)
        assert result.parse_status == "OK"
        # Should have function_definition nodes
        root = result.tree.root_node #type: ignore
        func_defs = [c for c in root.children if c.type == "function_definition"]
        assert len(func_defs) >= 3  # distance_sq, factorial, fibonacci
