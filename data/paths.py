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
    """Return sorted test-case directory names (those starting with ``t``)."""
    return sorted(
        d.name for d in root.iterdir()
        if d.is_dir() and d.name.startswith("t")
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
