"""
Oracle TS Router
Tree-sitter source-structure oracle for preprocessed C translation units.

Runs the oracle_ts package over .i files produced by the builder's
preprocess phase and returns structured verdicts with function indexes.

See workers/oracle_ts/LOCK.md for the v0 scope contract.
"""
import logging
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from oracle_ts import ORACLE_VERSION, PACKAGE_NAME, SCHEMA_VERSION  # type: ignore
from oracle_ts.policy.profile import TsProfile  # type: ignore
from oracle_ts.runner import run_oracle_ts  # type: ignore

logger = logging.getLogger(__name__)


# =============================================================================
# Default paths (shared /files volume from docker-compose)
# =============================================================================

ARTIFACTS_ROOT = Path("/files/artifacts/synthetic")


# =============================================================================
# Request/Response Models
# =============================================================================

class OracleTsRunRequest(BaseModel):
    """Request to run the tree-sitter oracle."""
    artifacts_root: Optional[str] = Field(
        None,
        description="Override path to synthetic artifacts root",
    )
    write_outputs: bool = Field(
        True,
        description="Write oracle JSON outputs to disk",
    )
    test_cases: Optional[List[str]] = Field(
        None,
        description="Specific test case names to process (default: all)",
    )


class OracleTsCaseResult(BaseModel):
    """Result for a single test case."""
    test_case: str
    tu_count: int
    function_count: int
    accept_count: int
    warn_count: int
    reject_count: int
    output_dir: Optional[str] = None


class OracleTsRunResponse(BaseModel):
    """Response from a full oracle_ts run."""
    package_name: str = PACKAGE_NAME # type: ignore
    oracle_version: str = ORACLE_VERSION # type: ignore
    schema_version: str = SCHEMA_VERSION # type: ignore
    profile_id: str
    cases_scanned: int = 0
    cases_with_i_files: int = 0
    total_functions: int = 0
    results: List[OracleTsCaseResult] = Field(default_factory=list)


# =============================================================================
# Router
# =============================================================================

router = APIRouter()


@router.post(
    "/run",
    response_model=OracleTsRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Run tree-sitter oracle over preprocessed .i files",
)
async def run_oracle_ts_endpoint(request: OracleTsRunRequest):
    """
    Scan all synthetic test-case directories under the artifacts root,
    locate preprocessed ``.i`` files in the ``preprocess/`` subdirectory,
    and run the tree-sitter oracle on each.

    Expected filesystem layout (produced by builder-worker v2)::

        /files/artifacts/synthetic/<name>/preprocess/*.i

    Oracle outputs are written to::

        /files/artifacts/synthetic/<name>/oracle_ts/

    Returns a summary with per-case function counts and verdicts.
    """
    profile = TsProfile.v0()
    root = Path(request.artifacts_root) if request.artifacts_root else ARTIFACTS_ROOT

    if not root.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifacts root not found: {root}",
        )

    response = OracleTsRunResponse(profile_id=profile.profile_id)

    # Walk every test-case directory
    for case_dir in sorted(root.iterdir()):
        if not case_dir.is_dir():
            continue

        case_name = case_dir.name

        # Filter by requested test cases if specified
        if request.test_cases and case_name not in request.test_cases:
            continue

        response.cases_scanned += 1

        # Look for preprocess/ directory with .i files
        pp_dir = case_dir / "preprocess"
        if not pp_dir.exists() or not pp_dir.is_dir():
            logger.debug("No preprocess/ dir at %s, skipping", pp_dir)
            continue

        i_files = sorted(pp_dir.glob("*.i"))
        if not i_files:
            logger.debug("No .i files in %s, skipping", pp_dir)
            continue

        response.cases_with_i_files += 1

        # Output directory
        out_dir = None
        if request.write_outputs:
            out_dir = case_dir / "oracle_ts"

        try:
            report, functions, recipes = run_oracle_ts(
                i_paths=i_files,
                profile=profile,
                output_dir=out_dir,
            )
        except Exception as e:
            logger.error(
                "oracle_ts failed on %s: %s", case_name, e, exc_info=True
            )
            response.results.append(OracleTsCaseResult(
                test_case=case_name,
                tu_count=0,
                function_count=0,
                accept_count=0,
                warn_count=0,
                reject_count=0,
            ))
            continue

        result = OracleTsCaseResult(
            test_case=case_name,
            tu_count=len(report.tu_reports),
            function_count=report.function_counts.total,
            accept_count=report.function_counts.accept,
            warn_count=report.function_counts.warn,
            reject_count=report.function_counts.reject,
            output_dir=str(out_dir) if out_dir else None,
        )
        response.results.append(result)
        response.total_functions += report.function_counts.total

    return response
