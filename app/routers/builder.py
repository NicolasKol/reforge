"""
Builder Router
Handles C/C++ project build requests and status tracking.
"""
import uuid
import json
import redis
import psycopg2
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field

from app.config import Settings


# Dependency for Redis connection
def get_redis() -> redis.Redis:
    """Get Redis client"""
    settings = Settings()
    return redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        decode_responses=True
    )


# Dependency for PostgreSQL connection
def get_db():
    """Get PostgreSQL connection"""
    settings = Settings()
    conn = psycopg2.connect(
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        database=settings.POSTGRES_DB,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD
    )
    try:
        yield conn
    finally:
        conn.close()


# =============================================================================
# Request/Response Models
# =============================================================================

class OptimizationLevel(str):
    """Optimization level enum"""
    pass  # Using string for flexibility


class Compiler(str):
    """Compiler enum"""
    pass


# FUTURE WORK: Git repository builds - DON'T TOUCH
# class BuildRequest(BaseModel):
#     """Request to build a C/C++ project"""
#     repo_url: str = Field(..., description="Git repository URL")
#     commit_ref: str = Field("HEAD", description="Branch, tag, or commit hash")
#     compiler: str = Field("gcc", description="Compiler: gcc or clang")
#     optimizations: List[str] = Field(
#         default=["O0", "O2", "O3"],
#         description="Optimization levels to build"
#     )
#     debug_symbols: bool = Field(True, description="Include debug symbols")
#     save_assembly: bool = Field(False, description="Save assembly files")


# class BuildJobResponse(BaseModel):
#     """Response after submitting a build job"""
#     job_id: str
#     status: str
#     message: str


# class BuildStatusResponse(BaseModel):
#     """Current status of a build job"""
#     job_id: str
#     status: str
#     repo_url: str
#     commit_ref: str
#     compiler: str
#     optimizations: List[str]
#     commit_hash: Optional[str] = None
#     artifact_count: int = 0
#     created_at: Optional[str] = None
#     started_at: Optional[str] = None
#     finished_at: Optional[str] = None
#     error_message: Optional[str] = None


# class ArtifactInfo(BaseModel):
#     """Information about a built artifact"""
#     filename: str
#     optimization: str
#     sha256: str
#     size_bytes: int
#     has_debug_info: bool
#     file_path: str


class SyntheticBuildRequest(BaseModel):
    """Request to build synthetic C/C++ source code"""
    name: str = Field(..., description="Unique identifier for this test case")
    source_code: str = Field(..., description="C/C++ source code to compile")
    test_category: str = Field(..., description="Category (arrays, loops, strings, etc.)")
    language: str = Field("c", description="Language: 'c' or 'cpp'")
    compilers: List[str] = Field(default=["gcc"], description="Compilers: gcc, clang")
    optimizations: List[str] = Field(
        default=["O0", "O2", "O3"],
        description="Optimization levels"
    )


class SyntheticBuildResponse(BaseModel):
    """Response after submitting synthetic build"""
    job_id: str
    name: str
    status: str
    message: str


# =============================================================================
# Router
# =============================================================================

router = APIRouter()


# FUTURE WORK: Git repository builds - DON'T TOUCH
# @router.post("/build", response_model=BuildJobResponse, status_code=status.HTTP_202_ACCEPTED)
# async def submit_build(request: BuildRequest, redis_client: redis.Redis = Depends(get_redis)):
#     """
#     Submit a git repository build job to the queue.
#     
#     The job will be processed asynchronously by builder workers.
#     Use the returned job_id to poll for status.
#     """
#     job_id = str(uuid.uuid4())
#     
#     # Prepare job payload
#     job_data = {
#         "job_id": job_id,
#         "job_type": "git_build",
#         "repo_url": request.repo_url,
#         "commit_ref": request.commit_ref,
#         "compiler": request.compiler,
#         "optimizations": request.optimizations,
#         "debug_symbols": request.debug_symbols,
#         "save_assembly": request.save_assembly
#     }
#     
#     # Enqueue to Redis
#     redis_client.rpush("builder:queue", json.dumps(job_data))
#     
#     return BuildJobResponse(
#         job_id=job_id,
#         status="QUEUED",
#         message=f"Build job queued for {request.repo_url}"
#     )


@router.post("/synthetic", response_model=SyntheticBuildResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_synthetic_build(
    request: SyntheticBuildRequest,
    redis_client: redis.Redis = Depends(get_redis)
):
    """
    Submit a synthetic C/C++ source code build job.
    
    This endpoint is for building single source files for testing purposes.
    It will compile the code at multiple optimization levels and create:
    - debug variant: Full debug symbols (ground truth for evaluation)
    - release variant: Optimized with debug info (intermediate)
    - stripped variant: Optimized and stripped (what LLM will analyze)
    
    The source code and all artifacts are stored for corpus building.
    Use this for creating test datasets from standalone C/C++ programs.
    """
    job_id = str(uuid.uuid4())
    
    # Validate compilers
    valid_compilers = {"gcc", "clang"}
    for compiler in request.compilers:
        if compiler not in valid_compilers:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid compiler: {compiler}. Must be one of {valid_compilers}"
            )
    
    # Validate optimizations
    valid_opts = {"O0", "O1", "O2", "O3", "Os"}
    for opt in request.optimizations:
        if opt not in valid_opts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid optimization: {opt}. Must be one of {valid_opts}"
            )
    
    # Prepare job payload
    job_data = {
        "job_id": job_id,
        "job_type": "synthetic_build",
        "name": request.name,
        "source_code": request.source_code,
        "test_category": request.test_category,
        "language": request.language,
        "compilers": request.compilers,
        "optimizations": request.optimizations
    }
    
    # Enqueue to Redis
    redis_client.rpush("builder:queue", json.dumps(job_data))
    
    return SyntheticBuildResponse(
        job_id=job_id,
        name=request.name,
        status="QUEUED",
        message=f"Synthetic build queued for {request.name}"
    )


@router.get("/job/{job_id}")
async def get_job_status(
    job_id: str,
    db_conn = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis)
):
    """
    Get status of any build job (git or synthetic).
    
    Returns job status by checking:
    1. Redis queue (QUEUED)
    2. Database (COMPLETED or FAILED)
    """
    cursor = db_conn.cursor()
    
    try:
        # Check if it's in Redis queue
        queue_data = redis_client.lrange("builder:queue", 0, -1)
        for item in queue_data: # type: ignore
            job = json.loads(item)
            if job.get("job_id") == job_id:
                return {
                    "job_id": job_id,
                    "status": "QUEUED",
                    "job_type": job.get("job_type"),
                    "message": "Job is waiting in queue"
                }
        
        # Check database for completed/failed jobs
        cursor.execute("""
            SELECT id, repo_url, commit_ref, compiler, status,
                   created_at, started_at, finished_at, error_message
            FROM reforge.build_jobs
            WHERE id::text = %s
        """, (job_id,))
        
        row = cursor.fetchone()
        if row:
            return {
                "job_id": str(row[0]),
                "job_type": "git_build",
                "status": row[4],
                "repo_url": row[1],
                "commit_ref": row[2],
                "compiler": row[3],
                "created_at": row[5].isoformat() if row[5] else None,
                "started_at": row[6].isoformat() if row[6] else None,
                "finished_at": row[7].isoformat() if row[7] else None,
                "error_message": row[8]
            }
        
        # Job not found
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found"
        )
        
    finally:
        cursor.close()


@router.get("/synthetic/{name}")
async def get_synthetic_status(name: str, db_conn = Depends(get_db)):
    """
    Get status of a synthetic build by name.
    
    Returns details about the synthetic code and all generated binaries.
    """
    cursor = db_conn.cursor()
    
    try:
        # Check if synthetic_code exists
        cursor.execute("""
            SELECT id, name, test_category, language, source_hash, created_at
            FROM reforge.synthetic_code
            WHERE name = %s
        """, (name,))
        
        row = cursor.fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Synthetic build '{name}' not found"
            )
        
        synthetic_id = row[0]
        
        # Get all binaries for this synthetic code
        cursor.execute("""
            SELECT compiler, optimization_level, variant_type, 
                   file_path, file_size, has_debug_info, is_stripped
            FROM reforge.binaries
            WHERE synthetic_code_id = %s
            ORDER BY compiler, optimization_level, variant_type
        """, (synthetic_id,))
        
        binaries = []
        for b in cursor.fetchall():
            binaries.append({
                "compiler": b[0],
                "optimization_level": b[1],
                "variant_type": b[2],
                "file_path": b[3],
                "file_size": b[4],
                "has_debug_info": b[5],
                "is_stripped": b[6]
            })
        
        return {
            "name": row[1],
            "test_category": row[2],
            "language": row[3],
            "source_hash": row[4],
            "created_at": row[5].isoformat() if row[5] else None,
            "status": "COMPLETED",
            "binary_count": len(binaries),
            "binaries": binaries
        }
        
    finally:
        cursor.close()


# FUTURE WORK: Git repository builds - DON'T TOUCH
# @router.get("/build/{job_id}/artifacts", response_model=List[ArtifactInfo])
# async def get_build_artifacts(job_id: str):
#     """
#     Get list of artifacts produced by a build job.
#     
#     **TODO:**
#     - Query PostgreSQL for binaries with build_job_id
#     - Return artifact metadata (filename, sha256, optimization level, etc.)
#     """
#     # PLACEHOLDER
#     raise HTTPException(
#         status_code=status.HTTP_501_NOT_IMPLEMENTED,
#         detail="Artifact listing not implemented yet"
#     )


# @router.get("/builds", response_model=List[BuildStatusResponse])
# async def list_builds(
#     status_filter: Optional[str] = None,
#     limit: int = 50,
#     offset: int = 0
# ):
#     """
#     List build jobs with optional filtering.
#     
#     **TODO:**
#     - Query PostgreSQL with pagination
#     - Filter by status if provided
#     - Return list of build jobs
#     """
#     # PLACEHOLDER
#     raise HTTPException(
#         status_code=status.HTTP_501_NOT_IMPLEMENTED,
#         detail="Build listing not implemented yet"
#     )


@router.delete("/synthetic/{name}")
async def delete_synthetic_build(name: str, db_conn = Depends(get_db)):
    """
    Delete a specific synthetic build and all its binaries.
    
    This removes:
    - All binary artifacts from database
    - The synthetic_code record
    
    Note: This does NOT delete physical files from disk.
    """
    cursor = db_conn.cursor()
    
    try:
        # Check if synthetic_code exists
        cursor.execute("""
            SELECT id FROM reforge.synthetic_code WHERE name = %s
        """, (name,))
        
        row = cursor.fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Synthetic build '{name}' not found"
            )
        
        synthetic_id = row[0]
        
        # Delete binaries first (foreign key constraint)
        cursor.execute("""
            DELETE FROM reforge.binaries WHERE synthetic_code_id = %s
        """, (synthetic_id,))
        binary_count = cursor.rowcount
        
        # Delete synthetic_code
        cursor.execute("""
            DELETE FROM reforge.synthetic_code WHERE id = %s
        """, (synthetic_id,))
        
        db_conn.commit()
        
        return {
            "status": "deleted",
            "name": name,
            "binaries_deleted": binary_count,
            "message": f"Deleted '{name}' and {binary_count} binaries"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db_conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )
    finally:
        cursor.close()


@router.delete("/synthetic")
async def delete_all_synthetic_builds(db_conn = Depends(get_db)):
    """
    Delete ALL synthetic builds and their binaries.
    
    WARNING: This deletes all synthetic data from the database.
    Physical files on disk are NOT deleted.
    """
    cursor = db_conn.cursor()
    
    try:
        # Delete all binaries first
        cursor.execute("DELETE FROM reforge.binaries WHERE synthetic_code_id IS NOT NULL")
        binary_count = cursor.rowcount
        
        # Delete all synthetic_code
        cursor.execute("DELETE FROM reforge.synthetic_code")
        synthetic_count = cursor.rowcount
        
        db_conn.commit()
        
        return {
            "status": "deleted",
            "synthetic_builds_deleted": synthetic_count,
            "binaries_deleted": binary_count,
            "message": f"Deleted all {synthetic_count} synthetic builds and {binary_count} binaries"
        }
        
    except Exception as e:
        db_conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )
    finally:
        cursor.close()


# TODO: Add endpoint for downloading artifacts
# TODO: Add endpoint for canceling a build
# TODO: Add endpoint for retrying failed builds
