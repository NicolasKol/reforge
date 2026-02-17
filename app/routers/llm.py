"""LLM Router — DEPRECATED.

The original Redis-queue + iterative-compile architecture has been replaced by
n8n-driven LLM calling via HTTP Request nodes.  Data serving now lives in
``app.routers.data`` and result persistence in ``app.routers.results``.

This module is kept as a stub so existing imports don't break.
"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def llm_deprecated():
    return {
        "message": "The /llm endpoint has been replaced. "
                   "Use /data for function data and /results for experiment results."
    }
