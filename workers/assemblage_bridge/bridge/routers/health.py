"""Health endpoint."""

from fastapi import APIRouter, Depends

from ..dependencies import get_context
from ..models import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def health_check(ctx=Depends(get_context)) -> HealthResponse:
    mq_ok = False
    s3_ok = False
    db_ok = False

    try:
        mq_ok = ctx.assemblage_client.check_connection()
    except Exception:
        pass

    try:
        s3_ok = ctx.minio_client.check_connection()
    except Exception:
        pass

    try:
        ctx.job_store.list_jobs(limit=1)
        db_ok = True
    except Exception:
        db_ok = False

    return HealthResponse(
        status="healthy" if (mq_ok or s3_ok or db_ok) else "degraded",
        rabbitmq_connected=mq_ok,
        minio_connected=s3_ok,
        jobs_db_ok=db_ok,
    )
