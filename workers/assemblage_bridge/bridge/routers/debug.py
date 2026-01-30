"""Debug endpoints for monitoring bridge internals."""

import logging
from typing import Dict, Any

from fastapi import APIRouter, Depends

from ..dependencies import get_context, verify_api_key
from ..models import JobStatus

router = APIRouter(prefix="/debug", tags=["Debug"])
logger = logging.getLogger(__name__)


@router.get("/active-jobs")
async def get_active_jobs(
    _: bool = Depends(verify_api_key),
    ctx=Depends(get_context),
) -> Dict[str, Any]:
    """Show currently tracked active jobs (jobs submitted and being polled).
    
    This shows which (repo_id, build_opt_id) pairs are being monitored
    and their corresponding job UUIDs.
    """
    active = [
        {
            "repo_id": repo_id,
            "build_opt_id": build_opt_id,
            "job_id": str(job_id),
        }
        for (repo_id, build_opt_id), job_id in ctx.active_jobs.items()
    ]
    
    return {
        "active_count": len(active),
        "active_jobs": active,
    }


@router.get("/poller-status")
async def get_poller_status(
    _: bool = Depends(verify_api_key),
    ctx=Depends(get_context),
) -> Dict[str, Any]:
    """Check if the background status poller is configured and running.
    
    Also shows connection status to Assemblage DB and MinIO.
    """
    assemblage_connected = ctx.assemblage_client.check_connection()
    minio_connected = ctx.minio_client.check_connection()
    
    # Count jobs by status
    queued_jobs, _ = ctx.job_store.list_jobs(status=JobStatus.QUEUED, limit=1000)
    cloning_jobs, _ = ctx.job_store.list_jobs(status=JobStatus.CLONING, limit=1000)
    building_jobs, _ = ctx.job_store.list_jobs(status=JobStatus.BUILDING, limit=1000)
    downloading_jobs, _ = ctx.job_store.list_jobs(status=JobStatus.DOWNLOADING, limit=1000)
    
    # Check if there are untracked incomplete jobs
    untracked_jobs = []
    for job in queued_jobs + cloning_jobs + building_jobs + downloading_jobs:
        if job.assemblage_task_id and job.assemblage_opt_id:
            key = (job.assemblage_task_id, job.assemblage_opt_id)
            if key not in ctx.active_jobs:
                untracked_jobs.append({
                    "job_id": str(job.job_id),
                    "status": job.status.value,
                    "repo_id": job.assemblage_task_id,
                    "opt_id": job.assemblage_opt_id,
                })
    
    result = {
        "assemblage_db_connected": assemblage_connected,
        "minio_connected": minio_connected,
        "active_jobs_count": len(ctx.active_jobs),
        "queued_jobs_count": len(queued_jobs),
        "cloning_jobs_count": len(cloning_jobs),
        "building_jobs_count": len(building_jobs),
        "downloading_jobs_count": len(downloading_jobs),
        "untracked_incomplete_jobs_count": len(untracked_jobs),
    }
    
    if untracked_jobs:
        result["untracked_incomplete_jobs"] = untracked_jobs
        result["warning"] = (
            f"Found {len(untracked_jobs)} incomplete jobs not in active_jobs. "
            "These jobs won't be polled! This can happen if bridge was restarted before fix. "
            "Use force-poll endpoint to update them manually, or restart bridge to restore tracking."
        )
    
    if not assemblage_connected:
        result["note"] = (
            "assemblage_db_connected is False - the poller is NOT running and jobs will stay QUEUED. "
            "Check bridge logs for connection errors."
        )
    
    return result


@router.get("/job/{job_id}/assemblage-status")
async def get_job_assemblage_status(
    job_id: str,
    _: bool = Depends(verify_api_key),
    ctx=Depends(get_context),
):
    """Query the current Assemblage DB status for a job.
    
    This bypasses the local cache and queries Assemblage directly.
    Useful for debugging why a job is stuck.
    """
    from uuid import UUID
    
    job_uuid = UUID(job_id)
    job = ctx.job_store.get_job(job_uuid)
    
    if not job:
        return {"error": "Job not found in local store"}
    
    if not job.assemblage_task_id or not job.assemblage_opt_id:
        return {
            "error": "Job has no Assemblage task ID",
            "note": "This job was never successfully submitted to Assemblage",
        }
    
    task_status = ctx.assemblage_client.get_task_status(
        job.assemblage_task_id,
        job.assemblage_opt_id,
    )
    
    if not task_status:
        return {
            "error": "No status found in Assemblage DB",
            "repo_id": job.assemblage_task_id,
            "build_opt_id": job.assemblage_opt_id,
            "note": "Task may not exist in b_status table or query failed",
        }
    
    return {
        "job_id": job_id,
        "local_status": job.status.value,
        "assemblage_repo_id": task_status.repo_id,
        "assemblage_build_opt_id": task_status.build_opt_id,
        "assemblage_clone_status": task_status.clone_status,
        "assemblage_build_status": task_status.build_status,
        "assemblage_clone_msg": task_status.clone_msg,
        "assemblage_build_msg": task_status.build_msg,
        "assemblage_build_time": task_status.build_time,
        "assemblage_commit": task_status.commit_hexsha,
        "assemblage_url": task_status.url,
    }


@router.post("/force-poll")
async def force_poll_job(
    job_id: str,
    _: bool = Depends(verify_api_key),
    ctx=Depends(get_context),
):
    """Manually trigger a status poll for a specific job.
    
    Useful for debugging or forcing an immediate update.
    """
    from uuid import UUID
    from ..clients.assemblage_client import map_assemblage_status_to_job_status
    
    job_uuid = UUID(job_id)
    job = ctx.job_store.get_job(job_uuid)
    
    if not job:
        return {"error": "Job not found"}
    
    if not job.assemblage_task_id or not job.assemblage_opt_id:
        return {"error": "Job has no Assemblage task ID"}
    
    task_status = ctx.assemblage_client.get_task_status(
        job.assemblage_task_id,
        job.assemblage_opt_id,
    )
    
    if not task_status:
        return {
            "error": "No status found in Assemblage DB",
            "action": "not_updated",
        }
    
    status = map_assemblage_status_to_job_status(
        task_status.clone_status,
        task_status.build_status,
    )
    
    progress_msg = f"Clone: {task_status.clone_status}, Build: {task_status.build_status}"
    error_msg = None
    
    if task_status.build_status == "FAILED":
        error_msg = task_status.build_msg or "Build failed"
    elif task_status.clone_status == "FAILED":
        error_msg = task_status.clone_msg or "Clone failed"
    
    ctx.job_store.update_job_status(
        job_id=job_uuid,
        status=status,
        progress_message=progress_msg,
        error_message=error_msg,
    )
    
    return {
        "job_id": job_id,
        "action": "updated",
        "new_status": status.value,
        "progress_message": progress_msg,
        "error_message": error_msg,
    }
