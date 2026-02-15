"""
Metric-function tests — ``compute_verdict_rates`` and ``compute_reason_shift``.

Covers the two untested metric functions identified in the academic review
(review_data_module.md §8.2, revisions R3 and R4).

Run with::

    pytest data/tests/test_metrics.py -v
"""

from __future__ import annotations

import pandas as pd
import pytest

from data.metrics import compute_reason_shift, compute_verdict_rates


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _make_report_row(
    *,
    test_case: str = "t01",
    opt: str = "O0",
    oracle_accept: int = 5,
    oracle_warn: int = 3,
    oracle_reject: int = 2,
    oracle_total: int = 10,
    match: int = 4,
    ambiguous: int = 1,
    no_match: int = 2,
    non_target: int = 3,
    reason_UNIQUE_BEST: int = 4,
    reason_NEAR_TIE: int = 1,
    reason_NO_CANDIDATES: int = 2,
    **extra_reasons: int,
) -> dict:
    """Build a single report-level row dict."""
    row = {
        "test_case": test_case,
        "opt": opt,
        "oracle_accept": oracle_accept,
        "oracle_warn": oracle_warn,
        "oracle_reject": oracle_reject,
        "oracle_total": oracle_total,
        "match": match,
        "ambiguous": ambiguous,
        "no_match": no_match,
        "non_target": non_target,
        "reason_UNIQUE_BEST": reason_UNIQUE_BEST,
        "reason_NEAR_TIE": reason_NEAR_TIE,
        "reason_NO_CANDIDATES": reason_NO_CANDIDATES,
    }
    for k, v in extra_reasons.items():
        row[k] = v
    return row


# ═══════════════════════════════════════════════════════════════════════════════
# R3 — TestComputeVerdictRates
# ═══════════════════════════════════════════════════════════════════════════════

class TestComputeVerdictRates:
    """Tests for compute_verdict_rates (review R3)."""

    def test_normal_case(self):
        """Known counts produce exact expected rates."""
        df = pd.DataFrame([_make_report_row(
            oracle_accept=50, oracle_warn=30, oracle_reject=20, oracle_total=100,
            match=40, ambiguous=10, no_match=30, non_target=20,
        )])
        result = compute_verdict_rates(df)

        assert result["accept_rate"].iloc[0] == 50.0
        assert result["warn_rate"].iloc[0] == 30.0
        assert result["reject_rate"].iloc[0] == 20.0
        assert result["match_rate"].iloc[0] == 40.0
        assert result["ambiguous_rate"].iloc[0] == 10.0
        assert result["no_match_rate"].iloc[0] == 30.0
        assert result["non_target_rate"].iloc[0] == 20.0

    def test_zero_oracle_total(self):
        """Zero oracle_total produces 0% rates without division error."""
        df = pd.DataFrame([_make_report_row(
            oracle_accept=0, oracle_warn=0, oracle_reject=0, oracle_total=0,
            match=5, ambiguous=1, no_match=2, non_target=2,
        )])
        result = compute_verdict_rates(df)

        assert result["accept_rate"].iloc[0] == 0.0
        assert result["warn_rate"].iloc[0] == 0.0
        assert result["reject_rate"].iloc[0] == 0.0

    def test_zero_alignment_total(self):
        """Zero alignment total produces 0% rates without division error."""
        df = pd.DataFrame([_make_report_row(
            oracle_accept=5, oracle_warn=3, oracle_reject=2, oracle_total=10,
            match=0, ambiguous=0, no_match=0, non_target=0,
        )])
        result = compute_verdict_rates(df)

        assert result["match_rate"].iloc[0] == 0.0
        assert result["ambiguous_rate"].iloc[0] == 0.0
        assert result["no_match_rate"].iloc[0] == 0.0
        assert result["non_target_rate"].iloc[0] == 0.0

    def test_oracle_rates_sum_to_100(self):
        """Oracle rates must sum to exactly 100%."""
        df = pd.DataFrame([_make_report_row(
            oracle_accept=7, oracle_warn=2, oracle_reject=1, oracle_total=10,
        )])
        result = compute_verdict_rates(df)

        oracle_sum = (
            result["accept_rate"].iloc[0]
            + result["warn_rate"].iloc[0]
            + result["reject_rate"].iloc[0]
        )
        assert oracle_sum == pytest.approx(100.0)

    def test_alignment_rates_sum_to_100(self):
        """Alignment rates must sum to exactly 100%."""
        df = pd.DataFrame([_make_report_row(
            match=17, ambiguous=3, no_match=5, non_target=25,
        )])
        result = compute_verdict_rates(df)

        align_sum = (
            result["match_rate"].iloc[0]
            + result["ambiguous_rate"].iloc[0]
            + result["no_match_rate"].iloc[0]
            + result["non_target_rate"].iloc[0]
        )
        assert align_sum == pytest.approx(100.0)

    def test_multi_row(self):
        """Multiple rows are computed independently."""
        df = pd.DataFrame([
            _make_report_row(
                test_case="t01", opt="O0",
                oracle_accept=8, oracle_warn=1, oracle_reject=1, oracle_total=10,
                match=6, ambiguous=0, no_match=2, non_target=2,
            ),
            _make_report_row(
                test_case="t01", opt="O1",
                oracle_accept=6, oracle_warn=2, oracle_reject=2, oracle_total=10,
                match=4, ambiguous=1, no_match=3, non_target=2,
            ),
        ])
        result = compute_verdict_rates(df)

        assert result["accept_rate"].iloc[0] == 80.0
        assert result["accept_rate"].iloc[1] == 60.0
        assert result["match_rate"].iloc[0] == 60.0
        assert result["match_rate"].iloc[1] == 40.0


# ═══════════════════════════════════════════════════════════════════════════════
# R4 — TestComputeReasonShift
# ═══════════════════════════════════════════════════════════════════════════════

class TestComputeReasonShift:
    """Tests for compute_reason_shift (review R4)."""

    def test_basic_shift(self):
        """Known counts produce correct shares and delta_pp."""
        # O0: 10 aligned pairs, O1: 10 aligned pairs
        df = pd.DataFrame([
            _make_report_row(
                test_case="t01", opt="O0",
                match=6, ambiguous=2, no_match=2, non_target=5,
                reason_UNIQUE_BEST=6, reason_NEAR_TIE=2, reason_NO_CANDIDATES=2,
            ),
            _make_report_row(
                test_case="t01", opt="O1",
                match=4, ambiguous=3, no_match=3, non_target=5,
                reason_UNIQUE_BEST=4, reason_NEAR_TIE=3, reason_NO_CANDIDATES=3,
            ),
        ])
        result = compute_reason_shift(df, "O0", "O1")

        # 10 aligned pairs at each opt (match + ambiguous + no_match)
        ub = result[result["reason_raw"] == "reason_UNIQUE_BEST"].iloc[0]
        assert ub["count_O0"] == 6
        assert ub["count_O1"] == 4
        assert ub["share_O0"] == 60.0   # 6/10 * 100
        assert ub["share_O1"] == 40.0   # 4/10 * 100
        assert ub["delta_pp"] == -20.0  # 40 - 60

    def test_multi_reason_shares_exceed_100(self):
        """Shares can sum to > 100% when pairs carry multiple reason tags.

        This validates the 'prevalence rate' semantics: each share is the
        fraction of pairs carrying that tag, not a probability mass.
        """
        # 5 aligned pairs at O0. Reason counts sum to 8 (> 5) because
        # some pairs carry multiple tags.
        df = pd.DataFrame([
            _make_report_row(
                test_case="t01", opt="O0",
                match=2, ambiguous=2, no_match=1, non_target=0,
                reason_UNIQUE_BEST=2, reason_NEAR_TIE=2,
                reason_NO_CANDIDATES=1,
                reason_PC_LINE_GAP=3,  # additive tag on 3 of the 5 pairs
            ),
            _make_report_row(
                test_case="t01", opt="O1",
                match=2, ambiguous=2, no_match=1, non_target=0,
                reason_UNIQUE_BEST=2, reason_NEAR_TIE=2,
                reason_NO_CANDIDATES=1,
                reason_PC_LINE_GAP=3,
            ),
        ])
        result = compute_reason_shift(df, "O0", "O1")

        # Sum of shares at O0: (2+2+1+3)/5 * 100 = 160%
        total_share = result["share_O0"].sum()
        assert total_share > 100.0

    def test_top_k_folding(self):
        """Reasons beyond top_k are folded into an 'Other' row."""
        df = pd.DataFrame([
            _make_report_row(
                test_case="t01", opt="O0",
                match=10, ambiguous=5, no_match=5, non_target=0,
                reason_UNIQUE_BEST=10, reason_NEAR_TIE=5,
                reason_NO_CANDIDATES=3,
                reason_LOW_OVERLAP_RATIO=2,
            ),
            _make_report_row(
                test_case="t01", opt="O1",
                match=8, ambiguous=6, no_match=6, non_target=0,
                reason_UNIQUE_BEST=8, reason_NEAR_TIE=6,
                reason_NO_CANDIDATES=4,
                reason_LOW_OVERLAP_RATIO=2,
            ),
        ])
        result = compute_reason_shift(df, "O0", "O1", top_k=2)

        # top_k=2 keeps 2 reasons + Other
        assert len(result) == 3
        other = result[result["reason"] == "Other"]
        assert len(other) == 1
        # Other row sums the folded reasons
        assert other["count_O0"].iloc[0] > 0

    def test_missing_opt_raises(self):
        """Requesting an opt level not in data raises ValueError."""
        df = pd.DataFrame([_make_report_row(opt="O0")])
        with pytest.raises(ValueError, match="O3"):
            compute_reason_shift(df, "O0", "O3")

    def test_no_reason_columns(self):
        """DataFrame without reason_* columns returns empty DataFrame."""
        df = pd.DataFrame([{
            "test_case": "t01", "opt": "O0",
            "match": 5, "ambiguous": 1, "no_match": 2, "non_target": 2,
        }])
        result = compute_reason_shift(df, "O0", "O1")
        assert result.empty

    def test_zero_only_rows_filtered(self):
        """Reasons with 0 count at both opt levels are excluded."""
        df = pd.DataFrame([
            _make_report_row(
                test_case="t01", opt="O0",
                match=5, ambiguous=0, no_match=0, non_target=0,
                reason_UNIQUE_BEST=5, reason_NEAR_TIE=0,
                reason_NO_CANDIDATES=0,
            ),
            _make_report_row(
                test_case="t01", opt="O1",
                match=5, ambiguous=0, no_match=0, non_target=0,
                reason_UNIQUE_BEST=5, reason_NEAR_TIE=0,
                reason_NO_CANDIDATES=0,
            ),
        ])
        result = compute_reason_shift(df, "O0", "O1")

        # NEAR_TIE and NO_CANDIDATES are 0 at both levels → filtered out
        assert len(result) == 1
        assert result["reason_raw"].iloc[0] == "reason_UNIQUE_BEST"

    def test_macro_averaging_equal_weight(self):
        """Macro-averaging gives equal weight to each test case.

        t01 has 100 aligned pairs, t02 has 10.  Micro-averaging is dominated
        by t01; macro-averaging treats them equally.
        """
        df = pd.DataFrame([
            # t01: large test case — 100 aligned pairs, 80% UNIQUE_BEST
            _make_report_row(
                test_case="t01", opt="O0",
                match=80, ambiguous=10, no_match=10, non_target=0,
                reason_UNIQUE_BEST=80, reason_NEAR_TIE=10,
                reason_NO_CANDIDATES=10,
            ),
            _make_report_row(
                test_case="t01", opt="O1",
                match=80, ambiguous=10, no_match=10, non_target=0,
                reason_UNIQUE_BEST=80, reason_NEAR_TIE=10,
                reason_NO_CANDIDATES=10,
            ),
            # t02: small test case — 10 aligned pairs, 20% UNIQUE_BEST
            _make_report_row(
                test_case="t02", opt="O0",
                match=2, ambiguous=4, no_match=4, non_target=0,
                reason_UNIQUE_BEST=2, reason_NEAR_TIE=4,
                reason_NO_CANDIDATES=4,
            ),
            _make_report_row(
                test_case="t02", opt="O1",
                match=2, ambiguous=4, no_match=4, non_target=0,
                reason_UNIQUE_BEST=2, reason_NEAR_TIE=4,
                reason_NO_CANDIDATES=4,
            ),
        ])

        micro = compute_reason_shift(df, "O0", "O1", averaging="micro")
        macro = compute_reason_shift(df, "O0", "O1", averaging="macro")

        ub_micro = micro[micro["reason_raw"] == "reason_UNIQUE_BEST"]["share_O0"].iloc[0]
        ub_macro = macro[macro["reason_raw"] == "reason_UNIQUE_BEST"]["share_O0"].iloc[0]

        # Micro: (80+2)/(100+10)*100 = 74.55%
        assert ub_micro == pytest.approx(74.55, abs=0.1)
        # Macro: mean(80/100, 2/10)*100 = mean(80%, 20%) = 50%
        assert ub_macro == pytest.approx(50.0, abs=0.1)

    def test_macro_vs_micro_single_testcase(self):
        """With a single test case, micro and macro produce identical shares."""
        df = pd.DataFrame([
            _make_report_row(
                test_case="t01", opt="O0",
                match=10, ambiguous=3, no_match=7, non_target=0,
                reason_UNIQUE_BEST=10, reason_NEAR_TIE=3,
                reason_NO_CANDIDATES=7,
            ),
            _make_report_row(
                test_case="t01", opt="O1",
                match=8, ambiguous=5, no_match=7, non_target=0,
                reason_UNIQUE_BEST=8, reason_NEAR_TIE=5,
                reason_NO_CANDIDATES=7,
            ),
        ])

        micro = compute_reason_shift(df, "O0", "O1", averaging="micro")
        macro = compute_reason_shift(df, "O0", "O1", averaging="macro")

        # Same reasons, same order — compare shares
        micro_sorted = micro.sort_values("reason_raw").reset_index(drop=True)
        macro_sorted = macro.sort_values("reason_raw").reset_index(drop=True)

        for col in ("share_O0", "share_O1", "delta_pp"):
            for i in range(len(micro_sorted)):
                assert micro_sorted[col].iloc[i] == pytest.approx(
                    macro_sorted[col].iloc[i], abs=0.01
                ), f"Mismatch at row {i}, col {col}"

    def test_delta_pp_equals_share_difference(self):
        """delta_pp == share_{opt_b} - share_{opt_a} for every row."""
        df = pd.DataFrame([
            _make_report_row(
                test_case="t01", opt="O0",
                match=10, ambiguous=3, no_match=7, non_target=0,
                reason_UNIQUE_BEST=10, reason_NEAR_TIE=3,
                reason_NO_CANDIDATES=7,
            ),
            _make_report_row(
                test_case="t01", opt="O1",
                match=7, ambiguous=5, no_match=8, non_target=0,
                reason_UNIQUE_BEST=7, reason_NEAR_TIE=5,
                reason_NO_CANDIDATES=8,
            ),
        ])
        result = compute_reason_shift(df, "O0", "O1")

        for _, row in result.iterrows():
            expected = round(row["share_O1"] - row["share_O0"], 2)
            assert row["delta_pp"] == pytest.approx(expected, abs=0.01)
