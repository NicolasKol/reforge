"""
Loader — read and validate oracle JSON files for the joiner.

Validates schema_version constraints:
  - oracle_dwarf ≥ 0.2  (line_rows field required)
  - oracle_ts   ≥ 0.1
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

# Minimum schema versions required.
_DWARF_MIN_SCHEMA = (0, 2)
_TS_MIN_SCHEMA = (0, 1)


def _parse_version(v: str) -> Tuple[int, ...]:
    return tuple(int(p) for p in v.split("."))


def _check_version(
    data: dict,
    label: str,
    min_version: Tuple[int, ...],
) -> None:
    sv = data.get("schema_version", "0.0")
    parsed = _parse_version(sv)
    if parsed < min_version:
        min_str = ".".join(str(p) for p in min_version)
        raise ValueError(
            f"{label} schema_version {sv} < required {min_str}"
        )


def load_dwarf_outputs(
    report_path: Path,
    functions_path: Path,
) -> Tuple[dict, List[dict]]:
    """
    Load and validate oracle_dwarf report + functions.

    Returns (report_dict, list_of_function_dicts).
    Raises ValueError if schema_version < 0.2.
    """
    report = json.loads(report_path.read_text(encoding="utf-8"))
    _check_version(report, "oracle_dwarf report", _DWARF_MIN_SCHEMA)

    functions_doc = json.loads(functions_path.read_text(encoding="utf-8"))
    _check_version(functions_doc, "oracle_dwarf functions", _DWARF_MIN_SCHEMA)

    return report, functions_doc.get("functions", [])


def load_ts_outputs(
    report_path: Path,
    functions_path: Path,
) -> Tuple[dict, List[dict]]:
    """
    Load and validate oracle_ts report + functions.

    Returns (ts_report_dict, list_of_function_dicts).
    """
    report = json.loads(report_path.read_text(encoding="utf-8"))
    _check_version(report, "oracle_ts report", _TS_MIN_SCHEMA)

    functions_doc = json.loads(functions_path.read_text(encoding="utf-8"))
    _check_version(functions_doc, "oracle_ts functions", _TS_MIN_SCHEMA)

    return report, functions_doc.get("functions", [])


def load_i_files(preprocess_dir: Path) -> Dict[str, str]:
    """
    Load all .i files from *preprocess_dir* into a {tu_path: content} dict.

    tu_path is the .i filename stem (matching the TU name convention from
    the builder).  Skips binary / non-UTF-8 files with a warning.
    """
    contents: Dict[str, str] = {}
    if not preprocess_dir.is_dir():
        logger.warning("preprocess dir does not exist: %s", preprocess_dir)
        return contents

    for i_file in sorted(preprocess_dir.glob("*.i")):
        try:
            text = i_file.read_text(encoding="utf-8", errors="replace")
            contents[i_file.name] = text
        except OSError as exc:
            logger.warning("failed to read %s: %s", i_file, exc)

    logger.info("loaded %d .i files from %s", len(contents), preprocess_dir)
    return contents
