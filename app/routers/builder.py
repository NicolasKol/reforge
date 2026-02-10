"""
Builder Router — builder_synth_v1

Synthetic C build submission and status tracking.
Profile: linux-x86_64-elf-gcc-c (hard-locked, not user-selectable).

No git/repo builds. No Clang. No C++. See LOCK.md.
"""
import uuid
import json
import redis
import psycopg2
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field, field_validator

from app.config import Settings


# =============================================================================
# Dependencies
# =============================================================================

def get_redis() -> redis.Redis:
    """Get Redis client."""
    settings = Settings()
    return redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        decode_responses=True,
    )


def get_db():
    """Get PostgreSQL connection."""
    settings = Settings()
    conn = psycopg2.connect(
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        database=settings.POSTGRES_DB,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
    )
    try:
        yield conn
    finally:
        conn.close()


# =============================================================================
# Request / Response Models
# =============================================================================

class SourceFileInput(BaseModel):
    """A single source file to compile."""
    filename: str = Field(..., description="Relative filename (e.g. 'main.c', 'utils.h')")
    content: str = Field(..., description="File content")


class BuildTarget(BaseModel):
    """Optional single-target rebuild specification."""
    optimization: str = Field(..., description="Optimization level: O0, O1, O2, O3")
    variant: str = Field(..., description="Variant: debug, release, stripped")


class SyntheticBuildRequest(BaseModel):
    """
    Request to build synthetic C source files.

    Accepts either:
      - files[]: List of {filename, content} for multi-file builds
      - source_code: Single string (convenience; auto-wrapped as {name}.c)

    At least one of files or source_code must be provided.
    """
    name: str = Field(..., description="Unique identifier for this test case")
    files: Optional[List[SourceFileInput]] = Field(
        None,
        description="Source files to compile (multi-file support)",
    )
    source_code: Optional[str] = Field(
        None,
        description="Single C source code string (convenience shorthand for files)",
    )
    test_category: str = Field(..., description="Category: arrays, loops, strings, etc.")
    language: str = Field("c", description="Language (only 'c' accepted in v1)")
    optimizations: List[str] = Field(
        default=["O0", "O1", "O2", "O3"],
        description="Optimization levels to build",
    )
    target: Optional[BuildTarget] = Field(
        None,
        description="If set, only build this single (optimization, variant) cell",
    )

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        if v != "c":
            raise ValueError("Only language='c' is supported in builder_synth_v1")
        return v


class SyntheticBuildResponse(BaseModel):
    """Response after submitting a synthetic build."""
    job_id: str
    name: str
    status: str
    message: str


# =============================================================================
# Router
# =============================================================================

router = APIRouter()

VALID_OPTIMIZATIONS = {"O0", "O1", "O2", "O3"}
VALID_VARIANTS = {"debug", "release", "stripped"}
PROFILE_ID = "linux-x86_64-elf-gcc-c"


@router.post(
    "/synthetic",
    response_model=SyntheticBuildResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_synthetic_build(
    request: SyntheticBuildRequest,
    redis_client: redis.Redis = Depends(get_redis),
):
    """
    Submit a synthetic C build job.

    Compiles source files at multiple optimization levels and creates three
    variants per level:
      - **debug**: Full debug symbols (ground truth for oracle)
      - **release**: Optimized, not stripped
      - **stripped**: Optimized and stripped (challenge target for LLM)

    Accepts multi-file input via `files[]` or single-file via `source_code`.
    Optionally specify `target` to rebuild a single (optimization, variant) cell.
    """
    job_id = str(uuid.uuid4())

    # --- Resolve files ---
    if request.files and request.source_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide either 'files' or 'source_code', not both",
        )

    if request.source_code:
        # Convenience: wrap single source into files list
        resolved_files = [{"filename": f"{request.name}.c", "content": request.source_code}]
    elif request.files:
        resolved_files = [{"filename": f.filename, "content": f.content} for f in request.files]
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide either 'files' or 'source_code'",
        )

    # --- Validate at least one .c file ---
    c_files = [f for f in resolved_files if f["filename"].endswith(".c")]
    if not c_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one .c file is required",
        )

    # --- Validate optimizations ---
    for opt in request.optimizations:
        if opt not in VALID_OPTIMIZATIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid optimization: {opt}. Must be one of {VALID_OPTIMIZATIONS}",
            )

    # --- Validate target if provided ---
    target_data = None
    if request.target:
        if request.target.optimization not in VALID_OPTIMIZATIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid target optimization: {request.target.optimization}",
            )
        if request.target.variant not in VALID_VARIANTS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid target variant: {request.target.variant}",
            )
        target_data = {
            "optimization": request.target.optimization,
            "variant": request.target.variant,
        }

    # --- Enqueue ---
    job_data = {
        "job_id": job_id,
        "job_type": "synthetic_build",
        "name": request.name,
        "files": resolved_files,
        "test_category": request.test_category,
        "language": request.language,
        "optimizations": request.optimizations,
        "profile": PROFILE_ID,
        "target": target_data,
    }

    redis_client.rpush("builder:queue", json.dumps(job_data))

    return SyntheticBuildResponse(
        job_id=job_id,
        name=request.name,
        status="QUEUED",
        message=f"Synthetic build queued for '{request.name}' "
                f"({len(resolved_files)} file(s), "
                f"{len(request.optimizations)} opt levels)",
    )


@router.get("/job/{job_id}")
async def get_job_status(
    job_id: str,
    db_conn=Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    """
    Get status of a build job by job_id.

    Checks Redis queue first (QUEUED), then database (COMPLETED / FAILED).
    """
    cursor = db_conn.cursor()

    try:
        # Check Redis queue
        queue_data = redis_client.lrange("builder:queue", 0, -1)
        for item in queue_data:  # type: ignore
            job = json.loads(item)
            if job.get("job_id") == job_id:
                return {
                    "job_id": job_id,
                    "status": "QUEUED",
                    "job_type": job.get("job_type"),
                    "message": "Job is waiting in queue",
                }

        # Check database
        cursor.execute(
            """
            SELECT id, name, test_category, language, snapshot_sha256,
                   status, file_count, created_at, metadata
            FROM reforge.synthetic_code
            WHERE id::text = %s
            """,
            (job_id,),
        )

        row = cursor.fetchone()
        if row:
            return {
                "job_id": str(row[0]),
                "name": row[1],
                "test_category": row[2],
                "language": row[3],
                "snapshot_sha256": row[4],
                "status": row[5],
                "file_count": row[6],
                "created_at": row[7].isoformat() if row[7] else None,
                "metadata": row[8],
            }

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    finally:
        cursor.close()


@router.get("/synthetic/{name}")
async def get_synthetic_status(name: str, db_conn=Depends(get_db)):
    """
    Get status of a synthetic build by name.

    Returns the synthetic_code record and all associated binaries.
    """
    cursor = db_conn.cursor()

    try:
        cursor.execute(
            """
            SELECT id, name, test_category, language, snapshot_sha256,
                   status, file_count, source_files, created_at, metadata
            FROM reforge.synthetic_code
            WHERE name = %s
            """,
            (name,),
        )

        row = cursor.fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Synthetic build '{name}' not found",
            )

        synthetic_id = row[0]

        # Get binaries
        cursor.execute(
            """
            SELECT compiler, optimization_level, variant_type,
                   file_path, file_hash, file_size,
                   has_debug_info, is_stripped, elf_metadata
            FROM reforge.binaries
            WHERE synthetic_code_id = %s
            ORDER BY optimization_level, variant_type
            """,
            (synthetic_id,),
        )

        binaries = []
        for b in cursor.fetchall():
            binaries.append({
                "compiler": b[0],
                "optimization_level": b[1],
                "variant_type": b[2],
                "file_path": b[3],
                "file_hash": b[4],
                "file_size": b[5],
                "has_debug_info": b[6],
                "is_stripped": b[7],
                "elf_metadata": b[8],
            })

        return {
            "name": row[1],
            "test_category": row[2],
            "language": row[3],
            "snapshot_sha256": row[4],
            "status": row[5],
            "file_count": row[6],
            "source_files": row[7],
            "created_at": row[8].isoformat() if row[8] else None,
            "metadata": row[9],
            "binary_count": len(binaries),
            "binaries": binaries,
        }

    finally:
        cursor.close()


@router.delete("/synthetic/{name}")
async def delete_synthetic_build(name: str, db_conn=Depends(get_db)):
    """
    Delete a synthetic build and all its binaries from the database.

    Does NOT delete physical files from disk (use manual cleanup).
    """
    cursor = db_conn.cursor()

    try:
        cursor.execute(
            "SELECT id FROM reforge.synthetic_code WHERE name = %s",
            (name,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Synthetic build '{name}' not found",
            )

        synthetic_id = row[0]

        # Delete binaries first (FK constraint)
        cursor.execute(
            "DELETE FROM reforge.binaries WHERE synthetic_code_id = %s",
            (synthetic_id,),
        )
        binary_count = cursor.rowcount

        # Delete synthetic_code
        cursor.execute(
            "DELETE FROM reforge.synthetic_code WHERE id = %s",
            (synthetic_id,),
        )

        db_conn.commit()

        return {
            "status": "deleted",
            "name": name,
            "binaries_deleted": binary_count,
            "message": f"Deleted '{name}' and {binary_count} binaries",
        }

    except HTTPException:
        raise
    except Exception as e:
        db_conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}",
        )
    finally:
        cursor.close()


@router.delete("/synthetic")
async def delete_all_synthetic_builds(db_conn=Depends(get_db)):
    """
    Delete ALL synthetic builds and their binaries from the database.

    WARNING: Bulldozes all synthetic data. Physical files on disk are NOT deleted.
    """
    cursor = db_conn.cursor()

    try:
        cursor.execute(
            "DELETE FROM reforge.binaries WHERE synthetic_code_id IS NOT NULL"
        )
        binary_count = cursor.rowcount

        cursor.execute("DELETE FROM reforge.synthetic_code")
        synthetic_count = cursor.rowcount

        db_conn.commit()

        return {
            "status": "deleted",
            "synthetic_builds_deleted": synthetic_count,
            "binaries_deleted": binary_count,
            "message": f"Deleted all {synthetic_count} synthetic builds and {binary_count} binaries",
        }

    except Exception as e:
        db_conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}",
        )
    finally:
        cursor.close()
