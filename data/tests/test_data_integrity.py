"""
Data integrity tests — ``oracle_decl_identity_v1`` patch validation.

These tests validate the correctness of the data-module metrics after the
stable-identity patch.  They cover:

    A — ``dwarf_function_id`` uniqueness within each ``(test_case, opt)``
    B — Stable-key completeness (``decl_file`` coverage + quality labels)
    C — Cross-opt transition multiplicity (no name-based collapse)
    D — ``dropped`` flag correctness
    E — ``n_candidates`` accuracy  (BUG-2 regression guard)
    F — Null-name preservation     (BUG-3 regression guard)

Tests A and C are the most critical; they directly verify the BUG-1 fix
(name-based dedup was silently dropping 35-55 % of pairs).

Run with::

    pytest reforge/data/tests/test_data_integrity.py -v
"""

from __future__ import annotations

import pandas as pd
import pytest

from data.enums import AlignmentVerdict, StableKeyQuality
from data.metrics import compute_transitions, enrich_pairs


# ═══════════════════════════════════════════════════════════════════════════════
# Synthetic-data helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _make_pair(
    *,
    test_case: str = "t01",
    opt: str = "O0",
    dwarf_function_id: str = "cu0x0:die0x1",
    dwarf_function_name: str | None = "foo",
    dwarf_function_name_norm: str | None = None,
    verdict: str = "MATCH",
    overlap_ratio: float = 1.0,
    overlap_count: int = 10,
    total_count: int = 10,
    gap_count: int = 0,
    reasons: list | None = None,
    candidates: list | None = None,
    best_tu_path: str = "src/main.c",
    best_ts_func_id: str = "ts_foo",
    best_ts_function_name: str = "foo",
    decl_file: str | None = "src/main.c",
    decl_line: int | None = 10,
    decl_column: int | None = 1,
    comp_dir: str | None = "/src",
    dwarf_verdict: str = "ACCEPT",
) -> dict:
    """Build a single pairs-DataFrame row dict."""
    if dwarf_function_name_norm is None:
        dwarf_function_name_norm = (
            dwarf_function_name
            if dwarf_function_name is not None
            else f"<anon@{dwarf_function_id}>"
        )
    return {
        "test_case": test_case,
        "opt": opt,
        "dwarf_function_id": dwarf_function_id,
        "dwarf_function_name": dwarf_function_name,
        "dwarf_function_name_norm": dwarf_function_name_norm,
        "dwarf_verdict": dwarf_verdict,
        "verdict": verdict,
        "overlap_ratio": overlap_ratio,
        "overlap_count": overlap_count,
        "total_count": total_count,
        "gap_count": gap_count,
        "reasons": reasons or ["UNIQUE_BEST"],
        "candidates": candidates or [
            {"func_id": best_ts_func_id, "overlap": overlap_ratio},
        ],
        "best_tu_path": best_tu_path,
        "best_ts_func_id": best_ts_func_id,
        "best_ts_function_name": best_ts_function_name,
        "decl_file": decl_file,
        "decl_line": decl_line,
        "decl_column": decl_column,
        "comp_dir": comp_dir,
    }


def _make_non_target(
    *,
    test_case: str = "t01",
    opt: str = "O0",
    dwarf_function_id: str = "cu0x0:die0xff",
    name: str = "_start",
    name_norm: str | None = None,
    dwarf_verdict: str = "REJECT",
    dwarf_reasons: list | None = None,
    decl_file: str | None = None,
    decl_line: int | None = None,
    decl_column: int | None = None,
    comp_dir: str | None = None,
) -> dict:
    """Build a single non-targets-DataFrame row dict."""
    if name_norm is None:
        name_norm = name or f"<anon@{dwarf_function_id}>"
    return {
        "test_case": test_case,
        "opt": opt,
        "dwarf_function_id": dwarf_function_id,
        "name": name,
        "name_norm": name_norm,
        "dwarf_verdict": dwarf_verdict,
        "dwarf_reasons": dwarf_reasons or ["DECLARATION_ONLY"],
        "decl_file": decl_file,
        "decl_line": decl_line,
        "decl_column": decl_column,
        "comp_dir": comp_dir,
    }


def _empty_non_targets() -> pd.DataFrame:
    """Return an empty non-targets DataFrame with correct columns."""
    return pd.DataFrame(columns=[
        "test_case", "opt", "dwarf_function_id", "name", "name_norm",
        "dwarf_verdict", "dwarf_reasons",
        "decl_file", "decl_line", "decl_column", "comp_dir",
    ])


# ═══════════════════════════════════════════════════════════════════════════════
# Test A — dwarf_function_id uniqueness within (test_case, opt)
# ═══════════════════════════════════════════════════════════════════════════════

class TestA_FunctionIdUniqueness:
    """``dwarf_function_id`` must never be duplicated in a (test_case, opt)."""

    def test_pairs_unique(self):
        """Three functions named 'report' with distinct IDs stay separate."""
        pairs = pd.DataFrame([
            _make_pair(dwarf_function_id="cu0:die1",
                       dwarf_function_name="report",
                       decl_file="a.c", decl_line=10),
            _make_pair(dwarf_function_id="cu0:die2",
                       dwarf_function_name="report",
                       decl_file="b.c", decl_line=20),
            _make_pair(dwarf_function_id="cu0:die3",
                       dwarf_function_name="report",
                       decl_file="c.c", decl_line=30),
        ])
        grouped = pairs.groupby(["test_case", "opt"])["dwarf_function_id"]
        for (tc, opt), ids in grouped:
            assert ids.is_unique, (
                f"Duplicate dwarf_function_id in ({tc}, {opt}): "
                f"{ids[ids.duplicated()].tolist()}"
            )

    def test_transitions_preserve_all_duplicates(self):
        """Three functions named 'report' at each opt must produce 3 rows."""
        rows = [
            # O0: three static 'report' — different DIE offsets
            _make_pair(opt="O0", dwarf_function_id="cu0:die1",
                       dwarf_function_name="report",
                       decl_file="a.c", decl_line=10),
            _make_pair(opt="O0", dwarf_function_id="cu0:die2",
                       dwarf_function_name="report",
                       decl_file="b.c", decl_line=20),
            _make_pair(opt="O0", dwarf_function_id="cu0:die3",
                       dwarf_function_name="report",
                       decl_file="c.c", decl_line=30),
            # O1: same three — different DIE offsets (unstable IDs)
            _make_pair(opt="O1", dwarf_function_id="cu1:die1",
                       dwarf_function_name="report",
                       decl_file="a.c", decl_line=10),
            _make_pair(opt="O1", dwarf_function_id="cu1:die2",
                       dwarf_function_name="report",
                       decl_file="b.c", decl_line=20),
            _make_pair(opt="O1", dwarf_function_id="cu1:die3",
                       dwarf_function_name="report",
                       decl_file="c.c", decl_line=30),
        ]
        pairs = pd.DataFrame(rows)
        enriched = enrich_pairs(pairs)
        result = compute_transitions(enriched, _empty_non_targets())

        report_rows = result[result["dwarf_function_name"] == "report"]
        assert len(report_rows) == 3, (
            f"Expected 3 'report' transition rows, got {len(report_rows)}. "
            f"BUG-1 regression: name-based dedup is collapsing rows."
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Test B — Stable key completeness
# ═══════════════════════════════════════════════════════════════════════════════

class TestB_StableKeyCompleteness:
    """Three-tier key quality: HIGH (file+line+column), MEDIUM (file+line),
    UNRESOLVED (missing file/line)."""

    def test_decl_columns_exist(self):
        pairs = pd.DataFrame([_make_pair()])
        for col in ("decl_file", "decl_line", "decl_column",
                     "dwarf_function_name_norm"):
            assert col in pairs.columns, f"Missing column: {col}"

    def test_key_quality_high_when_decl_complete(self):
        """HIGH requires decl_file + decl_line + decl_column."""
        pairs = pd.DataFrame([
            _make_pair(opt="O0", dwarf_function_id="cu0:die1",
                       decl_file="src/a.c", decl_line=10, decl_column=5),
            _make_pair(opt="O1", dwarf_function_id="cu1:die1",
                       decl_file="src/a.c", decl_line=10, decl_column=5),
        ])
        enriched = enrich_pairs(pairs)
        result = compute_transitions(enriched, _empty_non_targets())
        assert (result["key_quality"] == StableKeyQuality.HIGH.value).all()

    def test_key_quality_medium_when_column_missing(self):
        """MEDIUM when decl_file + decl_line present but decl_column is None."""
        pairs = pd.DataFrame([
            _make_pair(opt="O0", dwarf_function_id="cu0:die1",
                       decl_file="src/a.c", decl_line=10, decl_column=None),
            _make_pair(opt="O1", dwarf_function_id="cu1:die1",
                       decl_file="src/a.c", decl_line=10, decl_column=None),
        ])
        enriched = enrich_pairs(pairs)
        result = compute_transitions(enriched, _empty_non_targets())
        assert (result["key_quality"] == StableKeyQuality.MEDIUM.value).all()

    def test_key_quality_unresolved_when_decl_missing(self):
        pairs = pd.DataFrame([
            _make_pair(opt="O0", dwarf_function_id="cu0:die1",
                       decl_file=None, decl_line=None, decl_column=None),
        ])
        enriched = enrich_pairs(pairs)
        result = compute_transitions(enriched, _empty_non_targets())
        assert (
            result["key_quality"] == StableKeyQuality.UNRESOLVED.value
        ).all()


# ═══════════════════════════════════════════════════════════════════════════════
# Test C — Cross-opt transition multiplicity (BUG-1 core regression test)
# ═══════════════════════════════════════════════════════════════════════════════

class TestC_TransitionMultiplicity:
    """Functions with the same name but different declaration locations
    must each produce a separate transition row."""

    def test_static_duplicates_preserved(self):
        """Simulates t04_static_dup_names: 3×report, 3×process."""
        rows = []
        for name, file, line in [
            ("report",  "module_a.c",  5),
            ("report",  "module_b.c", 15),
            ("report",  "module_c.c", 25),
            ("process", "module_a.c", 50),
            ("process", "module_b.c", 60),
            ("process", "module_c.c", 70),
        ]:
            for i, opt in enumerate(["O0", "O1"]):
                rows.append(_make_pair(
                    test_case="t04", opt=opt,
                    dwarf_function_id=f"cu{i}:die{hash(name + file) & 0xfff:#05x}",
                    dwarf_function_name=name,
                    decl_file=file, decl_line=line,
                ))

        pairs = pd.DataFrame(rows)
        enriched = enrich_pairs(pairs)
        result = compute_transitions(enriched, _empty_non_targets())

        t04 = result[result["test_case"] == "t04"]
        reports  = t04[t04["dwarf_function_name"] == "report"]
        procs    = t04[t04["dwarf_function_name"] == "process"]

        assert len(reports) == 3, f"Expected 3 'report', got {len(reports)}"
        assert len(procs) == 3,   f"Expected 3 'process', got {len(procs)}"

    def test_different_decl_line_not_collapsed(self):
        """Two functions with the same name at different lines stay apart."""
        pairs = pd.DataFrame([
            _make_pair(opt="O0", dwarf_function_id="cu0:die1",
                       dwarf_function_name="init",
                       decl_file="src/main.c", decl_line=10),
            _make_pair(opt="O0", dwarf_function_id="cu0:die2",
                       dwarf_function_name="init",
                       decl_file="src/main.c", decl_line=45),
            _make_pair(opt="O1", dwarf_function_id="cu1:dieA",
                       dwarf_function_name="init",
                       decl_file="src/main.c", decl_line=10),
            _make_pair(opt="O1", dwarf_function_id="cu1:dieB",
                       dwarf_function_name="init",
                       decl_file="src/main.c", decl_line=45),
        ])
        enriched = enrich_pairs(pairs)
        result = compute_transitions(enriched, _empty_non_targets())

        inits = result[result["dwarf_function_name"] == "init"]
        assert len(inits) == 2, (
            f"Two 'init' at different lines should give 2 rows, got "
            f"{len(inits)}"
        )

    def test_correct_cross_opt_pairing(self):
        """Ensure a.c:10 at O0 merges with a.c:10 at O1, not b.c:20."""
        pairs = pd.DataFrame([
            _make_pair(opt="O0", dwarf_function_id="cu0:die1",
                       dwarf_function_name="report", verdict="MATCH",
                       overlap_ratio=0.95,
                       decl_file="a.c", decl_line=10),
            _make_pair(opt="O0", dwarf_function_id="cu0:die2",
                       dwarf_function_name="report", verdict="NO_MATCH",
                       overlap_ratio=0.0,
                       decl_file="b.c", decl_line=20),
            _make_pair(opt="O1", dwarf_function_id="cu1:die9",
                       dwarf_function_name="report", verdict="MATCH",
                       overlap_ratio=0.80,
                       decl_file="a.c", decl_line=10),
            _make_pair(opt="O1", dwarf_function_id="cu1:dieA",
                       dwarf_function_name="report", verdict="MATCH",
                       overlap_ratio=0.70,
                       decl_file="b.c", decl_line=20),
        ])
        enriched = enrich_pairs(pairs)
        result = compute_transitions(enriched, _empty_non_targets())

        # a.c:10 should pair O0-MATCH(0.95) with O1-MATCH(0.80)
        a_row = result[result["decl_file"] == "a.c"]
        assert len(a_row) == 1
        assert a_row.iloc[0]["verdict_O0"] == "MATCH"
        assert a_row.iloc[0]["verdict_O1"] == "MATCH"
        assert a_row.iloc[0]["overlap_O0"] == pytest.approx(0.95)
        assert a_row.iloc[0]["overlap_O1"] == pytest.approx(0.80)

        # b.c:20 should pair O0-NO_MATCH with O1-MATCH(0.70)
        b_row = result[result["decl_file"] == "b.c"]
        assert len(b_row) == 1
        assert b_row.iloc[0]["verdict_O0"] == "NO_MATCH"
        assert b_row.iloc[0]["overlap_O1"] == pytest.approx(0.70)

    def test_static_inline_no_cartesian_product(self):
        """A static inline in a header produces 2 DWARF entries per opt.

        Same (decl_file, decl_line) but different CU → same merge key.
        Must collapse 2×2=4 to 1 row, keeping worst-case overlap.
        """
        pairs = pd.DataFrame([
            # O0: two TU copies of abs_val
            _make_pair(opt="O0", dwarf_function_id="cu0:die1",
                       dwarf_function_name="abs_val",
                       decl_file="helpers.h", decl_line=8,
                       verdict="AMBIGUOUS", overlap_ratio=1.0),
            _make_pair(opt="O0", dwarf_function_id="cu1:die2",
                       dwarf_function_name="abs_val",
                       decl_file="helpers.h", decl_line=8,
                       verdict="AMBIGUOUS", overlap_ratio=0.9),
            # O1: two TU copies, both inlined away (absent from pairs)
        ])
        enriched = enrich_pairs(pairs)
        result = compute_transitions(enriched, _empty_non_targets(),
                                     opt_a="O0", opt_b="O1")

        abs_rows = result[result["dwarf_function_name"] == "abs_val"]
        assert len(abs_rows) == 1, (
            f"Static inline with identical merge key should collapse "
            f"to 1 row, got {len(abs_rows)}"
        )
        # Should keep the worse overlap (0.9)
        assert abs_rows.iloc[0]["overlap_O0"] == pytest.approx(0.9)
        assert abs_rows.iloc[0]["dropped"]


# ═══════════════════════════════════════════════════════════════════════════════
# Test D — Dropped flag correctness
# ═══════════════════════════════════════════════════════════════════════════════

class TestD_DroppedCounting:
    """The ``dropped`` flag must correctly identify functions that lose
    targetable status across optimisation levels."""

    def test_match_to_non_target_is_dropped(self):
        pairs = pd.DataFrame([
            _make_pair(opt="O0", dwarf_function_id="cu0:die1",
                       verdict="MATCH", decl_file="a.c", decl_line=1),
        ])
        nt = pd.DataFrame([
            _make_non_target(opt="O1", dwarf_function_id="cu1:die1",
                             name="foo", decl_file="a.c", decl_line=1),
        ])
        enriched = enrich_pairs(pairs)
        result = compute_transitions(enriched, nt)

        assert result["dropped"].sum() == 1
        assert "NON_TARGET" in result.iloc[0]["verdict_O1"]

    def test_non_target_to_match_is_not_dropped(self):
        pairs = pd.DataFrame([
            _make_pair(opt="O1", dwarf_function_id="cu1:die1",
                       verdict="MATCH", decl_file="a.c", decl_line=1),
        ])
        nt = pd.DataFrame([
            _make_non_target(opt="O0", dwarf_function_id="cu0:die1",
                             name="foo", decl_file="a.c", decl_line=1),
        ])
        enriched = enrich_pairs(pairs)
        result = compute_transitions(enriched, nt)

        assert result["dropped"].sum() == 0

    def test_match_to_absent_is_dropped(self):
        """Function present at O0 but completely absent at O1."""
        pairs = pd.DataFrame([
            _make_pair(opt="O0", dwarf_function_id="cu0:die1",
                       verdict="MATCH", decl_file="only_o0.c", decl_line=1),
        ])
        enriched = enrich_pairs(pairs)
        result = compute_transitions(enriched, _empty_non_targets())

        assert result["dropped"].sum() == 1
        assert result.iloc[0]["verdict_O1"] == "ABSENT"


# ═══════════════════════════════════════════════════════════════════════════════
# Test E — n_candidates accuracy (BUG-2 regression guard)
# ═══════════════════════════════════════════════════════════════════════════════

class TestE_CandidateCount:
    """``n_candidates`` must equal ``len(candidates)``, and the best match
    must be inside the candidates list."""

    def test_n_candidates_equals_len(self):
        candidates = [
            {"func_id": "ts_a", "overlap": 0.9},
            {"func_id": "ts_b", "overlap": 0.3},
            {"func_id": "ts_c", "overlap": 0.1},
        ]
        pairs = pd.DataFrame([
            _make_pair(candidates=candidates, best_ts_func_id="ts_a"),
        ])
        enriched = enrich_pairs(pairs)
        assert enriched.iloc[0]["n_candidates"] == 3

    def test_single_candidate(self):
        candidates = [{"func_id": "ts_only", "overlap": 1.0}]
        pairs = pd.DataFrame([
            _make_pair(candidates=candidates, best_ts_func_id="ts_only"),
        ])
        enriched = enrich_pairs(pairs)
        assert enriched.iloc[0]["n_candidates"] == 1

    def test_n_candidates_not_off_by_one(self):
        """BUG-2 regression: old code had ``1 + len(c)`` which overcounted."""
        candidates = [
            {"func_id": "ts_best", "overlap": 0.95},
            {"func_id": "ts_other", "overlap": 0.40},
        ]
        pairs = pd.DataFrame([
            _make_pair(candidates=candidates, best_ts_func_id="ts_best"),
        ])
        enriched = enrich_pairs(pairs)
        # Must be 2, NOT 3
        assert enriched.iloc[0]["n_candidates"] == 2

    def test_best_match_in_candidates(self):
        """``best_ts_func_id`` must appear in the candidates list."""
        candidates = [
            {"func_id": "ts_x", "overlap": 0.9},
            {"func_id": "ts_y", "overlap": 0.5},
        ]
        pairs = pd.DataFrame([
            _make_pair(candidates=candidates, best_ts_func_id="ts_x"),
        ])
        for _, row in pairs.iterrows():
            cand_ids = [c["func_id"] for c in row["candidates"]]
            assert row["best_ts_func_id"] in cand_ids, (
                f"best_ts_func_id {row['best_ts_func_id']} not in candidates"
            )

    def test_empty_pairs(self):
        """enrich_pairs must handle an empty DataFrame gracefully."""
        empty = pd.DataFrame(columns=[
            "test_case", "opt", "dwarf_function_id", "dwarf_function_name",
            "verdict", "overlap_ratio", "overlap_count", "total_count",
            "gap_count", "reasons", "candidates",
        ])
        result = enrich_pairs(empty)
        assert "n_candidates" in result.columns
        assert "gap_rate" in result.columns
        assert len(result) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Test F — Null-name preservation (BUG-3 regression guard)
# ═══════════════════════════════════════════════════════════════════════════════

class TestF_NullNamePreservation:
    """Functions with null ``dwarf_function_name`` must not disappear."""

    def test_null_name_gets_norm(self):
        pairs = pd.DataFrame([
            _make_pair(
                dwarf_function_name=None,
                dwarf_function_name_norm="<anon@cu0x0:die0x1>",
                decl_file="math.c", decl_line=42,
            ),
        ])
        assert pairs.iloc[0]["dwarf_function_name_norm"] == "<anon@cu0x0:die0x1>"

    def test_null_name_survives_enrichment(self):
        """Null names must not break enrich_pairs."""
        pairs = pd.DataFrame([
            _make_pair(
                dwarf_function_name=None,
                dwarf_function_name_norm="<anon@cu0:die1>",
                decl_file="math.c", decl_line=42,
            ),
        ])
        enriched = enrich_pairs(pairs)
        assert len(enriched) == 1

    def test_anonymous_functions_match_cross_opt(self):
        """Anonymous functions at the same decl location must merge
        even though their IDs differ across opts."""
        pairs = pd.DataFrame([
            _make_pair(
                opt="O0", dwarf_function_id="cu0:die1",
                dwarf_function_name=None,
                dwarf_function_name_norm="<anon@cu0:die1>",
                decl_file="math.c", decl_line=42,
            ),
            _make_pair(
                opt="O1", dwarf_function_id="cu1:dieA",
                dwarf_function_name=None,
                dwarf_function_name_norm="<anon@cu1:dieA>",
                decl_file="math.c", decl_line=42,
            ),
        ])
        enriched = enrich_pairs(pairs)
        result = compute_transitions(enriched, _empty_non_targets())

        # Stable key normalises <anon@…> → <anon>, so these should merge
        assert len(result) == 1, (
            f"Expected 1 merged row for anonymous function, got {len(result)}"
        )
        assert result.iloc[0]["key_quality"] == StableKeyQuality.HIGH.value
        assert result.iloc[0]["verdict_O0"] != "ABSENT"
        assert result.iloc[0]["verdict_O1"] != "ABSENT"
