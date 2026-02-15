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

    def test_partial_overlap(self):
        """TS span covers 3 of 5 DWARF evidence entries → ratio = 0.6."""
        i_content = '# 1 "src.c"\nline1;\nline2;\nline3;\nline4;\nline5;\n'
        om = build_origin_map(i_content, "src.c.i")

        # DWARF evidence covers lines 1-5, each with count=1
        dwarf_evidence = {
            ("src.c", 1): 1, ("src.c", 2): 1, ("src.c", 3): 1,
            ("src.c", 4): 1, ("src.c", 5): 1,
        }
        # TS function spans only .i lines 1-3 (maps to src.c lines 1-3)
        ts_funcs = [
            _make_ts_func("src.c.i:1:3:h", "src.c.i", "partial", 1, 3),
        ]

        results = score_candidates(dwarf_evidence, ts_funcs, om)
        assert len(results) == 1
        assert results[0].overlap_count == 3
        assert results[0].total_count == 5
        assert results[0].overlap_ratio == 0.6
        assert results[0].gap_count == 2

    def test_dwarf_multiplicity_counted(self):
        """DWARF evidence with multiplicity > 1: full count is added, not 1.

        This validates the consumed-set deduplication semantics: each unique
        origin (file, line) is counted at most once, but its full DWARF
        multiplicity is added to overlap_count.
        """
        i_content = '# 1 "m.c"\nstmt_a;\nstmt_b;\n'
        om = build_origin_map(i_content, "m.c.i")

        # Line 1 has multiplicity 3 (3 machine instructions)
        dwarf_evidence = {("m.c", 1): 3, ("m.c", 2): 1}
        ts_funcs = [
            _make_ts_func("m.c.i:1:1:h", "m.c.i", "fn", 1, 1),
        ]

        results = score_candidates(dwarf_evidence, ts_funcs, om)
        assert len(results) == 1
        # overlap_count should be 3 (full multiplicity), not 1
        assert results[0].overlap_count == 3
        assert results[0].total_count == 4  # 3 + 1
        assert results[0].gap_count == 1


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

    def test_below_min_overlap_with_candidate(self):
        """Candidate exists but overlap_count < min_overlap_lines → NO_CANDIDATES."""
        candidates = [
            CandidateResult(
                ts_func_id="a:1:5:h", tu_path="a", function_name="f",
                context_hash="h", overlap_count=2, total_count=5,
                overlap_ratio=0.4, gap_count=3, span_size=5, start_byte=0,
            ),
        ]
        best, ties, reasons = select_best(candidates, 0.7, 0.02, min_overlap_lines=3)
        assert best is None
        assert "NO_CANDIDATES" in reasons

    def test_gap_count_tag(self):
        """gap_count > 0 emits PC_LINE_GAP alongside the primary reason."""
        candidates = [
            CandidateResult(
                ts_func_id="a:1:5:h", tu_path="a", function_name="f",
                context_hash="h", overlap_count=4, total_count=5,
                overlap_ratio=0.8, gap_count=1, span_size=5, start_byte=0,
            ),
        ]
        best, ties, reasons = select_best(candidates, 0.7, 0.02, 1)
        assert best is not None
        assert "UNIQUE_BEST" in reasons
        assert "PC_LINE_GAP" in reasons

    def test_epsilon_boundary_exact_tie(self):
        """Candidates differing by just under epsilon → NEAR_TIE detected.

        Due to IEEE 754, ``1.0 - 0.02`` is not exactly ``0.02`` away from
        ``1.0``.  We use ``0.981`` (within epsilon = 0.02 of 1.0) to test
        the boundary without floating-point edge effects.
        """
        eps = 0.02
        candidates = [
            CandidateResult(
                ts_func_id="a:1:5:h1", tu_path="a.i", function_name="f1",
                context_hash="h1", overlap_count=5, total_count=5,
                overlap_ratio=1.0, gap_count=0, span_size=5, start_byte=0,
            ),
            CandidateResult(
                ts_func_id="b:1:5:h2", tu_path="b.i", function_name="f2",
                context_hash="h2", overlap_count=5, total_count=5,
                overlap_ratio=0.981, gap_count=0, span_size=5, start_byte=0,
            ),
        ]
        # 1.0 - 0.981 = 0.019 < eps → near-tie
        best, ties, reasons = select_best(candidates, 0.7, eps, 1)
        assert len(ties) == 1
        assert "NEAR_TIE" in reasons

    def test_epsilon_boundary_no_tie(self):
        """Candidates differing by epsilon + 0.001 → no NEAR_TIE."""
        eps = 0.02
        candidates = [
            CandidateResult(
                ts_func_id="a:1:5:h1", tu_path="a.i", function_name="f1",
                context_hash="h1", overlap_count=5, total_count=5,
                overlap_ratio=1.0, gap_count=0, span_size=5, start_byte=0,
            ),
            CandidateResult(
                ts_func_id="b:1:5:h2", tu_path="b.i", function_name="f2",
                context_hash="h2", overlap_count=5, total_count=5,
                overlap_ratio=1.0 - eps - 0.001, gap_count=0, span_size=5,
                start_byte=0,
            ),
        ]
        best, ties, reasons = select_best(candidates, 0.7, eps, 1)
        assert len(ties) == 0
        assert "NEAR_TIE" not in reasons
        assert "UNIQUE_BEST" in reasons


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
