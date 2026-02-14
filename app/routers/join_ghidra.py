"""
Join Ghidra Router
Oracle ↔ Ghidra decompile deterministic join.

Runs the join_oracles_to_ghidra_decompile package over all upstream
outputs for a given optimization level and variant combination.

See workers/join_oracles_to_ghidra_decompile/LOCK.md for the v1 scope contract.
"""
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from join_oracles_to_ghidra_decompile import (  # type: ignore
    JOINER_VERSION,
    PACKAGE_NAME,
    SCHEMA_VERSION,
)
from join_oracles_to_ghidra_decompile.policy.profile import (  # type: ignore
    JoinOraclesGhidraProfile,
)
from join_oracles_to_ghidra_decompile.runner import (  # type: ignore
    run_join_oracles_ghidra,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Default paths (shared /files volume from docker-compose)
# =============================================================================

ARTIFACTS_ROOT = Path("/files/artifacts/synthetic")


# =============================================================================
# Request / Response Models
# =============================================================================

class JoinGhidraRunRequest(BaseModel):
    """Request to run the oracle ↔ Ghidra join."""

    optimization_level: str = Field(
        ...,
        description="Optimization level: O0, O1, O2, or O3",
        pattern=r"^O[0-3]$",
    )
    oracle_variant: str = Field(
        "debug",
        description=(
            "Build variant that holds oracle and alignment outputs "
            "(default: 'debug')."
        ),
    )
    ghidra_variant: str = Field(
        "stripped",
        description=(
            "Build variant that holds Ghidra decompile outputs "
            "(default: 'stripped')."
        ),
    )
    artifacts_root: Optional[str] = Field(
        None,
        description="Override path to synthetic artifacts root",
    )
    write_outputs: bool = Field(
        True,
        description="Write join outputs (report + JSONL) to disk",
    )
    test_cases: Optional[List[str]] = Field(
        None,
        description="Specific test case names to process (default: all)",
    )


class JoinGhidraCaseResult(BaseModel):
    """Result for one test case."""

    test_case: str
    optimization_level: str
    oracle_variant: str
    ghidra_variant: str
    binary_sha256: Optional[str] = None
    n_dwarf_funcs: int = 0
    n_joined_to_ghidra: int = 0
    n_high_confidence: int = 0
    n_no_range: int = 0
    high_confidence_yield: float = 0.0
    output_dir: Optional[str] = None
    error: Optional[str] = None


class JoinGhidraRunResponse(BaseModel):
    """Response from a full join run (sweep across test cases)."""

    package_name: str = PACKAGE_NAME
    joiner_version: str = JOINER_VERSION
    schema_version: str = SCHEMA_VERSION
    profile_id: str
    optimization_level: str
    oracle_variant: str
    ghidra_variant: str
    cases_scanned: int = 0
    cases_joined: int = 0
    cases_skipped: int = 0
    total_dwarf_funcs: int = 0
    total_joined: int = 0
    total_high_confidence: int = 0
    results: List[JoinGhidraCaseResult] = Field(default_factory=list)


# =============================================================================
# Helpers
# =============================================================================

def _read_sha256_from_oracle_report(oracle_dir: Path) -> str:
    """Extract binary_sha256 from oracle_report.json."""
    report_path = oracle_dir / "oracle_report.json"
    with open(report_path, encoding="utf-8") as f:
        data = json.load(f)
    sha = data.get("binary_sha256")
    if not sha:
        raise ValueError(
            f"oracle_report.json at {report_path} missing binary_sha256"
        )
    return sha


def _read_sha256_from_ghidra_report(ghidra_dir: Path) -> str:
    """Extract binary_sha256 from Ghidra's report.json."""
    report_path = ghidra_dir / "report.json"
    with open(report_path, encoding="utf-8") as f:
        data = json.load(f)
    sha = data.get("binary_sha256")
    if not sha:
        raise ValueError(
            f"report.json at {report_path} missing binary_sha256"
        )
    return sha


# =============================================================================
# Router
# =============================================================================

router = APIRouter()


@router.post(
    "/run",
    response_model=JoinGhidraRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Run oracle ↔ Ghidra join over all test cases at a given opt level",
)
async def run_join_ghidra_endpoint(request: JoinGhidraRunRequest):
    """
    For each test case under *artifacts_root*, locate:

    - DWARF oracle outputs at ``<name>/<opt>/<oracle_variant>/oracle/``
    - Alignment outputs at ``<name>/<opt>/<oracle_variant>/join_dwarf_ts/``
    - Ghidra decompile outputs at ``<name>/<opt>/<ghidra_variant>/ghidra_decompile/``
    - Build receipt at ``<name>/build_receipt.json``

    Join outputs are written to::

        <name>/<opt>/<ghidra_variant>/join_oracles_ghidra/

    Returns a sweep summary with per-case join statistics.
    """
    profile = JoinOraclesGhidraProfile.v1()
    opt = request.optimization_level
    oracle_var = request.oracle_variant
    ghidra_var = request.ghidra_variant
    root = (
        Path(request.artifacts_root) if request.artifacts_root else ARTIFACTS_ROOT
    )

    if not root.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifacts root not found: {root}",
        )

    response = JoinGhidraRunResponse(
        profile_id=profile.profile_id,
        optimization_level=opt,
        oracle_variant=oracle_var,
        ghidra_variant=ghidra_var,
    )

    for case_dir in sorted(root.iterdir()):
        if not case_dir.is_dir():
            continue

        case_name = case_dir.name

        # Filter by requested test cases if specified
        if request.test_cases and case_name not in request.test_cases:
            continue

        response.cases_scanned += 1

        # ── Locate inputs ────────────────────────────────────────────
        oracle_dir = case_dir / opt / oracle_var / "oracle"
        alignment_dir = case_dir / opt / oracle_var / "join_dwarf_ts"
        ghidra_dir = case_dir / opt / ghidra_var / "ghidra_decompile"
        receipt_path = case_dir / "build_receipt.json"

        missing: List[str] = []
        if not oracle_dir.exists():
            missing.append(f"oracle: {oracle_dir}")
        if not alignment_dir.exists():
            missing.append(f"alignment: {alignment_dir}")
        if not ghidra_dir.exists():
            missing.append(f"ghidra: {ghidra_dir}")
        if not receipt_path.exists():
            missing.append(f"receipt: {receipt_path}")

        if missing:
            logger.debug(
                "Skipping %s/%s — missing: %s", case_name, opt, "; ".join(missing),
            )
            response.cases_skipped += 1
            continue

        # ── Resolve binary SHA-256 from oracle report ────────────────
        try:
            binary_sha256 = _read_sha256_from_oracle_report(oracle_dir)
        except Exception as e:
            logger.error(
                "Cannot read SHA-256 for %s/%s: %s", case_name, opt, e,
            )
            response.results.append(JoinGhidraCaseResult(
                test_case=case_name,
                optimization_level=opt,
                oracle_variant=oracle_var,
                ghidra_variant=ghidra_var,
                error=f"SHA-256 resolution failed: {e}",
            ))
            response.cases_skipped += 1
            continue

        # ── Resolve ghidra binary SHA-256 (may differ in cross-variant) ──
        ghidra_binary_sha256 = None
        if oracle_var != ghidra_var:
            try:
                ghidra_binary_sha256 = _read_sha256_from_ghidra_report(
                    ghidra_dir,
                )
            except Exception as e:
                logger.error(
                    "Cannot read Ghidra SHA-256 for %s/%s: %s",
                    case_name, opt, e,
                )
                response.results.append(JoinGhidraCaseResult(
                    test_case=case_name,
                    optimization_level=opt,
                    oracle_variant=oracle_var,
                    ghidra_variant=ghidra_var,
                    binary_sha256=binary_sha256,
                    error=f"Ghidra SHA-256 resolution failed: {e}",
                ))
                response.cases_skipped += 1
                continue

        # ── Output directory ─────────────────────────────────────────
        out_dir: Optional[Path] = None
        if request.write_outputs:
            out_dir = case_dir / opt / ghidra_var / "join_oracles_ghidra"

        # ── Run join ─────────────────────────────────────────────────
        try:
            report, funcs, _vars = run_join_oracles_ghidra(
                oracle_dir=oracle_dir,
                alignment_dir=alignment_dir,
                ghidra_dir=ghidra_dir,
                receipt_path=receipt_path,
                binary_sha256=binary_sha256,
                profile=profile,
                output_dir=out_dir,
                ghidra_binary_sha256=ghidra_binary_sha256,
                ghidra_variant=ghidra_var if ghidra_binary_sha256 else None,
            )
        except Exception as e:
            logger.error(
                "Join failed on %s/%s: %s", case_name, opt, e,
                exc_info=True,
            )
            response.results.append(JoinGhidraCaseResult(
                test_case=case_name,
                optimization_level=opt,
                oracle_variant=oracle_var,
                ghidra_variant=ghidra_var,
                binary_sha256=binary_sha256,
                error=str(e),
            ))
            response.cases_skipped += 1
            continue

        # ── Collect result ───────────────────────────────────────────
        response.cases_joined += 1

        hc = report.high_confidence
        yc = report.yield_counts

        result = JoinGhidraCaseResult(
            test_case=case_name,
            optimization_level=opt,
            oracle_variant=oracle_var,
            ghidra_variant=ghidra_var,
            binary_sha256=binary_sha256,
            n_dwarf_funcs=yc.n_dwarf_funcs,
            n_joined_to_ghidra=yc.n_joined_to_ghidra,
            n_high_confidence=hc.high_confidence_count,
            n_no_range=yc.n_no_range,
            high_confidence_yield=hc.yield_rate,
            output_dir=str(out_dir) if out_dir else None,
        )
        response.results.append(result)
        response.total_dwarf_funcs += yc.n_dwarf_funcs
        response.total_joined += yc.n_joined_to_ghidra
        response.total_high_confidence += hc.high_confidence_count

    return response
