"""
Ghidra Router
Decompile stripped ELF binaries via analyzer_ghidra_decompile.

Two endpoints:
  POST /ghidra/analyze      — single binary  (synchronous)
  POST /ghidra/run          — all test cases at an opt level (synchronous)

Both block until Ghidra + Python post-processing finish.
Good enough for interactive testing; swap for async/Celery later.

See workers/analyzer_ghidra_decompile/LOCK.md for the v1 scope contract.
"""
import logging
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from analyzer_ghidra_decompile import ANALYZER_VERSION, PACKAGE_NAME, SCHEMA_VERSION  # type: ignore
from analyzer_ghidra_decompile.policy.profile import Profile  # type: ignore
from analyzer_ghidra_decompile.runner import run_ghidra_decompile  # type: ignore 

logger = logging.getLogger(__name__)


# =============================================================================
# Default paths (shared /files volume from docker-compose)
# =============================================================================

ARTIFACTS_ROOT = Path("/files/artifacts/synthetic")


# =============================================================================
# Request/Response Models
# =============================================================================

class AnalyzeSingleRequest(BaseModel):
    """Request to decompile a single stripped binary."""
    binary_path: str = Field(
        ...,
        description="Absolute path to the stripped ELF binary inside the container",
        examples=["/files/artifacts/synthetic/t01/O0/stripped/bin/t01"],
    )
    output_dir: Optional[str] = Field(
        None,
        description="Override output directory. Auto-derived if omitted.",
    )


class AnalyzeRunRequest(BaseModel):
    """Request to run Ghidra over all test cases at one opt level."""
    optimization_level: str = Field(
        ...,
        description="Optimization level: O0, O1, O2, or O3",
        pattern=r"^O[0-3]$",
    )
    artifacts_root: Optional[str] = Field(
        None,
        description="Override path to synthetic artifacts root",
    )
    write_outputs: bool = Field(
        True,
        description="Write output files to disk",
    )


class AnalyzeBinaryResult(BaseModel):
    """Result summary for a single binary."""
    binary_path: str
    test_case: str
    binary_verdict: str
    reasons: List[str]
    function_counts: Dict[str, int]
    n_variables: int = 0
    n_calls: int = 0
    output_dir: Optional[str] = None
    error: Optional[str] = None


class AnalyzeSingleResponse(BaseModel):
    """Response from single binary analysis."""
    package_name: str = PACKAGE_NAME
    analyzer_version: str = ANALYZER_VERSION
    schema_version: str = SCHEMA_VERSION
    result: AnalyzeBinaryResult


class AnalyzeRunResponse(BaseModel):
    """Response from full run over all test cases."""
    package_name: str = PACKAGE_NAME
    analyzer_version: str = ANALYZER_VERSION
    schema_version: str = SCHEMA_VERSION
    profile_id: str
    optimization_level: str
    binaries_scanned: int = 0
    binaries_accepted: int = 0
    binaries_rejected: int = 0
    binaries_failed: int = 0
    results: List[AnalyzeBinaryResult] = Field(default_factory=list)


# =============================================================================
# Helpers
# =============================================================================

def _result_from_run(
    binary_path: str,
    test_case: str,
    output_dir: Optional[Path],
) -> AnalyzeBinaryResult:
    """Run the analyzer and return an AnalyzeBinaryResult."""
    report, funcs, variables, cfg, calls = run_ghidra_decompile(
        binary_path=binary_path,
        output_dir=output_dir,
    )
    return AnalyzeBinaryResult(
        binary_path=binary_path,
        test_case=test_case,
        binary_verdict=report.binary_verdict,
        reasons=report.reasons,
        function_counts=report.function_counts.model_dump(),
        n_variables=len(variables),
        n_calls=len(calls),
        output_dir=str(output_dir) if output_dir else None,
    )


# =============================================================================
# Router
# =============================================================================

router = APIRouter()


@router.post(
    "/analyze",
    response_model=AnalyzeSingleResponse,
    status_code=status.HTTP_200_OK,
    summary="Analyze a single stripped binary with Ghidra (synchronous)",
)
async def analyze_single(request: AnalyzeSingleRequest):
    """
    Decompile one stripped binary with Ghidra and return structured results.

    Blocks until complete (typically 10-60 seconds depending on binary size).

    Expected binary location::

        /files/artifacts/synthetic/<name>/<opt>/stripped/bin/<name>

    Outputs are written to::

        /files/artifacts/synthetic/<name>/<opt>/stripped/ghidra_decompile/
    """
    binary = Path(request.binary_path)
    if not binary.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Binary not found: {binary}",
        )

    # Derive output dir from binary path if not specified
    if request.output_dir:
        out_dir = Path(request.output_dir)
    else:
        # .../stripped/bin/<name> → .../stripped/ghidra_decompile/
        out_dir = binary.parent.parent / "ghidra_decompile"

    # Derive test_case name from path
    test_case = binary.name

    try:
        result = _result_from_run(
            binary_path=str(binary),
            test_case=test_case,
            output_dir=out_dir,
        )
    except Exception as e:
        logger.error("Ghidra analysis failed for %s: %s", binary, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {e}",
        )

    return AnalyzeSingleResponse(result=result)


@router.post(
    "/run",
    response_model=AnalyzeRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Run Ghidra over all stripped binaries at a given opt level",
)
async def run_all(request: AnalyzeRunRequest):
    """
    Scan all synthetic test-case directories, locate the **stripped**
    variant binary at the requested optimization level, and run the
    Ghidra decompiler on each.

    Expected filesystem layout (produced by builder-worker)::

        /files/artifacts/synthetic/<name>/<opt>/stripped/bin/<name>

    Outputs are written alongside the binary::

        /files/artifacts/synthetic/<name>/<opt>/stripped/ghidra_decompile/

    Blocks until all binaries are processed (sequential).
    """
    opt = request.optimization_level
    root = Path(request.artifacts_root) if request.artifacts_root else ARTIFACTS_ROOT

    if not root.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifacts root not found: {root}",
        )

    profile = Profile.v1()
    response = AnalyzeRunResponse(
        profile_id=profile.profile_id,
        optimization_level=opt,
    )

    for case_dir in sorted(root.iterdir()):
        if not case_dir.is_dir():
            continue

        case_name = case_dir.name
        stripped_binary = case_dir / opt / "stripped" / "bin" / case_name

        if not stripped_binary.exists():
            logger.debug("No stripped binary at %s, skipping", stripped_binary)
            continue

        out_dir = None
        if request.write_outputs:
            out_dir = case_dir / opt / "stripped" / "ghidra_decompile"

        try:
            result = _result_from_run(
                binary_path=str(stripped_binary),
                test_case=case_name,
                output_dir=out_dir,
            )
        except Exception as e:
            logger.error(
                "Ghidra analysis failed on %s: %s",
                stripped_binary, e, exc_info=True,
            )
            result = AnalyzeBinaryResult(
                binary_path=str(stripped_binary),
                test_case=case_name,
                binary_verdict="REJECT",
                reasons=["GHIDRA_CRASH"],
                function_counts={
                    "n_functions_total": 0,
                    "n_functions_ok": 0,
                    "n_functions_warn": 0,
                    "n_functions_fail": 0,
                },
                error=str(e),
            )
            response.binaries_failed += 1

        response.results.append(result)
        response.binaries_scanned += 1

        if result.binary_verdict == "REJECT":
            response.binaries_rejected += 1
        else:
            response.binaries_accepted += 1

    return response
