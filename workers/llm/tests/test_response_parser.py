"""
Tests for the top-k response parser.

Covers all parsing strategies:
1. Clean JSON
2. JSON in code fences
3. JSON embedded in surrounding text
4. Single-name fallback
5. Edge cases (empty, malformed, extra keys)
"""
import pytest

from workers.llm.response_parser import (
    ParsedResponse,
    parse_topk_response,
    _clean_name,
    _validate_prediction,
    _extract_json_from_fences,
    _extract_json_object,
)


# ═══════════════════════════════════════════════════════════════════════════════
# _clean_name
# ═══════════════════════════════════════════════════════════════════════════════

class TestCleanName:
    def test_already_clean(self):
        assert _clean_name("parse_header") == "parse_header"

    def test_strip_backticks(self):
        assert _clean_name("`parse_header`") == "parse_header"

    def test_strip_quotes(self):
        assert _clean_name('"parse_header"') == "parse_header"
        assert _clean_name("'parse_header'") == "parse_header"

    def test_strip_prefix_text(self):
        assert _clean_name("The function name is: parse_header") == "parse_header"
        assert _clean_name("the suggested function name should be parse_header") == "parse_header"

    def test_multiline_takes_first(self):
        assert _clean_name("parse_header\nsome explanation") == "parse_header"

    def test_strip_trailing_punctuation(self):
        assert _clean_name("parse_header.") == "parse_header"
        assert _clean_name("parse_header,") == "parse_header"

    def test_extract_identifier_from_text(self):
        # If there's a space, extract the first C-style identifier (2+ chars)
        result = _clean_name("I think parse_header")
        assert result == "think"  # first match of [a-zA-Z_][a-zA-Z0-9_]+
        # When the identifier IS first, it gets picked
        result2 = _clean_name("parse_header is the name")
        assert result2 == "parse_header"


# ═══════════════════════════════════════════════════════════════════════════════
# _validate_prediction
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidatePrediction:
    def test_valid(self):
        result = _validate_prediction({"name": "parse_header", "confidence": 0.9})
        assert result == {"name": "parse_header", "confidence": 0.9}

    def test_missing_name(self):
        assert _validate_prediction({"confidence": 0.9}) is None

    def test_empty_name(self):
        assert _validate_prediction({"name": "", "confidence": 0.9}) is None

    def test_not_dict(self):
        assert _validate_prediction("parse_header") is None

    def test_confidence_clamped(self):
        result = _validate_prediction({"name": "foo", "confidence": 1.5})
        assert result["confidence"] == 1.0
        result = _validate_prediction({"name": "foo", "confidence": -0.5})
        assert result["confidence"] == 0.0

    def test_default_confidence(self):
        result = _validate_prediction({"name": "foo"})
        assert result["confidence"] == 0.5

    def test_invalid_confidence_type(self):
        result = _validate_prediction({"name": "foo", "confidence": "high"})
        assert result["confidence"] == 0.5

    def test_name_cleaned(self):
        result = _validate_prediction({"name": "`parse_header`", "confidence": 0.8})
        assert result["name"] == "parse_header"


# ═══════════════════════════════════════════════════════════════════════════════
# Strategy 1: Direct JSON parse
# ═══════════════════════════════════════════════════════════════════════════════

class TestDirectJSON:
    def test_clean_json(self):
        resp = '{"predictions": [{"name": "parse_header", "confidence": 0.9}, {"name": "read_input", "confidence": 0.6}, {"name": "process_data", "confidence": 0.3}]}'
        parsed = parse_topk_response(resp)
        assert parsed.parse_ok is True
        assert len(parsed.predictions) == 3
        assert parsed.predictions[0]["name"] == "parse_header"
        assert parsed.predictions[0]["confidence"] == 0.9
        assert parsed.predictions[2]["name"] == "process_data"

    def test_single_prediction_object(self):
        resp = '{"name": "parse_header", "confidence": 0.95}'
        parsed = parse_topk_response(resp)
        assert parsed.parse_ok is True
        assert len(parsed.predictions) == 1
        assert parsed.predictions[0]["name"] == "parse_header"

    def test_bare_array(self):
        resp = '[{"name": "a", "confidence": 0.9}, {"name": "b", "confidence": 0.5}]'
        parsed = parse_topk_response(resp)
        assert parsed.parse_ok is True
        assert len(parsed.predictions) == 2

    def test_truncated_to_k(self):
        resp = '{"predictions": [{"name": "a", "confidence": 0.9}, {"name": "b", "confidence": 0.7}, {"name": "c", "confidence": 0.5}, {"name": "d", "confidence": 0.3}, {"name": "e", "confidence": 0.1}]}'
        parsed = parse_topk_response(resp, k=3)
        assert len(parsed.predictions) == 3


# ═══════════════════════════════════════════════════════════════════════════════
# Strategy 2: JSON in code fences
# ═══════════════════════════════════════════════════════════════════════════════

class TestCodeFenceJSON:
    def test_json_fence(self):
        resp = 'Here is my answer:\n```json\n{"predictions": [{"name": "parse_header", "confidence": 0.9}]}\n```'
        parsed = parse_topk_response(resp)
        assert parsed.parse_ok is True
        assert parsed.predictions[0]["name"] == "parse_header"

    def test_bare_fence(self):
        resp = '```\n{"predictions": [{"name": "foo", "confidence": 0.8}]}\n```'
        parsed = parse_topk_response(resp)
        assert parsed.parse_ok is True
        assert parsed.predictions[0]["name"] == "foo"


# ═══════════════════════════════════════════════════════════════════════════════
# Strategy 3: JSON embedded in text
# ═══════════════════════════════════════════════════════════════════════════════

class TestEmbeddedJSON:
    def test_json_with_surrounding_text(self):
        resp = 'Based on my analysis, here is the result: {"predictions": [{"name": "calculate_sum", "confidence": 0.85}]} I hope this helps.'
        parsed = parse_topk_response(resp)
        assert parsed.parse_ok is True
        assert parsed.predictions[0]["name"] == "calculate_sum"


# ═══════════════════════════════════════════════════════════════════════════════
# Strategy 4: Fallback — single name
# ═══════════════════════════════════════════════════════════════════════════════

class TestFallback:
    def test_plain_name(self):
        parsed = parse_topk_response("parse_header")
        assert parsed.parse_ok is False
        assert parsed.parse_error == "json_parse_failed"
        assert len(parsed.predictions) == 1
        assert parsed.predictions[0]["name"] == "parse_header"
        assert parsed.predictions[0]["confidence"] == 1.0

    def test_name_with_explanation(self):
        parsed = parse_topk_response("The function name should be parse_header")
        assert parsed.parse_ok is False
        assert parsed.predictions[0]["name"] == "parse_header"

    def test_backtick_wrapped_name(self):
        parsed = parse_topk_response("`init_buffer`")
        assert parsed.parse_ok is False
        assert parsed.predictions[0]["name"] == "init_buffer"


# ═══════════════════════════════════════════════════════════════════════════════
# Edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_empty_string(self):
        parsed = parse_topk_response("")
        assert parsed.parse_ok is False
        assert parsed.parse_error == "empty_response"
        assert parsed.predictions[0]["name"] == ""

    def test_none_input(self):
        parsed = parse_topk_response(None)
        assert parsed.parse_ok is False
        assert parsed.parse_error == "empty_response"

    def test_whitespace_only(self):
        parsed = parse_topk_response("   \n\t  ")
        assert parsed.parse_ok is False
        assert parsed.parse_error == "empty_response"

    def test_malformed_json(self):
        parsed = parse_topk_response('{"predictions": [}')
        assert parsed.parse_ok is False
        assert parsed.parse_error == "json_parse_failed"

    def test_json_with_no_predictions_key(self):
        parsed = parse_topk_response('{"result": "parse_header"}')
        assert parsed.parse_ok is False

    def test_json_with_invalid_predictions(self):
        # All predictions fail validation → fallback
        parsed = parse_topk_response('{"predictions": [{"invalid": true}]}')
        assert parsed.parse_ok is False

    def test_raw_text_preserved(self):
        raw = "parse_header"
        parsed = parse_topk_response(raw)
        assert parsed.raw_text == raw

    def test_extra_keys_ignored(self):
        resp = '{"predictions": [{"name": "foo", "confidence": 0.9, "reasoning": "blah"}], "model": "test"}'
        parsed = parse_topk_response(resp)
        assert parsed.parse_ok is True
        assert parsed.predictions[0]["name"] == "foo"


# ═══════════════════════════════════════════════════════════════════════════════
# Helper function tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestExtractHelpers:
    def test_extract_json_from_fences_json_tag(self):
        text = '```json\n{"key": "value"}\n```'
        assert _extract_json_from_fences(text) == '{"key": "value"}'

    def test_extract_json_from_fences_no_fence(self):
        assert _extract_json_from_fences("no fences here") is None

    def test_extract_json_object_simple(self):
        text = 'prefix {"key": "val"} suffix'
        assert _extract_json_object(text) == '{"key": "val"}'

    def test_extract_json_object_nested(self):
        text = '{"outer": {"inner": "val"}}'
        assert _extract_json_object(text) == '{"outer": {"inner": "val"}}'

    def test_extract_json_object_with_string_braces(self):
        text = '{"name": "hello {world}"}'
        assert _extract_json_object(text) == '{"name": "hello {world}"}'

    def test_extract_json_object_none(self):
        assert _extract_json_object("no json here") is None
