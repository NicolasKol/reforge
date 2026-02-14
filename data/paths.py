"""
Artifact path resolution for the synthetic test-case directory tree.

Layout convention::

    <artifacts_root>/
      <test_case>/
        build_receipt.json
        <opt>/              # O0, O1, O2, O3
          <variant>/        # debug, release, stripped
            oracle/
              oracle_report.json
              oracle_functions.json
            join_dwarf_ts/
              alignment_report.json
              alignment_pairs.json
"""

from __future__ import annotations

from pathlib import Path
from typing import List


def discover_test_cases(root: Path) -> List[str]:
    """Return sorted test-case directory names."""
    return sorted(
        d.name for d in root.iterdir()
        if d.is_dir()
    )


def build_receipt_path(root: Path, test_case: str) -> Path:
    return root / test_case / "build_receipt.json"


def oracle_report_path(
    root: Path, test_case: str, opt: str, variant: str,
) -> Path:
    return root / test_case / opt / variant / "oracle" / "oracle_report.json"


def alignment_report_path(
    root: Path, test_case: str, opt: str, variant: str,
) -> Path:
    return root / test_case / opt / variant / "join_dwarf_ts" / "alignment_report.json"


def alignment_pairs_path(
    root: Path, test_case: str, opt: str, variant: str,
) -> Path:
    return root / test_case / opt / variant / "join_dwarf_ts" / "alignment_pairs.json"


def oracle_functions_path(
    root: Path, test_case: str, opt: str, variant: str,
) -> Path:
    return root / test_case / opt / variant / "oracle" / "oracle_functions.json"


# ── Ghidra decompile outputs ─────────────────────────────────────────────────

def ghidra_decompile_dir(
    root: Path, test_case: str, opt: str, variant: str,
) -> Path:
    return root / test_case / opt / variant / "ghidra_decompile"


def ghidra_report_path(
    root: Path, test_case: str, opt: str, variant: str,
) -> Path:
    return ghidra_decompile_dir(root, test_case, opt, variant) / "report.json"


def ghidra_functions_path(
    root: Path, test_case: str, opt: str, variant: str,
) -> Path:
    return ghidra_decompile_dir(root, test_case, opt, variant) / "functions.jsonl"


def ghidra_variables_path(
    root: Path, test_case: str, opt: str, variant: str,
) -> Path:
    return ghidra_decompile_dir(root, test_case, opt, variant) / "variables.jsonl"


def ghidra_cfg_path(
    root: Path, test_case: str, opt: str, variant: str,
) -> Path:
    return ghidra_decompile_dir(root, test_case, opt, variant) / "cfg.jsonl"


def ghidra_calls_path(
    root: Path, test_case: str, opt: str, variant: str,
) -> Path:
    return ghidra_decompile_dir(root, test_case, opt, variant) / "calls.jsonl"


# ── Join oracles ↔ Ghidra outputs ────────────────────────────────────────────

def join_oracles_ghidra_dir(
    root: Path, test_case: str, opt: str, variant: str,
) -> Path:
    return root / test_case / opt / variant / "join_oracles_ghidra"


def joined_functions_path(
    root: Path, test_case: str, opt: str, variant: str,
) -> Path:
    return join_oracles_ghidra_dir(root, test_case, opt, variant) / "joined_functions.jsonl"


def joined_variables_path(
    root: Path, test_case: str, opt: str, variant: str,
) -> Path:
    return join_oracles_ghidra_dir(root, test_case, opt, variant) / "joined_variables.jsonl"


def join_report_path(
    root: Path, test_case: str, opt: str, variant: str,
) -> Path:
    return join_oracles_ghidra_dir(root, test_case, opt, variant) / "join_report.json"
