"""Assemblage Bridge FastAPI entrypoint."""

import logging
import os

from bridge.app import create_app
from bridge.config import Settings

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

app = create_app()

if __name__ == "__main__":
    import uvicorn

    settings = Settings()
    reload_flag = os.getenv("ASSEMBLAGE_BRIDGE_RELOAD", "false").lower() == "true"
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=reload_flag,
    )
