"""Shared application context attached to the FastAPI app."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple
from uuid import UUID

from .clients.assemblage_client import AssemblageClient
from .clients.minio_client import ArtifactDownloader, MinIOClient
from .storage import ArtifactStorage, JobStore
from .config import Settings


@dataclass
class BridgeContext:
    """Runtime dependencies kept on ``app.state`` for easy access."""

    settings: Settings
    job_store: JobStore
    artifact_storage: ArtifactStorage
    assemblage_client: AssemblageClient
    minio_client: MinIOClient
    artifact_downloader: ArtifactDownloader
    active_jobs: Dict[Tuple[int, int], UUID] = field(default_factory=dict)

    def close(self) -> None:
        """Release external resources."""
        self.assemblage_client.disconnect()
