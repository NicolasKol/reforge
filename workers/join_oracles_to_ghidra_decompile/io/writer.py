"""
Writer — deterministic serialization for join outputs.

Conventions (matching all other workers):
  - JSON:  indent=2, sort_keys=True, trailing newline.
  - JSONL: compact (no indent), sort_keys=True, one object per line.
  - Directories created with mkdir(parents=True, exist_ok=True).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List

from join_oracles_to_ghidra_decompile.io.schema import (
    JoinedFunctionRow,
    JoinedVariableRow,
    JoinReport,
)

log = logging.getLogger(__name__)


def write_outputs(
    report: JoinReport,
    joined_functions: List[JoinedFunctionRow],
    joined_variables: List[JoinedVariableRow],
    output_dir: Path,
) -> None:
    """Write all join output files to *output_dir*.

    File list:
      - join_report.json
      - joined_functions.jsonl   (sorted by dwarf_function_id, ghidra_entry_va)
      - joined_variables.jsonl   (stub in v1)
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── join_report.json ──────────────────────────────────────────────────
    report_path = output_dir / "join_report.json"
    report_path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    log.info("Wrote %s", report_path)

    # ── joined_functions.jsonl ────────────────────────────────────────────
    funcs_path = output_dir / "joined_functions.jsonl"
    sorted_funcs = sorted(
        joined_functions,
        key=lambda r: (r.dwarf_function_id, r.ghidra_entry_va or 0),
    )
    with open(funcs_path, "w", encoding="utf-8") as fh:
        for row in sorted_funcs:
            fh.write(
                json.dumps(row.model_dump(mode="json"), sort_keys=True)
                + "\n"
            )
    log.info("Wrote %s (%d rows)", funcs_path, len(sorted_funcs))

    # ── joined_variables.jsonl ────────────────────────────────────────────
    vars_path = output_dir / "joined_variables.jsonl"
    sorted_vars = sorted(
        joined_variables,
        key=lambda r: (r.dwarf_function_id, r.ghidra_func_id or ""),
    )
    with open(vars_path, "w", encoding="utf-8") as fh:
        for row in sorted_vars:
            fh.write(
                json.dumps(row.model_dump(mode="json"), sort_keys=True)
                + "\n"
            )
    log.info("Wrote %s (%d rows)", vars_path, len(sorted_vars))
