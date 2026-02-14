"""
Loader — read and validate all upstream inputs for the oracle↔Ghidra join.

Every load function returns raw dicts / lists of dicts.  Schema
validation happens at the Pydantic boundary (io/schema.py) when
outputs are constructed; the loader does minimal structural checks
and cross-validates ``binary_sha256`` across all sources.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Generic helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _load_json(path: Path) -> Any:
    """Read a JSON file and return the parsed object."""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _load_jsonl(path: Path) -> List[dict]:
    """Read a JSONL file and return a list of dicts."""
    rows: List[dict] = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                log.warning("JSONL parse error at %s:%d — %s", path, lineno, exc)
    return rows


# ═══════════════════════════════════════════════════════════════════════════════
# Build receipt
# ═══════════════════════════════════════════════════════════════════════════════

def load_build_receipt(receipt_path: Path) -> dict:
    """Load ``build_receipt.json`` and return the raw dict."""
    data = _load_json(receipt_path)
    if "job" not in data or "builds" not in data:
        raise ValueError(
            f"build_receipt.json at {receipt_path} missing 'job' or 'builds'"
        )
    return data


def resolve_target_build_entry(
    receipt: dict,
    binary_sha256: str,
) -> dict:
    """Find the build entry whose artifact SHA-256 matches.

    Returns the ``BuildCell`` dict.  Raises ``ValueError`` if no match.
    """
    for build in receipt.get("builds", []):
        artifact = build.get("artifact") or {}
        if artifact.get("sha256") == binary_sha256:
            return build
    raise ValueError(
        f"No build entry in receipt with artifact.sha256 == {binary_sha256!r}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Oracle DWARF outputs
# ═══════════════════════════════════════════════════════════════════════════════

def load_oracle_outputs(oracle_dir: Path) -> Tuple[dict, dict]:
    """Load ``oracle_report.json`` and ``oracle_functions.json``.

    Returns ``(report_dict, functions_dict)``.
    """
    report = _load_json(oracle_dir / "oracle_report.json")
    functions = _load_json(oracle_dir / "oracle_functions.json")

    sv = functions.get("schema_version", "0.0")
    if sv < "0.2":
        raise ValueError(
            f"oracle_functions.json schema_version {sv} < 0.2; "
            "line_rows evidence required"
        )
    return report, functions


# ═══════════════════════════════════════════════════════════════════════════════
# Alignment outputs
# ═══════════════════════════════════════════════════════════════════════════════

def load_alignment_outputs(alignment_dir: Path) -> Tuple[dict, dict]:
    """Load ``alignment_report.json`` and ``alignment_pairs.json``.

    Returns ``(report_dict, pairs_dict)``.
    """
    report = _load_json(alignment_dir / "alignment_report.json")
    pairs = _load_json(alignment_dir / "alignment_pairs.json")
    return report, pairs


# ═══════════════════════════════════════════════════════════════════════════════
# Ghidra decompile outputs
# ═══════════════════════════════════════════════════════════════════════════════

def load_ghidra_outputs(
    ghidra_dir: Path,
) -> Tuple[dict, List[dict], List[dict], List[dict], List[dict]]:
    """Load Ghidra report + four JSONL files.

    Returns ``(report, functions, variables, cfg, calls)``.
    """
    report = _load_json(ghidra_dir / "report.json")
    functions = _load_jsonl(ghidra_dir / "functions.jsonl")
    variables = _load_jsonl(ghidra_dir / "variables.jsonl")
    cfg = _load_jsonl(ghidra_dir / "cfg.jsonl")
    calls = _load_jsonl(ghidra_dir / "calls.jsonl")
    return report, functions, variables, cfg, calls


# ═══════════════════════════════════════════════════════════════════════════════
# Cross-validation
# ═══════════════════════════════════════════════════════════════════════════════

def cross_validate_sha256(
    oracle_sha: str,
    alignment_sha: str,
    ghidra_sha: str,
    oracle_receipt_sha: str,
    ghidra_receipt_sha: Optional[str] = None,
) -> None:
    """Validate binary_sha256 consistency across all sources.

    In a **same-variant** join (oracle and ghidra analyse the same
    binary), all four values must be identical.

    In a **cross-variant** join (e.g. oracle=debug, ghidra=stripped),
    the oracle+alignment SHA must match ``oracle_receipt_sha``, and
    the ghidra SHA must match ``ghidra_receipt_sha``.

    Parameters
    ----------
    oracle_sha:
        ``binary_sha256`` from ``oracle_report.json``.
    alignment_sha:
        ``binary_sha256`` from ``alignment_pairs.json``.
    ghidra_sha:
        ``binary_sha256`` from Ghidra's ``report.json``.
    oracle_receipt_sha:
        SHA-256 of the oracle binary as recorded in the build receipt.
    ghidra_receipt_sha:
        SHA-256 of the Ghidra binary as recorded in the build receipt.
        When *None*, defaults to *oracle_receipt_sha* (same-variant).

    Raises ``ValueError`` on any mismatch.
    """
    if ghidra_receipt_sha is None:
        ghidra_receipt_sha = oracle_receipt_sha

    mismatches: List[str] = []

    # Oracle side: oracle + alignment must agree with the oracle binary
    if oracle_sha != oracle_receipt_sha:
        mismatches.append(
            f"oracle={oracle_sha!r} != oracle_receipt={oracle_receipt_sha!r}"
        )
    if alignment_sha != oracle_receipt_sha:
        mismatches.append(
            f"alignment={alignment_sha!r} != oracle_receipt={oracle_receipt_sha!r}"
        )

    # Ghidra side: ghidra must agree with the ghidra binary
    if ghidra_sha != ghidra_receipt_sha:
        mismatches.append(
            f"ghidra={ghidra_sha!r} != ghidra_receipt={ghidra_receipt_sha!r}"
        )

    if mismatches:
        raise ValueError(
            "binary_sha256 mismatch — " + "; ".join(mismatches)
        )
