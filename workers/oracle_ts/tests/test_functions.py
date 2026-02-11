"""Tests for function index extraction."""
from pathlib import Path

from oracle_ts.core.ts_parser import parse_tu
from oracle_ts.core.function_index import index_functions


class TestFunctionIndex:
    """Tests for index_functions()."""

    def test_simple_extraction(self, simple_i_file: Path):
        """Extract functions from a simple .i file."""
        pr = parse_tu(simple_i_file)
        funcs = index_functions(pr)
        names = [f.name for f in funcs]
        assert "add" in names
        assert "multiply" in names
        assert "main" in names
        assert len(funcs) == 3

    def test_function_spans(self, simple_i_file: Path):
        """Function spans are valid (start < end)."""
        pr = parse_tu(simple_i_file)
        funcs = index_functions(pr)
        for f in funcs:
            assert f.start_byte < f.end_byte
            assert f.start_line <= f.end_line

    def test_span_id_format(self, simple_i_file: Path):
        """span_id follows tu_path:start_byte:end_byte format."""
        pr = parse_tu(simple_i_file)
        funcs = index_functions(pr)
        for f in funcs:
            # span_id = tu_path:start_byte:end_byte
            # Split from the right to handle Windows paths with ':'
            parts = f.span_id.rsplit(":", 2)
            assert len(parts) == 3
            assert parts[0] == pr.tu_path

    def test_ts_func_id_format(self, simple_i_file: Path):
        """ts_func_id = span_id:context_hash."""
        pr = parse_tu(simple_i_file)
        funcs = index_functions(pr)
        for f in funcs:
            assert f.ts_func_id == f"{f.span_id}:{f.context_hash}"

    def test_context_hash_deterministic(self, simple_i_file: Path):
        """Parsing twice gives the same context_hash."""
        pr1 = parse_tu(simple_i_file)
        pr2 = parse_tu(simple_i_file)
        f1 = index_functions(pr1)
        f2 = index_functions(pr2)
        for a, b in zip(f1, f2):
            assert a.context_hash == b.context_hash

    def test_preamble_span(self, simple_i_file: Path):
        """Preamble span starts at 0 and ends at function start."""
        pr = parse_tu(simple_i_file)
        funcs = index_functions(pr)
        for f in funcs:
            assert f.preamble_span.start_byte == 0
            assert f.preamble_span.end_byte == f.start_byte

    def test_signature_and_body_spans(self, simple_i_file: Path):
        """Signature + body cover the full function span."""
        pr = parse_tu(simple_i_file)
        funcs = index_functions(pr)
        for f in funcs:
            assert f.signature_span.start_byte == f.start_byte
            assert f.body_span.end_byte == f.end_byte

    def test_multi_file_extraction(self, multi_func_i_file: Path):
        """Extract functions from a multi-function .i file."""
        pr = parse_tu(multi_func_i_file)
        funcs = index_functions(pr)
        names = [f.name for f in funcs]
        assert "distance_sq" in names
        assert "factorial" in names
        assert "fibonacci" in names

    def test_no_functions_in_empty(self, empty_i_file: Path):
        """Empty file produces no functions."""
        pr = parse_tu(empty_i_file)
        funcs = index_functions(pr)
        assert len(funcs) == 0
