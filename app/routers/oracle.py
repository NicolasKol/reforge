"""
Oracle Router
DWARF-based alignment oracle for debug-variant ELF binaries.

Runs the oracle_dwarf package over synthetic debug binaries at a
specified optimization level and returns structured verdicts.

See workers/oracle_dwarf/LOCK.md for the v0 scope contract.
"""
import logging
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from oracle_dwarf import ORACLE_VERSION, PACKAGE_NAME, SCHEMA_VERSION  # type: ignore
from oracle_dwarf.policy.profile import Profile  # type: ignore
from oracle_dwarf.runner import run_oracle  # type: ignore

logger = logging.getLogger(__name__)


# =============================================================================
# Default paths (shared /files volume from docker-compose)
# =============================================================================

ARTIFACTS_ROOT = Path("/files/artifacts/synthetic")
OUTPUT_ROOT = Path("/files/oracle_output")


# =============================================================================
# Request/Response Models
# =============================================================================

class OracleRunRequest(BaseModel):
    """Request to run the DWARF oracle."""
    optimization_level: str = Field(
        ...,
        description="Optimization level: O0 or O1",
        pattern=r"^O[01]$",
    )
    artifacts_root: Optional[str] = Field(
        None,
        description="Override path to synthetic artifacts root",
    )
    write_outputs: bool = Field(
        True,
        description="Write oracle JSON outputs to disk",
    )


class OracleBinaryResult(BaseModel):
    """Result for a single binary."""
    binary_path: str
    verdict: str
    reasons: List[str]
    function_counts: dict
    output_dir: Optional[str] = None


class OracleRunResponse(BaseModel):
    """Response from a full oracle run."""
    package_name: str = PACKAGE_NAME
    oracle_version: str = ORACLE_VERSION
    schema_version: str = SCHEMA_VERSION
    profile_id: str
    optimization_level: str
    binaries_scanned: int = 0
    binaries_accepted: int = 0
    binaries_rejected: int = 0
    results: List[OracleBinaryResult] = Field(default_factory=list)


# =============================================================================
# Router
# =============================================================================

router = APIRouter()


@router.post(
    "/run",
    response_model=OracleRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Run DWARF oracle over debug binaries for a given opt level",
)
async def run_oracle_endpoint(request: OracleRunRequest):
    """
    Scan all synthetic test-case directories under the artifacts root,
    locate the **debug** variant binary at the requested optimization
    level, and run the DWARF oracle on each.

    Expected filesystem layout (produced by builder-worker)::

        /files/artifacts/synthetic/<name>/gcc_<opt>/debug

    Returns a summary with per-binary verdicts and function counts.
    """
    profile = Profile.v0()
    opt = request.optimization_level
    root = Path(request.artifacts_root) if request.artifacts_root else ARTIFACTS_ROOT

    if not root.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifacts root not found: {root}",
        )

    response = OracleRunResponse(
        profile_id=profile.profile_id,
        optimization_level=opt,
    )

    # Walk every test-case directory looking for gcc_<opt>/debug binaries
    for case_dir in sorted(root.iterdir()):
        if not case_dir.is_dir():
            continue

        # Builder produces:  <name>/gcc_O0/debug, <name>/gcc_O1/debug, …
        debug_binary = case_dir / f"gcc_{opt}" / "debug"
        if not debug_binary.exists():
            continue

        binary_path = str(debug_binary)
        out_dir = None
        if request.write_outputs:
            out_dir = OUTPUT_ROOT / case_dir.name / f"gcc_{opt}"

        try:
            report, functions = run_oracle(
                binary_path=binary_path,
                profile=profile,
                output_dir=out_dir,
            )
        except Exception as e:
            logger.error("Oracle failed on %s: %s", binary_path, e, exc_info=True)
            response.results.append(
                OracleBinaryResult(
                    binary_path=binary_path,
                    verdict="REJECT",
                    reasons=["DWARF_PARSE_ERROR"],
                    function_counts={"total": 0, "accept": 0, "warn": 0, "reject": 0},
                )
            )
            response.binaries_scanned += 1
            response.binaries_rejected += 1
            continue

        result = OracleBinaryResult(
            binary_path=binary_path,
            verdict=report.verdict,
            reasons=report.reasons,
            function_counts=report.function_counts.model_dump(),
            output_dir=str(out_dir) if out_dir else None,
        )
        response.results.append(result)
        response.binaries_scanned += 1

        if report.verdict == "REJECT":
            response.binaries_rejected += 1
        else:
            response.binaries_accepted += 1

    return response
