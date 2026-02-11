"""
Runner — top-level join orchestration from paths / CLI.

Ties together loader, core join logic, and writer.  Called from
the API endpoint or from a CLI.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

from join_dwarf_ts.core.join import run_join
from join_dwarf_ts.io.loader import load_dwarf_outputs, load_i_files, load_ts_outputs
from join_dwarf_ts.io.schema import AlignmentPairsOutput, AlignmentReport
from join_dwarf_ts.io.writer import write_outputs
from join_dwarf_ts.policy.profile import JoinProfile

logger = logging.getLogger(__name__)


def run_join_from_paths(
    dwarf_dir: Path,
    ts_dir: Path,
    preprocess_dir: Path,
    profile: Optional[JoinProfile] = None,
    output_dir: Optional[Path] = None,
) -> Tuple[AlignmentPairsOutput, AlignmentReport]:
    """
    Run the DWARF ↔ Tree-sitter join from file-system paths.

    Parameters
    ----------
    dwarf_dir : Path
        Directory containing oracle_report.json and oracle_functions.json.
    ts_dir : Path
        Directory containing oracle_ts_report.json and oracle_ts_functions.json.
    preprocess_dir : Path
        Directory containing preprocessed .i files.
    profile : JoinProfile, optional
        Join configuration.  Defaults to JoinProfile.v0().
    output_dir : Path, optional
        Directory to write alignment outputs.  If None, outputs are
        not written to disk (API-only usage).

    Returns
    -------
    (AlignmentPairsOutput, AlignmentReport)
    """
    if profile is None:
        profile = JoinProfile.v0()

    # ── 1. Load inputs ───────────────────────────────────────────────
    dwarf_report, dwarf_functions = load_dwarf_outputs(
        report_path=dwarf_dir / "oracle_report.json",
        functions_path=dwarf_dir / "oracle_functions.json",
    )

    ts_report, ts_functions = load_ts_outputs(
        report_path=ts_dir / "oracle_ts_report.json",
        functions_path=ts_dir / "oracle_ts_functions.json",
    )

    i_contents: Dict[str, str] = load_i_files(preprocess_dir)

    # ── 2. Run join ──────────────────────────────────────────────────
    pairs_output, report = run_join(
        dwarf_functions=dwarf_functions,
        dwarf_report=dwarf_report,
        ts_functions=ts_functions,
        ts_report=ts_report,
        i_contents=i_contents,
        profile=profile,
    )

    # ── 3. Write outputs ─────────────────────────────────────────────
    if output_dir:
        write_outputs(pairs_output, report, output_dir)
        logger.info("join outputs written to %s", output_dir)

    return pairs_output, report
