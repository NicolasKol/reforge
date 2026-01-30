"""Application startup/shutdown lifecycle wiring."""

from __future__ import annotations

import asyncio
import logging
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from typing import Callable

from fastapi import FastAPI

from .clients.assemblage_client import AssemblageClient, AssemblageConfig
from .config import Settings
from .context import BridgeContext
from .clients.minio_client import ArtifactDownloader, MinIOClient
from .models import JobStatus
from .services import poll_status_updates
from .storage import ArtifactStorage, JobStore

logger = logging.getLogger(__name__)


def build_lifespan(settings: Settings) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Create a lifespan context manager bound to provided settings."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("Starting Assemblage Bridge...")

        job_db_path = Path(settings.db_path)
        job_db_path.parent.mkdir(parents=True, exist_ok=True)

        job_store = JobStore(job_db_path)
        artifact_storage = ArtifactStorage(Path(settings.local_out_dir))

        assemblage_client = AssemblageClient(
            AssemblageConfig(
                db_host=settings.db_host,
                db_port=settings.db_port,
                db_name=settings.db_name,
                db_user=settings.db_user,
                db_password=settings.db_password,
            )
        )

        minio_client = MinIOClient(
            endpoint_url=settings.s3_endpoint,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            bucket=settings.s3_bucket,
            region=settings.s3_region,
        )
        artifact_downloader = ArtifactDownloader(minio_client, artifact_storage)

        ctx = BridgeContext(
            settings=settings,
            job_store=job_store,
            artifact_storage=artifact_storage,
            assemblage_client=assemblage_client,
            minio_client=minio_client,
            artifact_downloader=artifact_downloader,
        )

        app.state.settings = settings
        app.state.ctx = ctx

        # Restore active_jobs from DB for jobs that aren't finished yet
        restored_count = 0
        try:
            incomplete_statuses = [
                JobStatus.QUEUED,
                JobStatus.CLONING,
                JobStatus.BUILDING,
                JobStatus.DOWNLOADING,
            ]
            for status in incomplete_statuses:
                jobs, _ = job_store.list_jobs(status=status, limit=1000)
                for job in jobs:
                    if job.assemblage_task_id and job.assemblage_opt_id:
                        ctx.active_jobs[(job.assemblage_task_id, job.assemblage_opt_id)] = job.job_id
                        restored_count += 1
            if restored_count > 0:
                logger.info(f"Restored {restored_count} incomplete jobs to active tracking")
        except Exception as exc:
            logger.warning(f"Failed to restore active jobs from DB: {exc}")

        polling_task = None
        try:
            max_attempts = 12  # ~1 minute with the 5s delay
            for attempt in range(1, max_attempts + 1):
                if assemblage_client.check_connection():
                    polling_task = asyncio.create_task(poll_status_updates(ctx))
                    logger.info(
                        "Started Assemblage status polling after %s attempt(s)",
                        attempt,
                    )
                    break
                logger.warning(
                    "Assemblage DB not reachable yet (attempt %s/%s). "
                    "DB: %s:%s/%s. Retrying in 5s...",
                    attempt,
                    max_attempts,
                    settings.db_host,
                    settings.db_port,
                    settings.db_name,
                )
                await asyncio.sleep(5)

            if not polling_task:
                logger.error(
                    "Failed to connect to Assemblage database after %s attempts. "
                    "Status polling will NOT run. Jobs will remain QUEUED.",
                    max_attempts,
                )
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Could not start status polling: %s", exc, exc_info=True)

        yield

        logger.info("Shutting down Assemblage Bridge...")
        if polling_task:
            polling_task.cancel()
            try:
                await polling_task
            except asyncio.CancelledError:
                pass
        ctx.close()
        logger.info("Assemblage Bridge stopped")

    return lifespan
