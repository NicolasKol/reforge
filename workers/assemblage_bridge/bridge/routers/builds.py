"""Build-related API routes."""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from ..dependencies import get_context, get_settings, verify_api_key
from ..models import (
    BuildRequest,
    BuildSubmitResponse,
    JobListResponse,
    JobResponse,
    JobStatus,
)
from ..services import download_artifacts_for_job
from ..storage import compute_recipe_hash

router = APIRouter(prefix="/build", tags=["Build"])
logger = logging.getLogger(__name__)


@router.post("", response_model=BuildSubmitResponse)
async def submit_build(
    request: BuildRequest,
    ctx=Depends(get_context),
    settings=Depends(get_settings),
    _: bool = Depends(verify_api_key),
):
    job = ctx.job_store.create_job(request)
    logger.info("Created job %s for %s", job.job_id, request.repo_url)

    try:
        if not ctx.assemblage_client.check_connection():
            ctx.job_store.update_job_status(
                job.job_id,
                JobStatus.FAILED,
                error_message="Cannot connect to Assemblage database",
            )
            raise HTTPException(status_code=503, detail="Assemblage database not available")

        compiler = request.recipe.compiler
        if hasattr(compiler, "value"):
            compiler = compiler.value
        build_opt_id = 1 if compiler == "clang" else 2

        priority_value = request.priority.value if hasattr(request.priority, "value") else str(request.priority)

        repo_id, build_opt_id = ctx.assemblage_client.submit_build(
            request,
            build_opt_id=build_opt_id,
            priority=priority_value,
        )

        ctx.active_jobs[(repo_id, build_opt_id)] = job.job_id

        ctx.job_store.update_job_status(
            job.job_id,
            JobStatus.QUEUED,
            assemblage_task_id=repo_id,
            assemblage_opt_id=build_opt_id,
            progress_message="Submitted to Assemblage (coordinator will dispatch)",
        )

        logger.info("Job %s submitted as repo_id=%s opt=%s", job.job_id, repo_id, build_opt_id)

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to submit job %s: %s", job.job_id, exc)
        ctx.job_store.update_job_status(
            job.job_id,
            JobStatus.FAILED,
            error_message=str(exc),
        )
        raise HTTPException(status_code=500, detail=f"Failed to submit build: {exc}")

    return BuildSubmitResponse(
        job_id=job.job_id,
        status=JobStatus.QUEUED,
        recipe_hash=job.recipe_hash,
        message="Build submitted to Assemblage database",
    )


@router.get("/{job_id}", response_model=JobResponse)
async def get_build_status(job_id: UUID, _: bool = Depends(verify_api_key), ctx=Depends(get_context)):
    job = ctx.job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("", response_model=JobListResponse)
async def list_builds(
    status: JobStatus | None = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=100, description="Max results"),
    offset: int = Query(0, ge=0, description="Result offset"),
    _: bool = Depends(verify_api_key),
    ctx=Depends(get_context),
):
    jobs, total = ctx.job_store.list_jobs(status=status, limit=limit, offset=offset)
    return JobListResponse(jobs=jobs, total=total, offset=offset, limit=limit)


@router.post("/{job_id}/retry", response_model=BuildSubmitResponse)
async def retry_build(job_id: UUID, _: bool = Depends(verify_api_key), ctx=Depends(get_context)):
    job = ctx.job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status not in (JobStatus.FAILED, JobStatus.TIMEOUT, JobStatus.CANCELLED):
        raise HTTPException(status_code=400, detail=f"Cannot retry job with status {job.status}")

    new_job = ctx.job_store.create_job(job.request)

    compiler = job.request.recipe.compiler
    if hasattr(compiler, "value"):
        compiler = compiler.value
    build_opt_id = 1 if compiler == "clang" else 2
    priority_value = job.request.priority.value if hasattr(job.request.priority, "value") else str(job.request.priority)

    try:
        repo_id, build_opt_id = ctx.assemblage_client.submit_build(
            job.request,
            build_opt_id=build_opt_id,
            priority=priority_value,
        )
        ctx.active_jobs[(repo_id, build_opt_id)] = new_job.job_id
        ctx.job_store.update_job_status(
            new_job.job_id,
            JobStatus.QUEUED,
            assemblage_task_id=repo_id,
            assemblage_opt_id=build_opt_id,
            progress_message=f"Retry of job {job_id}",
        )
    except Exception as exc:
        ctx.job_store.update_job_status(
            new_job.job_id,
            JobStatus.FAILED,
            error_message=str(exc),
        )
        raise HTTPException(status_code=500, detail=f"Failed to submit retry: {exc}")

    return BuildSubmitResponse(
        job_id=new_job.job_id,
        status=JobStatus.QUEUED,
        recipe_hash=new_job.recipe_hash,
        message=f"Retry submitted (original job: {job_id})",
    )


@router.delete("/{job_id}")
async def cancel_build(
    job_id: UUID,
    cleanup: bool = Query(False, description="Also delete local artifacts"),
    _: bool = Depends(verify_api_key),
    ctx=Depends(get_context),
):
    job = ctx.job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status in (JobStatus.SUCCESS, JobStatus.FAILED):
        raise HTTPException(status_code=400, detail=f"Cannot cancel completed job with status {job.status}")

    ctx.job_store.update_job_status(job_id, JobStatus.CANCELLED)

    repo_id = job.assemblage_task_id
    opt_id = job.assemblage_opt_id
    if repo_id and opt_id:
        ctx.active_jobs.pop((repo_id, opt_id), None)

    if cleanup:
        ctx.artifact_storage.cleanup_job(job_id)

    return {"status": "cancelled", "job_id": str(job_id)}


@router.get("/{job_id}/artifacts")
async def list_job_artifacts(job_id: UUID, _: bool = Depends(verify_api_key), ctx=Depends(get_context)):
    job = ctx.job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": str(job_id),
        "artifact_count": job.artifact_count,
        "artifacts": [
            {
                "filename": a.filename,
                "local_path": a.local_path,
                "sha256": a.sha256,
                "size_bytes": a.size_bytes,
                "optimization": a.optimization,
            }
            for a in job.artifacts
        ],
    }


@router.get("/{job_id}/artifact/{filename}")
async def download_artifact(job_id: UUID, filename: str, _: bool = Depends(verify_api_key), ctx=Depends(get_context)):
    job = ctx.job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    for artifact in job.artifacts:
        if artifact.filename == filename:
            from pathlib import Path
            from fastapi.responses import FileResponse

            path = Path(artifact.local_path)
            if not path.exists():
                raise HTTPException(status_code=410, detail="Artifact file no longer exists")
            return FileResponse(path=str(path), filename=filename, media_type="application/octet-stream")

    raise HTTPException(status_code=404, detail="Artifact not found")


@router.post("/{job_id}/download")
async def trigger_artifact_download(job_id: UUID, _: bool = Depends(verify_api_key), ctx=Depends(get_context)):
    job = ctx.job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.assemblage_task_id:
        raise HTTPException(status_code=400, detail="Job has no Assemblage task ID")

    asyncio.create_task(download_artifacts_for_job(ctx, job_id, job.assemblage_task_id))

    return {
        "status": "download_started",
        "job_id": str(job_id),
        "message": "Artifact download initiated. Poll job status for completion.",
    }


@router.post("/recipe/hash")
async def compute_hash(recipe: dict, _: bool = Depends(verify_api_key)):
    from ..models import BuildRecipe

    try:
        parsed = BuildRecipe(**recipe)
        return {
            "recipe_hash": compute_recipe_hash(parsed),
            "canonical_recipe": parsed.model_dump(),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid recipe: {exc}")
