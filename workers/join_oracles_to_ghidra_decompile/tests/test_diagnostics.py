"""Tests for core.diagnostics — noise tags, high-confidence, report."""
from __future__ import annotations

from join_oracles_to_ghidra_decompile.core.address_join import (
    join_dwarf_to_ghidra,
)
from join_oracles_to_ghidra_decompile.core.build_context import (
    BuildContext,
)
from join_oracles_to_ghidra_decompile.core.diagnostics import (
    build_join_report,
    build_joined_function_rows,
    build_variable_stubs,
)
from join_oracles_to_ghidra_decompile.core.function_table import (
    apply_eligibility,
    build_dwarf_function_table,
    build_ghidra_function_table,
)
from join_oracles_to_ghidra_decompile.core.invariants import (
    check_report_invariants,
)
from join_oracles_to_ghidra_decompile.io.schema import (
    JoinedFunctionRow,
    JoinReport,
)
from join_oracles_to_ghidra_decompile.policy.profile import (
    JoinOraclesGhidraProfile,
)
from join_oracles_to_ghidra_decompile.tests.conftest import TEST_SHA256


def _make_ctx() -> BuildContext:
    return BuildContext(
        binary_sha256=TEST_SHA256,
        job_id="job-42",
        test_case="math_recurse",
        opt="O0",
        variant="stripped",
        builder_profile_id="gcc-O0O1O2O3",
    )


def _run_full_join(oracle_functions, alignment_pairs,
                   ghidra_functions, ghidra_cfg, ghidra_variables):
    profile = JoinOraclesGhidraProfile.v1()
    dwarf_table = build_dwarf_function_table(oracle_functions, alignment_pairs)
    apply_eligibility(dwarf_table, profile.aux_function_names)
    ghidra_table, interval_index = build_ghidra_function_table(
        ghidra_functions, ghidra_cfg, ghidra_variables,
    )
    join_results = join_dwarf_to_ghidra(
        dwarf_table, ghidra_table, interval_index, profile,
    )
    rows = build_joined_function_rows(join_results, _make_ctx(), profile)
    return rows, profile


class TestJoinedFunctionRows:
    """Test output row construction."""

    def test_row_count(self, oracle_functions, alignment_pairs,
                       ghidra_functions, ghidra_cfg, ghidra_variables):
        rows, _ = _run_full_join(
            oracle_functions, alignment_pairs,
            ghidra_functions, ghidra_cfg, ghidra_variables,
        )
        assert len(rows) == 4

    def test_provenance_fields(self, oracle_functions, alignment_pairs,
                               ghidra_functions, ghidra_cfg, ghidra_variables):
        rows, _ = _run_full_join(
            oracle_functions, alignment_pairs,
            ghidra_functions, ghidra_cfg, ghidra_variables,
        )
        for row in rows:
            assert row.binary_sha256 == TEST_SHA256
            assert row.job_id == "job-42"
            assert row.test_case == "math_recurse"

    def test_high_confidence_add(self, oracle_functions, alignment_pairs,
                                  ghidra_functions, ghidra_cfg, ghidra_variables):
        """'add' has ACCEPT + MATCH(1 cand, ratio=1.0) + JOINED_STRONG + HIGH cfg."""
        rows, _ = _run_full_join(
            oracle_functions, alignment_pairs,
            ghidra_functions, ghidra_cfg, ghidra_variables,
        )
        by_fid = {r.dwarf_function_id: r for r in rows}
        r = by_fid["cu0:0x100"]
        assert r.is_high_confidence is True

    def test_not_high_confidence_warn(self, oracle_functions, alignment_pairs,
                                       ghidra_functions, ghidra_cfg, ghidra_variables):
        """'helper' has WARN oracle → not high-confidence."""
        rows, _ = _run_full_join(
            oracle_functions, alignment_pairs,
            ghidra_functions, ghidra_cfg, ghidra_variables,
        )
        by_fid = {r.dwarf_function_id: r for r in rows}
        r = by_fid["cu0:0x300"]
        assert r.is_high_confidence is False

    def test_not_high_confidence_reject(self, oracle_functions, alignment_pairs,
                                         ghidra_functions, ghidra_cfg, ghidra_variables):
        """REJECT function with no ranges → NO_RANGE exclusion, not non-target."""
        rows, _ = _run_full_join(
            oracle_functions, alignment_pairs,
            ghidra_functions, ghidra_cfg, ghidra_variables,
        )
        by_fid = {r.dwarf_function_id: r for r in rows}
        r = by_fid["cu0:0x400"]
        assert r.is_high_confidence is False
        # Rangeless functions are excluded as NO_RANGE, not NON_TARGET
        assert r.is_non_target is False
        assert r.exclusion_reason == "NO_RANGE"

    def test_no_range_row_present(self, oracle_functions, alignment_pairs,
                                   ghidra_functions, ghidra_cfg, ghidra_variables):
        """NO_RANGE function must be present with ghidra_func_id = None."""
        rows, _ = _run_full_join(
            oracle_functions, alignment_pairs,
            ghidra_functions, ghidra_cfg, ghidra_variables,
        )
        by_fid = {r.dwarf_function_id: r for r in rows}
        r = by_fid["cu0:0x400"]
        assert r.ghidra_match_kind == "NO_RANGE"
        assert r.ghidra_func_id is None


class TestManyToOne:
    """Test many-to-one / FAT_FUNCTION tagging."""

    def test_no_fat_in_fixture(self, oracle_functions, alignment_pairs,
                                ghidra_functions, ghidra_cfg, ghidra_variables):
        """With these fixtures, no two DWARF funcs map to same Ghidra."""
        rows, _ = _run_full_join(
            oracle_functions, alignment_pairs,
            ghidra_functions, ghidra_cfg, ghidra_variables,
        )
        for r in rows:
            if r.ghidra_func_id:
                assert r.n_dwarf_funcs_per_ghidra_func == 1
                assert r.fat_function_multi_dwarf is False


class TestVariableStubs:
    """Test variable join stub output."""

    def test_empty_stubs(self, oracle_functions, alignment_pairs,
                         ghidra_functions, ghidra_cfg, ghidra_variables):
        rows, _ = _run_full_join(
            oracle_functions, alignment_pairs,
            ghidra_functions, ghidra_cfg, ghidra_variables,
        )
        stubs = build_variable_stubs(rows)
        assert stubs == []


class TestJoinReport:
    """Test report assembly."""

    def test_report_yield(self, oracle_functions, alignment_pairs,
                           ghidra_functions, ghidra_cfg, ghidra_variables):
        rows, profile = _run_full_join(
            oracle_functions, alignment_pairs,
            ghidra_functions, ghidra_cfg, ghidra_variables,
        )
        report = build_join_report(rows, _make_ctx(), profile)

        assert isinstance(report, JoinReport)
        assert report.yield_counts.n_dwarf_funcs == 4
        assert report.yield_counts.n_no_range == 1
        assert report.yield_counts.n_joined_to_ghidra >= 2

    def test_report_high_confidence(self, oracle_functions, alignment_pairs,
                                     ghidra_functions, ghidra_cfg, ghidra_variables):
        rows, profile = _run_full_join(
            oracle_functions, alignment_pairs,
            ghidra_functions, ghidra_cfg, ghidra_variables,
        )
        report = build_join_report(rows, _make_ctx(), profile)

        # Denominator is now eligible_for_gold (2: add + multiply)
        assert report.high_confidence.total == 2
        # At least 'add' should be high-confidence
        assert report.high_confidence.high_confidence_count >= 1
        assert report.high_confidence.yield_rate > 0

    def test_report_variable_join_not_implemented(
        self, oracle_functions, alignment_pairs,
        ghidra_functions, ghidra_cfg, ghidra_variables,
    ):
        rows, profile = _run_full_join(
            oracle_functions, alignment_pairs,
            ghidra_functions, ghidra_cfg, ghidra_variables,
        )
        report = build_join_report(rows, _make_ctx(), profile)
        assert report.variable_join.implemented is False

    def test_report_match_kind_stratification(
        self, oracle_functions, alignment_pairs,
        ghidra_functions, ghidra_cfg, ghidra_variables,
    ):
        rows, profile = _run_full_join(
            oracle_functions, alignment_pairs,
            ghidra_functions, ghidra_cfg, ghidra_variables,
        )
        report = build_join_report(rows, _make_ctx(), profile)

        assert "NO_RANGE" in report.yield_by_match_kind
        # At least JOINED_STRONG should be present
        assert "JOINED_STRONG" in report.yield_by_match_kind

    def test_yield_by_align_verdict_no_range_not_conflated(
        self, oracle_functions, alignment_pairs,
        ghidra_functions, ghidra_cfg, ghidra_variables,
    ):
        """Regression: NO_RANGE rows must NOT appear as NON_TARGET in
        yield_by_align_verdict.  They must be bucketed under 'NO_RANGE'."""
        rows, profile = _run_full_join(
            oracle_functions, alignment_pairs,
            ghidra_functions, ghidra_cfg, ghidra_variables,
        )
        report = build_join_report(rows, _make_ctx(), profile)

        # Fixture has 1 NO_RANGE function, 0 real non-targets
        assert report.exclusion_summary.n_no_range == 1
        assert report.exclusion_summary.n_non_target == 0

        # yield_by_align_verdict must reflect exclusion_summary
        assert report.yield_by_align_verdict.get("NO_RANGE", 0) == 1
        assert report.yield_by_align_verdict.get("NON_TARGET", 0) == 0

    def test_report_passes_all_report_invariants(
        self, oracle_functions, alignment_pairs,
        ghidra_functions, ghidra_cfg, ghidra_variables,
    ):
        """The fixture pipeline report must pass all report-level invariants."""
        rows, profile = _run_full_join(
            oracle_functions, alignment_pairs,
            ghidra_functions, ghidra_cfg, ghidra_variables,
        )
        report = build_join_report(rows, _make_ctx(), profile)
        violations = check_report_invariants(report)
        assert violations == [], f"Report invariant violations: {violations}"
