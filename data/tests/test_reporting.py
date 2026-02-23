"""Tests for data.reporting — stratified report generation."""
from __future__ import annotations

import pytest

from data.reporting import generate_report
from data.scoring import SCORER_VERSION


@pytest.fixture()
def scored_rows():
    """A small set of scored result rows for testing."""
    return [
        {
            "experiment_id": "exp01",
            "run_id": "run_001",
            "dwarf_function_id": "f1",
            "test_case": "t02",
            "opt": "O0",
            "predicted_name": "parse_header",
            "ground_truth_name": "parse_header",
            "exact_match_norm": True,
            "token_precision": 1.0,
            "token_recall": 1.0,
            "token_f1": 1.0,
            "is_trivial_prediction": False,
            "scorer_version": SCORER_VERSION,
        },
        {
            "experiment_id": "exp01",
            "run_id": "run_001",
            "dwarf_function_id": "f2",
            "test_case": "t02",
            "opt": "O0",
            "predicted_name": "calculate",
            "ground_truth_name": "calculate_sum",
            "exact_match_norm": False,
            "token_precision": 1.0,
            "token_recall": 0.5,
            "token_f1": 0.6667,
            "is_trivial_prediction": False,
            "scorer_version": SCORER_VERSION,
        },
        {
            "experiment_id": "exp01",
            "run_id": "run_001",
            "dwarf_function_id": "f3",
            "test_case": "t05",
            "opt": "O2",
            "predicted_name": "FUN_00401000",
            "ground_truth_name": "init_system",
            "exact_match_norm": False,
            "token_precision": 0.0,
            "token_recall": 0.0,
            "token_f1": 0.0,
            "is_trivial_prediction": True,
            "scorer_version": SCORER_VERSION,
        },
    ]


@pytest.fixture()
def function_metadata():
    """Post-hoc metadata for stratification."""
    return [
        {
            "dwarf_function_id": "f1",
            "test_case": "t02",
            "opt": "O0",
            "confidence_tier": "GOLD",
            "quality_weight": 1.0,
        },
        {
            "dwarf_function_id": "f2",
            "test_case": "t02",
            "opt": "O0",
            "confidence_tier": "GOLD",
            "quality_weight": 0.95,
        },
        {
            "dwarf_function_id": "f3",
            "test_case": "t05",
            "opt": "O2",
            "confidence_tier": "SILVER",
            "quality_weight": 0.7,
        },
    ]


class TestGenerateReport:
    def test_has_all_sections(self, scored_rows, function_metadata):
        report = generate_report("exp01", "run_001", scored_rows, function_metadata)
        assert "meta" in report
        assert "overall" in report
        assert "by_opt" in report
        assert "by_tier" in report
        assert "by_quality_weight_bin" in report
        assert "by_test_case" in report

    def test_n_sums_to_total(self, scored_rows, function_metadata):
        report = generate_report("exp01", "run_001", scored_rows, function_metadata)
        total = report["meta"]["n_total"]

        # Each stratification's N values should sum to total
        for section_key in ("by_opt", "by_tier", "by_test_case", "by_quality_weight_bin"):
            section_sum = sum(s["n"] for s in report[section_key])
            assert section_sum == total, (
                f"{section_key}: sum of n ({section_sum}) != n_total ({total})"
            )

    def test_exact_match_rate_range(self, scored_rows, function_metadata):
        report = generate_report("exp01", "run_001", scored_rows, function_metadata)
        overall_rate = report["overall"]["exact_match_rate"]
        assert 0.0 <= overall_rate <= 1.0

        for section_key in ("by_opt", "by_tier", "by_test_case"):
            for entry in report[section_key]:
                assert 0.0 <= entry["exact_match_rate"] <= 1.0

    def test_empty_experiment(self):
        report = generate_report("exp_empty", None, [], None)
        assert report["meta"]["n_total"] == 0
        assert report["overall"]["n"] == 0
        assert report["overall"]["exact_match_rate"] == 0.0
        assert report["by_opt"] == []
        assert report["by_tier"] == []

    def test_meta_fields(self, scored_rows, function_metadata):
        report = generate_report("exp01", "run_001", scored_rows, function_metadata)
        meta = report["meta"]
        assert meta["experiment_id"] == "exp01"
        assert meta["run_id"] == "run_001"
        assert meta["scorer_version"] == SCORER_VERSION
        assert "generated_at" in meta

    def test_without_metadata(self, scored_rows):
        """Report can be generated without function metadata — tiers default to UNKNOWN."""
        report = generate_report("exp01", "run_001", scored_rows, None)
        assert report["meta"]["n_total"] == 3
        # All rows should fall into UNKNOWN tier
        tier_names = {t["tier"] for t in report["by_tier"]}
        assert "UNKNOWN" in tier_names
