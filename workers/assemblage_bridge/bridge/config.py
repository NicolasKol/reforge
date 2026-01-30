"""Configuration helpers for the Assemblage Bridge service."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Settings:
    """Application settings sourced from environment variables."""

    # Assemblage Database
    db_host: str = os.getenv("ASSEMBLAGE_DB_HOST", "assemblage-db")
    db_port: int = int(os.getenv("ASSEMBLAGE_DB_PORT", "5432"))
    db_name: str = os.getenv("ASSEMBLAGE_DB_NAME", "assemblage")
    db_user: str = os.getenv("ASSEMBLAGE_DB_USER", "assemblage")
    db_password: str = os.getenv("ASSEMBLAGE_DB_PASSWORD", "assemblage_pw")

    # Assemblage MinIO/S3
    s3_endpoint: str = os.getenv("ASSEMBLAGE_S3_ENDPOINT", "http://assemblage-minio:9000")
    s3_access_key: str = os.getenv("ASSEMBLAGE_S3_ACCESS_KEY", "minioadmin")
    s3_secret_key: str = os.getenv("ASSEMBLAGE_S3_SECRET_KEY", "minioadmin")
    s3_bucket: str = os.getenv("ASSEMBLAGE_S3_BUCKET", "artifacts")
    s3_region: str = os.getenv("ASSEMBLAGE_S3_REGION", "us-east-1")

    # Bridge settings
    port: int = int(os.getenv("ASSEMBLAGE_BRIDGE_PORT", "8090"))
    local_out_dir: str = os.getenv("ASSEMBLAGE_LOCAL_OUT_DIR", "/files/binaries")
    db_path: str = os.getenv("ASSEMBLAGE_DB_PATH", "/files/assemblage_bridge/jobs.db")

    # Security
    api_key: Optional[str] = os.getenv("ASSEMBLAGE_BRIDGE_API_KEY")
    require_api_key: bool = os.getenv("ASSEMBLAGE_BRIDGE_REQUIRE_API_KEY", "false").lower() == "true"

    # Assemblage dataset/project naming
    default_dataset: str = os.getenv("ASSEMBLAGE_DEFAULT_DATASET", "Reforge")
