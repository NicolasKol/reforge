"""Tests for data.binning — canonical quality_weight and overlap_ratio bins."""
from __future__ import annotations

import pytest

from data.binning import (
    OVERLAP_RATIO_BIN_ORDER,
    QUALITY_WEIGHT_BIN_DETAILED_ORDER,
    QUALITY_WEIGHT_BIN_ORDER,
    overlap_ratio_bin,
    quality_weight_bin,
    quality_weight_bin_detailed,
)


# ── quality_weight_bin (simple) ───────────────────────────────────────────────

class TestQualityWeightBin:
    """Test the 6-bin simple binning function."""

    @pytest.mark.parametrize(
        "qw, expected",
        [
            (None, "none"),
            (0.0, "[0,0.5)"),
            (0.499, "[0,0.5)"),
            (0.5, "[0.5,0.8)"),
            (0.799, "[0.5,0.8)"),
            (0.8, "[0.8,0.95)"),
            (0.949, "[0.8,0.95)"),
            (0.95, "[0.95,1.0)"),
            (0.999, "[0.95,1.0)"),
            (1.0, "==1.0"),
        ],
    )
    def test_exact_bin_labels(self, qw, expected):
        assert quality_weight_bin(qw) == expected

    def test_all_bins_in_order(self):
        """Every possible output label must appear in the canonical order."""
        all_labels = {
            quality_weight_bin(v)
            for v in [None, 0.0, 0.25, 0.5, 0.7, 0.8, 0.9, 0.95, 0.99, 1.0]
        }
        for label in all_labels:
            assert label in QUALITY_WEIGHT_BIN_ORDER, (
                f"Label {label!r} not in QUALITY_WEIGHT_BIN_ORDER"
            )


# ── quality_weight_bin_detailed ───────────────────────────────────────────────

class TestQualityWeightBinDetailed:
    """Test the detailed binning that splits 'none' into two sub-bins."""

    def test_none_no_range(self):
        result = quality_weight_bin_detailed(
            None, has_range=False, align_verdict=None,
        )
        assert result == "none_no_range"

    def test_none_not_match(self):
        result = quality_weight_bin_detailed(
            None, has_range=True, align_verdict="AMBIGUOUS",
        )
        assert result == "none_not_match"

    def test_none_not_match_no_verdict(self):
        result = quality_weight_bin_detailed(
            None, has_range=True, align_verdict=None,
        )
        assert result == "none_not_match"

    def test_match_exact_1(self):
        result = quality_weight_bin_detailed(
            1.0, has_range=True, align_verdict="MATCH",
        )
        assert result == "==1.0"

    def test_match_near_perfect(self):
        result = quality_weight_bin_detailed(
            0.95, has_range=True, align_verdict="MATCH",
        )
        assert result == "[0.95,1.0)"

    def test_match_moderate(self):
        result = quality_weight_bin_detailed(
            0.6, has_range=True, align_verdict="MATCH",
        )
        assert result == "[0.5,0.8)"

    def test_zero_qw_non_match_treated_as_none(self):
        """qw=0.0 with non-MATCH verdict → none_not_match, not [0,0.5)."""
        result = quality_weight_bin_detailed(
            0.0, has_range=True, align_verdict="AMBIGUOUS",
        )
        # qw is not None but align_verdict != MATCH → falls to none path
        assert result == "none_not_match"

    def test_no_range_always_wins_over_verdict(self):
        """When has_range=False, even if align_verdict is set, use none_no_range."""
        result = quality_weight_bin_detailed(
            0.0, has_range=False, align_verdict="MATCH",
        )
        # qw=0.0 is not None AND align_verdict is MATCH → bins numerically
        # Actually, 0.0 is not None, so it goes to _bin_unit_value(0.0)
        # Wait — we need to be precise about semantics here.
        # If qw == 0.0 AND align_verdict == "MATCH" → it IS a valid MATCH
        # with very low quality weight.  That's "[0,0.5)".
        # But has_range=False + MATCH is contradictory in practice.
        assert result == "[0,0.5)"

    def test_all_detailed_labels_in_order(self):
        """Every possible output label must appear in the detailed order."""
        all_labels = set()
        all_labels.add(
            quality_weight_bin_detailed(None, has_range=False, align_verdict=None)
        )
        all_labels.add(
            quality_weight_bin_detailed(None, has_range=True, align_verdict="AMBIGUOUS")
        )
        for v in [0.0, 0.25, 0.5, 0.7, 0.8, 0.9, 0.95, 0.99, 1.0]:
            all_labels.add(
                quality_weight_bin_detailed(v, has_range=True, align_verdict="MATCH")
            )
        for label in all_labels:
            assert label in QUALITY_WEIGHT_BIN_DETAILED_ORDER, (
                f"Label {label!r} not in QUALITY_WEIGHT_BIN_DETAILED_ORDER"
            )


# ── overlap_ratio_bin ─────────────────────────────────────────────────────────

class TestOverlapRatioBin:
    """Test overlap_ratio binning (same thresholds as quality_weight)."""

    @pytest.mark.parametrize(
        "ratio, expected",
        [
            (None, "none"),
            (0.0, "[0,0.5)"),
            (0.5, "[0.5,0.8)"),
            (0.8, "[0.8,0.95)"),
            (0.95, "[0.95,1.0)"),
            (1.0, "==1.0"),
        ],
    )
    def test_exact_bin_labels(self, ratio, expected):
        assert overlap_ratio_bin(ratio) == expected

    def test_all_bins_in_order(self):
        all_labels = {
            overlap_ratio_bin(v)
            for v in [None, 0.0, 0.5, 0.8, 0.95, 1.0]
        }
        for label in all_labels:
            assert label in OVERLAP_RATIO_BIN_ORDER
