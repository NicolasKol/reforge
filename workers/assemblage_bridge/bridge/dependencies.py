"""FastAPI dependency helpers."""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException, Request

from .config import Settings
from .context import BridgeContext


def get_settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[attr-defined]


def get_context(request: Request) -> BridgeContext:
    return request.app.state.ctx  # type: ignore[attr-defined]


def verify_api_key(
    x_api_key: Optional[str] = Header(None),
    settings: Settings = Depends(get_settings),
) -> bool:
    """Optional API key gate."""
    if not settings.require_api_key:
        return True

    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required")

    if x_api_key != settings.api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")

    return True
