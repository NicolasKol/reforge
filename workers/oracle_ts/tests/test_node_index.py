"""Tests for structural node index."""
from pathlib import Path

from oracle_ts.core.ts_parser import parse_tu
from oracle_ts.core.node_index import (
    STRUCTURAL_NODE_TYPES,
    index_structural_nodes,
)


# ── Helper ───────────────────────────────────────────────────────────────────

def _get_func_node(tmp_path: Path, code: str):
    """Parse C code, return (first function_definition node, source_bytes)."""
    p = tmp_path / "test.i"
    p.write_text(code)
    pr = parse_tu(p)
    root = pr.tree.root_node  # type: ignore
    for child in root.children:
        if child.type == "function_definition":
            return child, pr.source_bytes
    raise ValueError("No function_definition found")


# ── Tests: allowlist metadata ────────────────────────────────────────────────

class TestStructuralNodeTypes:
    """Allowlist sanity checks."""

    def test_allowlist_is_frozenset(self):
        assert isinstance(STRUCTURAL_NODE_TYPES, frozenset)

    def test_baseline_types_present(self):
        expected = {
            "compound_statement", "if_statement", "for_statement",
            "while_statement", "switch_statement", "return_statement",
        }
        assert expected.issubset(STRUCTURAL_NODE_TYPES)


# ── Tests: per-type detection ────────────────────────────────────────────────

class TestPerTypeDetection:
    """Each allowlisted node type is collected."""

    def test_compound_statement(self, tmp_path):
        code = "int f(void) { return 0; }\n"
        node, src = _get_func_node(tmp_path, code)
        types = [r.node_type for r in index_structural_nodes(node, src)]
        assert "compound_statement" in types

    def test_if_statement(self, tmp_path):
        code = "int f(int x) { if (x) return 1; return 0; }\n"
        node, src = _get_func_node(tmp_path, code)
        types = [r.node_type for r in index_structural_nodes(node, src)]
        assert "if_statement" in types

    def test_for_statement(self, tmp_path):
        code = "void f(void) { for (int i=0; i<10; i++) {} }\n"
        node, src = _get_func_node(tmp_path, code)
        types = [r.node_type for r in index_structural_nodes(node, src)]
        assert "for_statement" in types

    def test_while_statement(self, tmp_path):
        code = "void f(void) { while (1) {} }\n"
        node, src = _get_func_node(tmp_path, code)
        types = [r.node_type for r in index_structural_nodes(node, src)]
        assert "while_statement" in types

    def test_switch_statement(self, tmp_path):
        code = "void f(int x) { switch(x) { case 0: break; } }\n"
        node, src = _get_func_node(tmp_path, code)
        types = [r.node_type for r in index_structural_nodes(node, src)]
        assert "switch_statement" in types

    def test_return_statement(self, tmp_path):
        code = "int f(void) { return 42; }\n"
        node, src = _get_func_node(tmp_path, code)
        types = [r.node_type for r in index_structural_nodes(node, src)]
        assert "return_statement" in types

    def test_do_statement(self, tmp_path):
        code = "void f(void) { do { } while (1); }\n"
        node, src = _get_func_node(tmp_path, code)
        types = [r.node_type for r in index_structural_nodes(node, src)]
        assert "do_statement" in types

    def test_goto_statement(self, tmp_path):
        code = "void f(void) { goto end; end: return; }\n"
        node, src = _get_func_node(tmp_path, code)
        types = [r.node_type for r in index_structural_nodes(node, src)]
        assert "goto_statement" in types

    def test_labeled_statement(self, tmp_path):
        code = "void f(void) { goto end; end: return; }\n"
        node, src = _get_func_node(tmp_path, code)
        types = [r.node_type for r in index_structural_nodes(node, src)]
        assert "labeled_statement" in types


# ── Tests: depth tracking / flags ────────────────────────────────────────────

class TestDepthAndFlags:
    """Depth tracking and DEEP_NESTING flag."""

    def test_depth_increases_with_nesting(self, tmp_path):
        code = "void f(void) { if (1) { if (1) { } } }\n"
        node, src = _get_func_node(tmp_path, code)
        results = index_structural_nodes(node, src)
        depths = sorted(set(r.depth for r in results))
        assert len(depths) > 1

    def test_deep_nesting_flag_set(self, tmp_path):
        """DEEP_NESTING flag set when depth >= threshold."""
        inner = "{ " * 9 + "return 0;" + " }" * 9
        code = f"int f(void) {{ if(1) {{ if(1) {{ if(1) {{ if(1) {{ if(1) {{ if(1) {{ if(1) {{ if(1) {{ if(1) {inner} }} }} }} }} }} }} }} }} }}\n"
        node, src = _get_func_node(tmp_path, code)
        results = index_structural_nodes(node, src, deep_nesting_threshold=8)
        flagged = [r for r in results if "DEEP_NESTING" in r.uncertainty_flags]
        assert len(flagged) > 0

    def test_no_deep_nesting_below_threshold(self, tmp_path):
        code = "void f(void) { if (1) { return; } }\n"
        node, src = _get_func_node(tmp_path, code)
        results = index_structural_nodes(node, src, deep_nesting_threshold=8)
        flagged = [r for r in results if "DEEP_NESTING" in r.uncertainty_flags]
        assert len(flagged) == 0

    def test_custom_threshold(self, tmp_path):
        """Low threshold flags shallow nesting."""
        code = "void f(void) { if (1) { if (1) { } } }\n"
        node, src = _get_func_node(tmp_path, code)
        results = index_structural_nodes(node, src, deep_nesting_threshold=2)
        flagged = [r for r in results if "DEEP_NESTING" in r.uncertainty_flags]
        assert len(flagged) > 0


# ── Tests: output quality ────────────────────────────────────────────────────

class TestOutputQuality:
    """Hash, span, and determinism checks."""

    def test_node_hash_raw_populated(self, tmp_path):
        code = "int f(void) { return 0; }\n"
        node, src = _get_func_node(tmp_path, code)
        results = index_structural_nodes(node, src)
        for r in results:
            assert len(r.node_hash_raw) == 64  # SHA-256 hex

    def test_spans_valid(self, tmp_path):
        code = "int f(int x) { if (x) { return x; } return 0; }\n"
        node, src = _get_func_node(tmp_path, code)
        results = index_structural_nodes(node, src)
        for r in results:
            assert r.start_byte < r.end_byte
            assert r.start_line <= r.end_line

    def test_empty_function_no_control_flow(self, tmp_path):
        code = "void f(void) { }\n"
        node, src = _get_func_node(tmp_path, code)
        results = index_structural_nodes(node, src)
        types = [r.node_type for r in results]
        assert "compound_statement" in types
        assert "if_statement" not in types
        assert "return_statement" not in types

    def test_deterministic(self, tmp_path):
        """Same input -> identical output."""
        code = "int f(int x) { if(x) { for(int i=0;i<x;i++){} return x; } return 0; }\n"
        node1, src1 = _get_func_node(tmp_path, code)
        r1 = index_structural_nodes(node1, src1)
        # Re-parse
        node2, src2 = _get_func_node(tmp_path, code)
        r2 = index_structural_nodes(node2, src2)
        assert len(r1) == len(r2)
        for a, b in zip(r1, r2):
            assert a.node_type == b.node_type
            assert a.depth == b.depth
            assert a.node_hash_raw == b.node_hash_raw
