"""Background services for polling Assemblage and downloading artifacts."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from .clients.assemblage_client import map_assemblage_status_to_job_status
from .context import BridgeContext
from .models import JobStatus, OptimizationLevel

logger = logging.getLogger(__name__)


async def poll_status_updates(ctx: BridgeContext) -> None:
    """Periodically sync Assemblage task state into the local job store."""
    logger.info("Status polling loop started")
    poll_iteration = 0
    while True:
        try:
            jobs_to_check = list(ctx.active_jobs.items())
            poll_iteration += 1
            logger.debug("Poll iteration %s starting; active_jobs=%s", poll_iteration, len(jobs_to_check))
            
            if jobs_to_check:
                logger.debug(f"Polling {len(jobs_to_check)} active jobs: {jobs_to_check}")
            elif poll_iteration % 12 == 1:  # Log every ~1 minute when idle
                logger.debug("Polling loop active but no jobs to check (active_jobs is empty)")

                # Defensive rehydration: if we have no active jobs, re-scan the DB for incomplete ones
                try:
                    incomplete_statuses = [
                        JobStatus.QUEUED,
                        JobStatus.CLONING,
                        JobStatus.BUILDING,
                        JobStatus.DOWNLOADING,
                    ]
                    restored = 0
                    for status in incomplete_statuses:
                        jobs, _ = ctx.job_store.list_jobs(status=status, limit=200)
                        for job in jobs:
                            if job.assemblage_task_id and job.assemblage_opt_id:
                                key = (job.assemblage_task_id, job.assemblage_opt_id)
                                if key not in ctx.active_jobs:
                                    ctx.active_jobs[key] = job.job_id
                                    restored += 1
                    if restored:
                        logger.info(f"Rehydrated {restored} jobs into active polling from DB")
                        jobs_to_check = list(ctx.active_jobs.items())
                except Exception as exc:  # pragma: no cover - defensive best-effort
                    logger.warning(f"Failed to rehydrate active jobs during polling: {exc}")
            
            for (repo_id, build_opt_id), job_id in jobs_to_check:
                logger.debug(
                    "Checking job %s: repo_id=%s, opt=%s (ctx.active_jobs size=%s)",
                    job_id,
                    repo_id,
                    build_opt_id,
                    len(ctx.active_jobs),
                )
                
                task_status = ctx.assemblage_client.get_task_status(repo_id, build_opt_id)
                if not task_status:
                    logger.warning(
                        f"No status found for job {job_id} (repo_id={repo_id}, opt={build_opt_id}). "
                        "Task may not exist in Assemblage DB yet or query failed."
                    )
                    continue

                status = map_assemblage_status_to_job_status(
                    task_status.clone_status,
                    task_status.build_status,
                )
                progress_msg = f"Clone: {task_status.clone_status}, Build: {task_status.build_status}"
                error_msg: Optional[str] = None

                if task_status.build_status == "FAILED":
                    error_msg = task_status.build_msg or "Build failed"
                elif task_status.clone_status == "FAILED":
                    error_msg = task_status.clone_msg or "Clone failed"

                logger.info(
                    "Job %s status update -> %s | repo_id=%s opt=%s | %s",
                    job_id,
                    status.value,
                    repo_id,
                    build_opt_id,
                    progress_msg,
                )
                
                ctx.job_store.update_job_status(
                    job_id=job_id,
                    status=status,
                    progress_message=progress_msg,
                    error_message=error_msg,
                )

                if task_status.build_status == "SUCCESS":
                    logger.info(
                        "Job %s build SUCCESS; scheduling artifact download (repo_id=%s, opt=%s)",
                        job_id,
                        repo_id,
                        build_opt_id,
                    )
                    asyncio.create_task(download_artifacts_for_job(ctx, job_id, repo_id))
                    ctx.active_jobs.pop((repo_id, build_opt_id), None)
                elif status in (JobStatus.FAILED, JobStatus.TIMEOUT):
                    logger.info(
                        "Job %s finished with status %s, removing from active jobs",
                        job_id,
                        status.value,
                    )
                    ctx.active_jobs.pop((repo_id, build_opt_id), None)

            await asyncio.sleep(5)
        except Exception as exc:  # pragma: no cover - best-effort background loop
            logger.error("Error in status polling loop: %s", exc, exc_info=True)
            await asyncio.sleep(10)


async def download_artifacts_for_job(ctx: BridgeContext, job_id, repo_id: int) -> None:
    """Download artifacts from MinIO for a completed job."""
    try:
        job = ctx.job_store.get_job(job_id)
        if not job:
            logger.error("Job %s not found for artifact download", job_id)
            return

        logger.debug(
            "Preparing artifact download: job_id=%s repo_id=%s req_repo=%s opts=%s compiler=%s",
            job_id,
            repo_id,
            job.request.repo_url,
            job.request.recipe.optimizations,
            job.request.recipe.compiler,
        )

        ctx.job_store.update_job_status(
            job_id=job_id,
            status=JobStatus.DOWNLOADING,
            progress_message="Downloading artifacts...",
        )

        request = job.request
        # Parse username/project from GitHub URL: https://github.com/user/repo
        url_parts = request.repo_url.rstrip("/").rstrip(".git").split("/")
        if len(url_parts) >= 2:
            username = url_parts[-2]
            project_name = url_parts[-1]
        else:
            # Fallback to simple parsing
            project_name = url_parts[-1]
            username = "unknown"
            logger.warning(f"Could not parse username from URL {request.repo_url}, using 'unknown'")

        compiler = request.recipe.compiler
        if hasattr(compiler, "value"):
            compiler = compiler.value
        
        # Get actual commit hash from Assemblage DB (not the branch name!)
        # Assemblage resolves branch -> commit hash during clone and stores it in commit_hexsha
        commit_hash = None
        if job.assemblage_task_id and job.assemblage_opt_id:
            logger.debug(
                "Fetching commit hash from Assemblage for job %s (repo_id=%s, opt=%s)",
                job_id,
                job.assemblage_task_id,
                job.assemblage_opt_id,
            )
            task_status = ctx.assemblage_client.get_task_status(
                job.assemblage_task_id,
                job.assemblage_opt_id,
            )
            if task_status and task_status.commit_hexsha:
                commit_hash = task_status.commit_hexsha
                logger.info(
                    "Job %s using Assemblage commit hash %s (clone=%s build=%s)",
                    job_id,
                    commit_hash,
                    task_status.clone_status,
                    task_status.build_status,
                )
        
        # Fallback to request commit_ref if we couldn't get it from DB
        if not commit_hash:
            commit_hash = request.commit_ref or "HEAD"
            logger.warning(
                f"Could not get commit hash from Assemblage DB, using commit_ref: {commit_hash}. "
                "This may not match MinIO paths if a branch name was provided."
            )
        
        s3_prefix = f"{username}/{project_name}/{commit_hash}/{compiler}/"
        logger.info(
            "Downloading artifacts for job %s: user=%s project=%s commit=%s compiler=%s prefix=%s",
            job_id,
            username,
            project_name,
            commit_hash,
            compiler,
            s3_prefix,
        )

        # Assemblage uploads to: {username}/{project}/{commit}/{compiler}/{optimization}/
        # We need to use username instead of dataset
        results = ctx.artifact_downloader.download_all_artifacts(
            job_id=job_id,
            dataset=username,  # Changed: use username from URL
            project=project_name,
            commit_hash=commit_hash,
            compiler=compiler,
            optimizations=[OptimizationLevel(o) if isinstance(o, str) else o for o in request.recipe.optimizations],
        )

        if not results:
            logger.warning(
                f"No artifacts found for job {job_id}. "
                f"MinIO path: {s3_prefix}opt_*/"
            )
        else:
            logger.debug(
                "Job %s downloaded artifacts: %s",
                job_id,
                [(r[0].name, r[3].value) for r in results],
            )

        for path, sha256, size, opt, s3_key in results:
            ctx.job_store.add_artifact(
                job_id=job_id,
                filename=path.name,
                local_path=str(path),
                sha256=sha256,
                size_bytes=size,
                optimization=opt,
                s3_key=s3_key,
            )

        ctx.job_store.update_job_status(
            job_id=job_id,
            status=JobStatus.SUCCESS,
            progress_message=f"Downloaded {len(results)} artifacts",
        )

        logger.info("Downloaded %s artifacts for job %s", len(results), job_id)

    except Exception as exc:  # pragma: no cover - best-effort background task
        logger.error("Failed to download artifacts for job %s: %s", job_id, exc, exc_info=True)
        ctx.job_store.update_job_status(
            job_id=job_id,
            status=JobStatus.FAILED,
            error_message=f"Artifact download failed: {exc}",
        )
