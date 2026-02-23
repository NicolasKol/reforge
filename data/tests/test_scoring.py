"""Tests for data.scoring — deterministic function-naming scorer."""
from __future__ import annotations

import pytest

from data.scoring import (
    SCORER_VERSION,
    ScoredRow,
    exact_match_norm,
    is_trivial_prediction,
    normalize_and_tokenize,
    score_experiment,
    score_row,
    token_f1,
    token_precision,
    token_recall,
)


# ═══════════════════════════════════════════════════════════════════════════════
# normalize_and_tokenize
# ═══════════════════════════════════════════════════════════════════════════════


class TestNormalizeAndTokenize:
    """Tokeniser must handle snake_case, camelCase, and digit boundaries."""

    def test_snake_case(self):
        assert normalize_and_tokenize("parse_header") == ["parse", "header"]

    def test_camel_case(self):
        assert normalize_and_tokenize("parseHeader") == ["parse", "header"]

    def test_pascal_case(self):
        assert normalize_and_tokenize("ParseHeader") == ["parse", "header"]

    def test_digit_boundary(self):
        assert normalize_and_tokenize("calc2sum") == ["calc", "2", "sum"]

    def test_leading_trailing_underscores(self):
        assert normalize_and_tokenize("__my_func__") == ["my", "func"]

    def test_kebab_case(self):
        assert normalize_and_tokenize("parse-header") == ["parse", "header"]

    def test_mixed_case_digits(self):
        assert normalize_and_tokenize("getItem3Count") == [
            "get", "item", "3", "count",
        ]

    def test_all_caps_acronym(self):
        # "HTTPParser" → "http", "parser"
        result = normalize_and_tokenize("HTTPParser")
        assert result == ["http", "parser"]

    def test_empty(self):
        assert normalize_and_tokenize("") == []

    def test_single_word(self):
        assert normalize_and_tokenize("main") == ["main"]


# ═══════════════════════════════════════════════════════════════════════════════
# exact_match_norm
# ═══════════════════════════════════════════════════════════════════════════════


class TestExactMatchNorm:
    def test_identical(self):
        assert exact_match_norm("parse_header", "parse_header") is True

    def test_case_insensitive(self):
        assert exact_match_norm("Parse_Header", "parse_header") is True

    def test_camel_vs_snake(self):
        assert exact_match_norm("parseHeader", "parse_header") is True

    def test_different(self):
        assert exact_match_norm("parse_header", "calculate_sum") is False

    def test_empty_both(self):
        assert exact_match_norm("", "") is True


# ═══════════════════════════════════════════════════════════════════════════════
# token_precision / token_recall / token_f1
# ═══════════════════════════════════════════════════════════════════════════════


class TestTokenMetrics:
    def test_f1_perfect(self):
        assert token_f1("parse_header", "parse_header") == 1.0

    def test_f1_zero(self):
        assert token_f1("foo_bar", "baz_qux") == 0.0

    def test_f1_partial(self):
        # "array_min" tokens: {array, min}
        # "find_minimum" tokens: {find, minimum}
        # intersection = {} → F1 = 0
        assert token_f1("array_min", "find_minimum") == 0.0

    def test_f1_overlap(self):
        # "array_min" tokens: {array, min}
        # "min_array_value" tokens: {min, array, value}
        # intersection = {array, min} → P = 2/2 = 1.0, R = 2/3 ≈ 0.667
        f1 = token_f1("array_min", "min_array_value")
        assert 0.79 < f1 < 0.81  # 2*1.0*0.667 / (1.0+0.667) ≈ 0.8

    def test_precision_empty_pred(self):
        assert token_precision("", "parse_header") == 0.0

    def test_recall_empty_gt(self):
        assert token_recall("parse_header", "") == 0.0

    def test_precision_all_correct(self):
        assert token_precision("parse_header", "parse_header_extra") == 1.0

    def test_recall_missing_tokens(self):
        # pred={parse, header}, gt={parse, header, extra}
        assert abs(token_recall("parse_header", "parse_header_extra") - 2 / 3) < 1e-9


# ═══════════════════════════════════════════════════════════════════════════════
# is_trivial_prediction
# ═══════════════════════════════════════════════════════════════════════════════


class TestIsTrivialPrediction:
    @pytest.mark.parametrize(
        "name",
        [
            None,
            "",
            "   ",
            "unknown",
            "func",
            "function",
            "FUN_00401000",
            "sub_00401a2f",
            "0x00401000",
            "fcn.00401000",
        ],
    )
    def test_trivial(self, name):
        assert is_trivial_prediction(name) is True

    @pytest.mark.parametrize(
        "name",
        [
            "parse_header",
            "calculate_sum",
            "processBuffer",
            "main",
            "init_system",
        ],
    )
    def test_not_trivial(self, name):
        assert is_trivial_prediction(name) is False


# ═══════════════════════════════════════════════════════════════════════════════
# score_row
# ═══════════════════════════════════════════════════════════════════════════════


class TestScoreRow:
    def test_scorer_version_present(self):
        s = score_row("a", "b")
        assert s.scorer_version == SCORER_VERSION

    def test_returns_scored_row(self):
        s = score_row("parse_header", "parse_header")
        assert isinstance(s, ScoredRow)
        assert s.exact_match_norm is True
        assert s.token_f1 == 1.0
        assert s.is_trivial_prediction is False

    def test_none_inputs(self):
        s = score_row(None, None) #type: ignore
        assert s.exact_match_norm is True  # both empty → match
        assert s.is_trivial_prediction is True

    def test_determinism(self):
        """Same input must produce identical output across 100 iterations."""
        results = [score_row("parseHeader", "parse_header") for _ in range(100)]
        first = results[0].model_dump()
        for r in results[1:]:
            assert r.model_dump() == first

    def test_scorer_does_not_read_prompt(self):
        """score_row signature only accepts (predicted, ground_truth)."""
        import inspect
        sig = inspect.signature(score_row)
        params = list(sig.parameters.keys())
        assert params == ["predicted", "ground_truth"], (
            f"score_row should only take predicted/ground_truth, got {params}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# score_experiment (batch)
# ═══════════════════════════════════════════════════════════════════════════════


class TestScoreExperiment:
    def test_enriches_rows(self):
        rows = [
            {
                "predicted_name": "parse_header",
                "ground_truth_name": "parse_header",
                "other_field": 42,
            },
            {
                "predicted_name": "FUN_00401000",
                "ground_truth_name": "calculate_sum",
                "other_field": 99,
            },
        ]
        scored = score_experiment(rows)
        assert len(scored) == 2

        # First row: exact match
        assert scored[0]["exact_match_norm"] is True
        assert scored[0]["is_trivial_prediction"] is False
        assert scored[0]["other_field"] == 42  # preserved

        # Second row: trivial prediction, no match
        assert scored[1]["exact_match_norm"] is False
        assert scored[1]["is_trivial_prediction"] is True
        assert scored[1]["scorer_version"] == SCORER_VERSION

    def test_does_not_mutate_input(self):
        rows = [{"predicted_name": "a", "ground_truth_name": "b"}]
        original_keys = set(rows[0].keys())
        score_experiment(rows)
        assert set(rows[0].keys()) == original_keys

    def test_empty(self):
        assert score_experiment([]) == []
