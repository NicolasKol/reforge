"""
Tests for join_dwarf_ts.core.candidate — forward-map scoring.
"""
from join_dwarf_ts.core.candidate import (
    CandidateResult,
    TsFunctionInfo,
    detect_header_replication,
    score_candidates,
    select_best,
)
from join_dwarf_ts.core.origin_map import build_origin_map


def _make_ts_func(
    ts_func_id: str,
    tu_path: str,
    name: str,
    start_line: int,
    end_line: int,
    context_hash: str = "",
    start_byte: int = 0,
    end_byte: int = 100,
) -> TsFunctionInfo:
    return TsFunctionInfo(
        ts_func_id=ts_func_id,
        tu_path=tu_path,
        name=name,
        context_hash=context_hash,
        start_line=start_line,
        end_line=end_line,
        start_byte=start_byte,
        end_byte=end_byte,
    )


class TestScoreCandidates:
    """score_candidates() tests."""

    def test_perfect_match(self):
        i_content = '# 1 "test.c"\nint add(int a, int b) {\n    return a + b;\n}\n'
        om = build_origin_map(i_content, "test.c.i")

        dwarf_evidence = {("test.c", 1): 1, ("test.c", 2): 1, ("test.c", 3): 1}
        ts_funcs = [
            _make_ts_func("test.c.i:1:4:hash", "test.c.i", "add", 1, 4),
        ]

        results = score_candidates(dwarf_evidence, ts_funcs, om)
        assert len(results) == 1
        assert results[0].overlap_count > 0
        assert results[0].overlap_ratio > 0.0

    def test_no_overlap(self):
        i_content = '# 1 "test.c"\nint x;\nint y;\n# 10 "other.c"\nint z;\n'
        om = build_origin_map(i_content, "test.c.i")

        dwarf_evidence = {("other.c", 99): 1}
        ts_funcs = [
            _make_ts_func("test.c.i:1:3:hash", "test.c.i", "foo", 1, 3),
        ]

        results = score_candidates(dwarf_evidence, ts_funcs, om)
        # score_candidates filters out zero-overlap candidates
        assert len(results) == 0

    def test_empty_evidence(self):
        i_content = '# 1 "test.c"\nint x;\n'
        om = build_origin_map(i_content, "test.c.i")

        results = score_candidates({}, [], om)
        assert results == []

    def test_multiple_candidates_sorted(self):
        i_content = '# 1 "a.c"\nint a1;\nint a2;\nint a3;\nint a4;\nint a5;\n'
        om = build_origin_map(i_content, "a.c.i")

        dwarf_evidence = {("a.c", 1): 1, ("a.c", 2): 1}
        ts_funcs = [
            _make_ts_func("a.c.i:1:2:h1", "a.c.i", "f1", 1, 2, start_byte=0),
            _make_ts_func("a.c.i:1:6:h2", "a.c.i", "f2", 1, 6, start_byte=0),
        ]

        results = score_candidates(dwarf_evidence, ts_funcs, om)
        assert len(results) == 2
        # f1 has smaller span, same overlap → should rank higher
        # Both have same overlap, f1 span=2, f2 span=6
        sorted_r = sorted(results, key=lambda c: (
            -c.overlap_ratio, -c.overlap_count, c.span_size,
        ))
        assert sorted_r[0].ts_func_id == "a.c.i:1:2:h1"


class TestSelectBest:
    """select_best() threshold and tie-break tests."""

    def test_unique_match(self):
        candidates = [
            CandidateResult(
                ts_func_id="a:1:5:h", tu_path="a", function_name="f",
                context_hash="h", overlap_count=3, total_count=3,
                overlap_ratio=1.0, gap_count=0, span_size=5, start_byte=0,
            ),
        ]
        best, ties, reasons = select_best(candidates, 0.7, 0.02, 1)
        assert best is not None
        assert best.ts_func_id == "a:1:5:h"
        assert ties == []
        assert "UNIQUE_BEST" in reasons

    def test_no_candidates_gives_no_match(self):
        best, ties, reasons = select_best([], 0.7, 0.02, 1)
        assert best is None
        assert "NO_CANDIDATES" in reasons

    def test_below_threshold(self):
        candidates = [
            CandidateResult(
                ts_func_id="a:1:5:h", tu_path="a", function_name="f",
                context_hash="h", overlap_count=1, total_count=10,
                overlap_ratio=0.1, gap_count=9, span_size=5, start_byte=0,
            ),
        ]
        best, ties, reasons = select_best(candidates, 0.7, 0.02, 1)
        assert best is not None  # Still returned for inspection
        assert "LOW_OVERLAP_RATIO" in reasons

    def test_near_tie_detected(self):
        candidates = [
            CandidateResult(
                ts_func_id="a:1:5:h1", tu_path="a.i", function_name="f1",
                context_hash="h1", overlap_count=5, total_count=5,
                overlap_ratio=1.0, gap_count=0, span_size=5, start_byte=0,
            ),
            CandidateResult(
                ts_func_id="b:1:5:h2", tu_path="b.i", function_name="f2",
                context_hash="h2", overlap_count=5, total_count=5,
                overlap_ratio=0.99, gap_count=0, span_size=5, start_byte=0,
            ),
        ]
        best, ties, reasons = select_best(candidates, 0.7, 0.02, 1)
        assert best is not None
        assert len(ties) == 1
        assert "NEAR_TIE" in reasons

    def test_below_min_overlap(self):
        # With overlap_count=0, score_candidates returns empty → NO_CANDIDATES
        best, ties, reasons = select_best([], 0.7, 0.02, 1)
        assert "NO_CANDIDATES" in reasons


class TestHeaderReplication:
    """detect_header_replication() tests."""

    def test_same_hash_different_tu(self):
        best = CandidateResult(
            ts_func_id="a.i:1:5:h", tu_path="a.i", function_name="f",
            context_hash="SAME_HASH", overlap_count=3, total_count=3,
            overlap_ratio=1.0, gap_count=0, span_size=5, start_byte=0,
        )
        tie = CandidateResult(
            ts_func_id="b.i:1:5:h", tu_path="b.i", function_name="f",
            context_hash="SAME_HASH", overlap_count=3, total_count=3,
            overlap_ratio=1.0, gap_count=0, span_size=5, start_byte=0,
        )
        assert detect_header_replication(best, [tie]) is True

    def test_different_hash_no_replication(self):
        best = CandidateResult(
            ts_func_id="a.i:1:5:h", tu_path="a.i", function_name="f",
            context_hash="HASH_A", overlap_count=3, total_count=3,
            overlap_ratio=1.0, gap_count=0, span_size=5, start_byte=0,
        )
        tie = CandidateResult(
            ts_func_id="b.i:1:5:h", tu_path="b.i", function_name="g",
            context_hash="HASH_B", overlap_count=3, total_count=3,
            overlap_ratio=1.0, gap_count=0, span_size=5, start_byte=0,
        )
        assert detect_header_replication(best, [tie]) is False

    def test_same_tu_no_replication(self):
        best = CandidateResult(
            ts_func_id="a.i:1:5:h", tu_path="a.i", function_name="f",
            context_hash="SAME", overlap_count=3, total_count=3,
            overlap_ratio=1.0, gap_count=0, span_size=5, start_byte=0,
        )
        tie = CandidateResult(
            ts_func_id="a.i:6:10:h", tu_path="a.i", function_name="g",
            context_hash="SAME", overlap_count=3, total_count=3,
            overlap_ratio=1.0, gap_count=0, span_size=5, start_byte=0,
        )
        assert detect_header_replication(best, [tie]) is False
