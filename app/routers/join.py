"""
Join Router
DWARF ↔ Tree-sitter deterministic alignment joiner.

Runs the join_dwarf_ts package over oracle outputs for a given
test case and optimization level (variant).

See workers/join_dwarf_ts/LOCK.md for the v0 scope contract.
"""
import logging
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from join_dwarf_ts import JOINER_VERSION, PACKAGE_NAME, SCHEMA_VERSION  # type: ignore
from join_dwarf_ts.policy.profile import JoinProfile  # type: ignore
from join_dwarf_ts.runner import run_join_from_paths  # type: ignore

logger = logging.getLogger(__name__)


# =============================================================================
# Default paths (shared /files volume from docker-compose)
# =============================================================================

ARTIFACTS_ROOT = Path("/files/artifacts/synthetic")


# =============================================================================
# Request / Response Models
# =============================================================================

class JoinRunRequest(BaseModel):
    """Request to run the DWARF ↔ TS join."""

    optimization_level: str = Field(
        ...,
        description="Optimization level: O0 or O1",
        pattern=r"^O[01]$",
    )
    variant: str = Field(
        "debug",
        description="Build variant (e.g. 'debug'). Determines the DWARF oracle path.",
    )
    artifacts_root: Optional[str] = Field(
        None,
        description="Override path to synthetic artifacts root",
    )
    write_outputs: bool = Field(
        True,
        description="Write alignment JSON outputs to disk",
    )
    test_cases: Optional[List[str]] = Field(
        None,
        description="Specific test case names to process (default: all)",
    )


class JoinCaseResult(BaseModel):
    """Result for one test case."""

    test_case: str
    optimization_level: str
    variant: str
    match_count: int = 0
    ambiguous_count: int = 0
    no_match_count: int = 0
    non_target_count: int = 0
    output_dir: Optional[str] = None
    error: Optional[str] = None


class JoinRunResponse(BaseModel):
    """Response from a full join run (sweep across test cases)."""

    package_name: str = PACKAGE_NAME
    joiner_version: str = JOINER_VERSION
    schema_version: str = SCHEMA_VERSION
    profile_id: str
    optimization_level: str
    variant: str
    cases_scanned: int = 0
    cases_joined: int = 0
    cases_skipped: int = 0
    total_matches: int = 0
    results: List[JoinCaseResult] = Field(default_factory=list)


# =============================================================================
# Router
# =============================================================================

router = APIRouter()


@router.post(
    "/run",
    response_model=JoinRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Run DWARF ↔ TS join over oracle outputs for a given opt level",
)
async def run_join_endpoint(request: JoinRunRequest):
    """
    For each test case under *artifacts_root*, locate:

    - DWARF oracle outputs at ``<name>/<opt>/<variant>/oracle/``
    - Tree-sitter oracle outputs at ``<name>/oracle_ts/``
    - Preprocessed .i files at ``<name>/preprocess/``

    Alignment outputs are written to::

        <name>/<opt>/<variant>/join_dwarf_ts/

    Returns a sweep summary across all matched test cases.
    """
    profile = JoinProfile.v0()
    opt = request.optimization_level
    variant = request.variant
    root = Path(request.artifacts_root) if request.artifacts_root else ARTIFACTS_ROOT

    if not root.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifacts root not found: {root}",
        )

    response = JoinRunResponse(
        profile_id=profile.profile_id,
        optimization_level=opt,
        variant=variant,
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
        dwarf_dir = case_dir / opt / variant / "oracle"
        ts_dir = case_dir / "oracle_ts"
        preprocess_dir = case_dir / "preprocess"

        if not dwarf_dir.exists():
            logger.debug("No dwarf oracle at %s, skipping", dwarf_dir)
            response.cases_skipped += 1
            continue

        if not ts_dir.exists():
            logger.debug("No ts oracle at %s, skipping", ts_dir)
            response.cases_skipped += 1
            continue

        if not preprocess_dir.exists():
            logger.debug("No preprocess dir at %s, skipping", preprocess_dir)
            response.cases_skipped += 1
            continue

        # ── Output directory ─────────────────────────────────────────
        out_dir = None
        if request.write_outputs:
            out_dir = case_dir / opt / variant / "join_dwarf_ts"

        # ── Run join ─────────────────────────────────────────────────
        try:
            pairs_output, report = run_join_from_paths(
                dwarf_dir=dwarf_dir,
                ts_dir=ts_dir,
                preprocess_dir=preprocess_dir,
                profile=profile,
                output_dir=out_dir,
            )
        except Exception as e:
            logger.error(
                "join failed on %s/%s/%s: %s",
                case_name, opt, variant, e,
                exc_info=True,
            )
            response.results.append(JoinCaseResult(
                test_case=case_name,
                optimization_level=opt,
                variant=variant,
                error=str(e),
            ))
            response.cases_skipped += 1
            continue

        response.cases_joined += 1

        counts = report.pair_counts
        result = JoinCaseResult(
            test_case=case_name,
            optimization_level=opt,
            variant=variant,
            match_count=counts.match,
            ambiguous_count=counts.ambiguous,
            no_match_count=counts.no_match,
            non_target_count=counts.non_target,
            output_dir=str(out_dir) if out_dir else None,
        )
        response.results.append(result)
        response.total_matches += counts.match

    return response
