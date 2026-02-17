"""
Deterministic scoring module for LLM function-naming experiments.

All metric computations are rule-based (regex tokenisation, set operations).
No ML models, no embeddings, no floating-point non-determinism beyond
standard IEEE 754 division.

Scorer version is tracked so that results scored with different logic
can be distinguished in analyses.

Usage::

    from data.scoring import score_row, score_experiment, SCORER_VERSION

    s = score_row("parse_header", "parseHeader")
    assert s.exact_match_norm is True
    assert s.token_f1 == 1.0
    assert s.scorer_version == SCORER_VERSION
"""

from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

log = logging.getLogger(__name__)

# Bump on ANY change to tokenisation, normalisation, or metric logic.
SCORER_VERSION = "1.0.0"


# ═══════════════════════════════════════════════════════════════════════════════
# Tokenisation & normalisation
# ═══════════════════════════════════════════════════════════════════════════════

# Regex that splits on:
#   - underscores / hyphens (snake_case, kebab-case)
#   - camelCase transitions  (lowerUpper)
#   - digit ↔ alpha boundary (calc2sum → calc, 2, sum)
_SPLIT_RE = re.compile(
    r"[_\-]+"                            # explicit separators
    r"|(?<=[a-z])(?=[A-Z])"              # camelCase: lower→Upper
    r"|(?<=[A-Z])(?=[A-Z][a-z])"         # ABCDef → ABC, Def
    r"|(?<=[a-zA-Z])(?=[0-9])"           # alpha→digit
    r"|(?<=[0-9])(?=[a-zA-Z])"           # digit→alpha
)


def normalize_and_tokenize(name: str) -> List[str]:
    """Split a function name into canonical lowercase tokens.

    Handles snake_case, camelCase, digit boundaries, and mixed styles.
    Deterministic and locale-independent.

    >>> normalize_and_tokenize("parseHeader")
    ['parse', 'header']
    >>> normalize_and_tokenize("calc2sum")
    ['calc', '2', 'sum']
    >>> normalize_and_tokenize("__my_func__")
    ['my', 'func']
    """
    if not name:
        return []
    tokens = _SPLIT_RE.split(name)
    return [t.lower() for t in tokens if t]


def _normalize_flat(name: str) -> str:
    """Lowercase, strip separators — for exact-match comparison."""
    return name.lower().replace("_", "").replace("-", "")


# ═══════════════════════════════════════════════════════════════════════════════
# Trivial prediction detection
# ═══════════════════════════════════════════════════════════════════════════════

_TRIVIAL_NAMES: frozenset[str] = frozenset({
    "",
    "unknown",
    "func",
    "function",
    "unnamed",
    "sub",
    "fn",
    "proc",
    "routine",
    "handler",
    "callback",
})

_TRIVIAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^fun_[0-9a-f]+$", re.IGNORECASE),       # FUN_00401000
    re.compile(r"^sub_[0-9a-f]+$", re.IGNORECASE),       # sub_00401000
    re.compile(r"^0x[0-9a-f]+$", re.IGNORECASE),         # 0x00401000
    re.compile(r"^fcn\.[0-9a-f]+$", re.IGNORECASE),      # fcn.00401000
    re.compile(r"^_*func_?[0-9]*_*$", re.IGNORECASE),    # func, func_1, __func__
)


def is_trivial_prediction(name: Optional[str]) -> bool:
    """Return True if *name* is an empty, placeholder, or address-like prediction.

    These are "non-answers" that should be flagged separately from genuine
    wrong predictions.

    >>> is_trivial_prediction("FUN_00401000")
    True
    >>> is_trivial_prediction("parse_header")
    False
    """
    if not name:
        return True
    stripped = name.strip()
    if not stripped:
        return True
    if stripped.lower() in _TRIVIAL_NAMES:
        return True
    return any(p.match(stripped) for p in _TRIVIAL_PATTERNS)


# ═══════════════════════════════════════════════════════════════════════════════
# Metric functions
# ═══════════════════════════════════════════════════════════════════════════════


def exact_match_norm(predicted: str, ground_truth: str) -> bool:
    """Normalised exact match — case-insensitive, separators stripped.

    >>> exact_match_norm("Parse_Header", "parseHeader")
    True
    """
    return _normalize_flat(predicted) == _normalize_flat(ground_truth)


def token_precision(predicted: str, ground_truth: str) -> float:
    r"""Fraction of predicted tokens found in the ground truth.

    $$\text{precision} = \frac{|P \cap G|}{|P|}$$
    """
    p_toks = set(normalize_and_tokenize(predicted))
    g_toks = set(normalize_and_tokenize(ground_truth))
    if not p_toks:
        return 0.0
    return len(p_toks & g_toks) / len(p_toks)


def token_recall(predicted: str, ground_truth: str) -> float:
    r"""Fraction of ground-truth tokens found in the prediction.

    $$\text{recall} = \frac{|P \cap G|}{|G|}$$
    """
    p_toks = set(normalize_and_tokenize(predicted))
    g_toks = set(normalize_and_tokenize(ground_truth))
    if not g_toks:
        return 0.0
    return len(p_toks & g_toks) / len(g_toks)


def token_f1(predicted: str, ground_truth: str) -> float:
    """Harmonic mean of token precision and recall."""
    p = token_precision(predicted, ground_truth)
    r = token_recall(predicted, ground_truth)
    if p + r == 0:
        return 0.0
    return 2 * p * r / (p + r)


# ═══════════════════════════════════════════════════════════════════════════════
# Scored row model
# ═══════════════════════════════════════════════════════════════════════════════


class ScoredRow(BaseModel):
    """Deterministic scoring output for one prediction."""

    model_config = ConfigDict(extra="ignore")

    exact_match_norm: bool
    token_precision: float
    token_recall: float
    token_f1: float
    is_trivial_prediction: bool
    scorer_version: str
    predicted_tokens: List[str]
    ground_truth_tokens: List[str]


def score_row(predicted: str, ground_truth: str) -> ScoredRow:
    """Score a single (predicted, ground_truth) name pair.

    This function reads ONLY these two strings — it never accesses
    ``prompt_text``, ``c_raw``, or any model-visible payload.
    """
    pred = predicted or ""
    gt = ground_truth or ""

    return ScoredRow(
        exact_match_norm=exact_match_norm(pred, gt),
        token_precision=token_precision(pred, gt),
        token_recall=token_recall(pred, gt),
        token_f1=token_f1(pred, gt),
        is_trivial_prediction=is_trivial_prediction(pred),
        scorer_version=SCORER_VERSION,
        predicted_tokens=normalize_and_tokenize(pred),
        ground_truth_tokens=normalize_and_tokenize(gt),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Batch scoring
# ═══════════════════════════════════════════════════════════════════════════════


def score_experiment(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Score all result rows, adding score fields to each dict.

    Each row must have ``predicted_name`` and ``ground_truth_name``.
    Returns a **new** list — the original dicts are not mutated.
    """
    scored: List[Dict[str, Any]] = []
    for row in rows:
        pred = row.get("predicted_name") or ""
        gt = row.get("ground_truth_name") or ""
        s = score_row(pred, gt)
        enriched = {**row, **s.model_dump()}
        scored.append(enriched)
    return scored


# ═══════════════════════════════════════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════════════════════════════════════


def _cli_main() -> None:  # pragma: no cover
    """Score an experiment's results JSONL and write scored output.

    Usage::

        python -m data.scoring \\
            --experiment exp01_funcnaming_gpt4omini_gold_O0 \\
            --artifacts-path ./docker/local-files/artifacts
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Score LLM experiment results",
    )
    parser.add_argument(
        "--experiment", required=True, help="Experiment ID",
    )
    parser.add_argument(
        "--artifacts-path",
        default="./docker/local-files/artifacts",
        help="Artifacts root directory",
    )
    args = parser.parse_args()

    results_dir = Path(args.artifacts_path) / "results" / "llm" / args.experiment
    results_path = results_dir / "results.jsonl"
    scored_path = results_dir / "scored_results.jsonl"

    if not results_path.exists():
        print(f"ERROR: {results_path} not found", file=sys.stderr)
        sys.exit(1)

    # Read
    rows: List[Dict[str, Any]] = []
    with open(results_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    if not rows:
        print("No rows to score.")
        sys.exit(0)

    # Score
    scored = score_experiment(rows)

    # Write
    with open(scored_path, "w", encoding="utf-8") as f:
        for row in scored:
            f.write(json.dumps(row, default=str) + "\n")

    # Summary
    n = len(scored)
    em = sum(1 for r in scored if r["exact_match_norm"])
    trivial = sum(1 for r in scored if r["is_trivial_prediction"])
    avg_f1 = sum(r["token_f1"] for r in scored) / n
    print(f"Scored {n} rows → {scored_path}")
    print(f"  Exact match (norm): {em}/{n}  ({em/n*100:.1f}%)")
    print(f"  Mean token F1:      {avg_f1:.3f}")
    print(f"  Trivial predictions: {trivial}/{n}")
    print(f"  Scorer version:     {SCORER_VERSION}")


if __name__ == "__main__":
    _cli_main()
