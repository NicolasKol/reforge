"""
Response parser for top-k LLM predictions.

Parses structured JSON responses from LLMs that return ranked candidate
function names.  Handles common failure modes gracefully:

1. Clean JSON → parse directly
2. JSON inside markdown code fences → extract and parse
3. JSON embedded in surrounding text → regex extract
4. Completely non-JSON → fall back to cleaned text as single prediction

Usage::

    from workers.llm.response_parser import parse_topk_response

    parsed = parse_topk_response('{"predictions": [{"name": "foo", "confidence": 0.9}]}')
    assert parsed.parse_ok is True
    assert parsed.predictions[0]["name"] == "foo"

    # Graceful degradation
    parsed = parse_topk_response("parse_header")
    assert parsed.parse_ok is False
    assert parsed.predictions[0]["name"] == "parse_header"
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Max candidates to keep (truncate longer lists)
MAX_K = 3


@dataclass
class ParsedResponse:
    """Result of parsing an LLM response for top-k predictions."""
    predictions: List[Dict[str, Any]]   # [{"name": str, "confidence": float}, ...]
    parse_ok: bool                       # True if valid JSON was extracted
    parse_error: Optional[str] = None    # Error message if parse_ok is False
    raw_text: str = ""                   # Original response text


# ── Cleaning helpers ──────────────────────────────────────────────────────────

# Patterns for extracting a name from noisy LLM output
_PREFIX_PATTERNS = [
    re.compile(r"^(?:the\s+)?(?:suggested\s+)?(?:function\s+)?name\s+(?:is|should\s+be|could\s+be)\s*:?\s*", re.IGNORECASE),
    re.compile(r"^```\s*", re.MULTILINE),
    re.compile(r"\s*```$", re.MULTILINE),
    re.compile(r"^[`\"']+|[`\"']+$"),
]

# Valid C identifier (snake_case)
_VALID_IDENT = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _clean_name(raw: str) -> str:
    """Clean a candidate name string: strip quotes, backticks, prefixes."""
    name = raw.strip()
    for pat in _PREFIX_PATTERNS:
        name = pat.sub("", name).strip()
    # Take only the first line / first word if multi-line
    name = name.split("\n")[0].strip()
    # If it still contains spaces, try to extract just the identifier
    if " " in name:
        # Look for a snake_case identifier in the text
        match = re.search(r"[a-zA-Z_][a-zA-Z0-9_]+", name)
        if match:
            name = match.group(0)
    # Strip trailing punctuation
    name = name.rstrip(".,;:!?")
    return name


def _validate_prediction(pred: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Validate and normalize a single prediction dict.

    Returns normalized dict or None if invalid.
    """
    if not isinstance(pred, dict):
        return None

    name = pred.get("name")
    if not name or not isinstance(name, str):
        return None

    name = _clean_name(name)
    if not name:
        return None

    confidence = pred.get("confidence", 0.5)
    try:
        confidence = float(confidence)
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = 0.5

    return {"name": name, "confidence": confidence}


def _extract_json_from_fences(text: str) -> Optional[str]:
    """Extract JSON from markdown code fences like ```json ... ```."""
    patterns = [
        re.compile(r"```json\s*\n?(.*?)\n?\s*```", re.DOTALL | re.IGNORECASE),
        re.compile(r"```\s*\n?(.*?)\n?\s*```", re.DOTALL),
    ]
    for pat in patterns:
        m = pat.search(text)
        if m:
            return m.group(1).strip()
    return None


def _extract_json_object(text: str) -> Optional[str]:
    """Extract the first JSON object {...} from text using brace matching."""
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape_next = False

    for i in range(start, len(text)):
        ch = text[i]
        if escape_next:
            escape_next = False
            continue
        if ch == "\\":
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]

    return None


def _parse_json_predictions(json_str: str) -> Optional[List[Dict[str, Any]]]:
    """Try to parse a JSON string into a predictions list.

    Handles both ``{"predictions": [...]}`` and bare ``[...]`` formats.
    """
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        return None

    # Handle {"predictions": [...]}
    if isinstance(data, dict):
        preds = data.get("predictions")
        if isinstance(preds, list):
            validated = [_validate_prediction(p) for p in preds]
            return [p for p in validated if p is not None]

        # Single prediction object: {"name": "...", "confidence": ...}
        if "name" in data:
            v = _validate_prediction(data)
            return [v] if v else None

    # Handle bare array: [{"name": "...", "confidence": ...}, ...]
    if isinstance(data, list):
        validated = [_validate_prediction(p) for p in data]
        return [p for p in validated if p is not None]

    return None


def parse_topk_response(response_text: str, k: int = MAX_K) -> ParsedResponse:
    """Parse an LLM response into top-k predictions.

    Tries increasingly lenient parsing strategies:

    1. Direct ``json.loads()`` on full response text
    2. Extract JSON from markdown code fences
    3. Extract first ``{...}`` block via brace matching
    4. Fall back: treat cleaned text as a single prediction

    Parameters
    ----------
    response_text : str
        Raw LLM response text.
    k : int
        Maximum number of predictions to return.

    Returns
    -------
    ParsedResponse
        Always returns at least one prediction (even if fallback).
    """
    raw = (response_text or "").strip()

    if not raw:
        return ParsedResponse(
            predictions=[{"name": "", "confidence": 0.0}],
            parse_ok=False,
            parse_error="empty_response",
            raw_text=raw,
        )

    # Strategy 1: Direct JSON parse
    preds = _parse_json_predictions(raw)
    if preds:
        return ParsedResponse(
            predictions=preds[:k],
            parse_ok=True,
            raw_text=raw,
        )

    # Strategy 2: Extract from code fences
    from_fence = _extract_json_from_fences(raw)
    if from_fence:
        preds = _parse_json_predictions(from_fence)
        if preds:
            return ParsedResponse(
                predictions=preds[:k],
                parse_ok=True,
                raw_text=raw,
            )

    # Strategy 3: Extract first JSON object
    json_obj = _extract_json_object(raw)
    if json_obj:
        preds = _parse_json_predictions(json_obj)
        if preds:
            return ParsedResponse(
                predictions=preds[:k],
                parse_ok=True,
                raw_text=raw,
            )

    # Strategy 4: Fallback — clean the raw text as a single name
    cleaned = _clean_name(raw)
    if not cleaned:
        cleaned = raw.split()[0] if raw.split() else ""

    return ParsedResponse(
        predictions=[{"name": cleaned, "confidence": 1.0}],
        parse_ok=False,
        parse_error="json_parse_failed",
        raw_text=raw,
    )
