"""MinIO/S3 client for downloading artifacts from Assemblage storage."""

import logging
from pathlib import Path
from typing import Generator, Optional
from uuid import UUID

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from ..models import OptimizationLevel
from ..storage import ArtifactStorage, compute_file_sha256

logger = logging.getLogger(__name__)


class MinIOClient:
    """Client for interacting with Assemblage's MinIO/S3 artifact storage."""
    
    def __init__(
        self,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str = "us-east-1",
    ):
        """Initialize MinIO client.
        
        Args:
            endpoint_url: MinIO endpoint (e.g., http://minio:9000)
            access_key: S3 access key
            secret_key: S3 secret key
            bucket: Bucket name for artifacts
            region: AWS region (use us-east-1 for MinIO default)
        """
        self.endpoint_url = endpoint_url
        self.bucket = bucket
        
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
            ),
        )
    
    def check_connection(self) -> bool:
        """Check if MinIO is reachable and bucket exists.
        
        Returns:
            True if connection successful
        """
        try:
            self._client.head_bucket(Bucket=self.bucket)
            return True
        except ClientError as e:
            logger.error(f"MinIO connection check failed: {e}")
            return False
    
    def list_artifacts(self, prefix: str) -> list[dict]:
        """List artifacts under a prefix.
        
        Args:
            prefix: S3 key prefix (e.g., "Dataset/Project/commit/")
            
        Returns:
            List of object metadata dicts with 'Key', 'Size', 'LastModified'
        """
        try:
            response = self._client.list_objects_v2(
                Bucket=self.bucket,
                Prefix=prefix,
            )
            return response.get("Contents", [])
        except ClientError as e:
            logger.error(f"Failed to list artifacts: {e}")
            return []
    
    def download_artifact(self, s3_key: str) -> Optional[bytes]:
        """Download a single artifact.
        
        Args:
            s3_key: Full S3 object key
            
        Returns:
            Artifact content or None if not found
        """
        try:
            response = self._client.get_object(
                Bucket=self.bucket,
                Key=s3_key,
            )
            return response["Body"].read()
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                logger.warning(f"Artifact not found: {s3_key}")
                return None
            logger.error(f"Failed to download artifact {s3_key}: {e}")
            raise
    
    def stream_artifact(
        self,
        s3_key: str,
        chunk_size: int = 8192
    ) -> Generator[bytes, None, None]:
        """Stream artifact content in chunks.
        
        Args:
            s3_key: Full S3 object key
            chunk_size: Chunk size in bytes
            
        Yields:
            Content chunks
        """
        try:
            response = self._client.get_object(
                Bucket=self.bucket,
                Key=s3_key,
            )
            for chunk in response["Body"].iter_chunks(chunk_size=chunk_size):
                yield chunk
        except ClientError as e:
            logger.error(f"Failed to stream artifact {s3_key}: {e}")
            raise
    
    def get_artifact_metadata(self, s3_key: str) -> Optional[dict]:
        """Get artifact metadata without downloading.
        
        Args:
            s3_key: Full S3 object key
            
        Returns:
            Metadata dict or None
        """
        try:
            response = self._client.head_object(
                Bucket=self.bucket,
                Key=s3_key,
            )
            return {
                "size": response["ContentLength"],
                "last_modified": response["LastModified"],
                "content_type": response.get("ContentType"),
            }
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return None
            raise


class ArtifactDownloader:
    """High-level artifact download manager."""
    
    # Map Assemblage optimization folder names to our enum
    OPT_LEVEL_MAP = {
        "opt_NONE": OptimizationLevel.NONE,
        "opt_LOW": OptimizationLevel.LOW,
        "opt_MEDIUM": OptimizationLevel.MEDIUM,
        "opt_HIGH": OptimizationLevel.HIGH,
    }
    
    def __init__(
        self,
        minio_client: MinIOClient,
        artifact_storage: ArtifactStorage,
    ):
        """Initialize downloader.
        
        Args:
            minio_client: MinIO client instance
            artifact_storage: Local storage manager
        """
        self.minio = minio_client
        self.storage = artifact_storage
    
    def build_s3_prefix(
        self,
        dataset: str,
        project: str,
        commit_hash: str,
        compiler: str,
    ) -> str:
        """Build S3 key prefix for Assemblage artifact location.
        
        Assemblage layout: artifacts/<Dataset>/<Project>/<commit>/<compiler>/<opt>/
        
        Args:
            dataset: Dataset name
            project: Project name
            commit_hash: Git commit hash
            compiler: Compiler name
            
        Returns:
            S3 key prefix
        """
        prefix = f"{dataset}/{project}/{commit_hash}/{compiler}/"
        logger.debug(
            "Building S3 prefix: dataset=%s project=%s commit=%s compiler=%s -> %s",
            dataset,
            project,
            commit_hash,
            compiler,
            prefix,
        )
        return prefix
    
    def discover_artifacts(
        self,
        dataset: str,
        project: str,
        commit_hash: str,
        compiler: str,
    ) -> dict[OptimizationLevel, list[dict]]:
        """Discover all artifacts for a build.
        
        Args:
            dataset: Dataset name
            project: Project name  
            commit_hash: Git commit hash
            compiler: Compiler name
            
        Returns:
            Dict mapping optimization level to list of artifact metadata
        """
        prefix = self.build_s3_prefix(dataset, project, commit_hash, compiler)
        all_objects = self.minio.list_artifacts(prefix)
        logger.debug(
            "discover_artifacts: bucket=%s prefix=%s objects=%s",
            self.minio.bucket,
            prefix,
            len(all_objects),
        )
        
        # Group by optimization level
        by_opt: dict[OptimizationLevel, list[dict]] = {}
        
        for obj in all_objects:
            key = obj["Key"]
            # Parse path: .../opt_LEVEL/filename
            parts = key.split("/")
            if len(parts) >= 2:
                opt_str = parts[-2]
                if opt_str in self.OPT_LEVEL_MAP:
                    opt = self.OPT_LEVEL_MAP[opt_str]
                    if opt not in by_opt:
                        by_opt[opt] = []
                    by_opt[opt].append({
                        "key": key,
                        "filename": parts[-1],
                        "size": obj["Size"],
                        "last_modified": obj["LastModified"],
                    })
                else:
                    logger.debug("Skipping object with unknown opt folder: %s", key)
        
        return by_opt
    
    def download_all_artifacts(
        self,
        job_id: UUID,
        dataset: str,
        project: str,
        commit_hash: str,
        compiler: str,
        optimizations: Optional[list[OptimizationLevel]] = None,
    ) -> list[tuple[Path, str, int, OptimizationLevel, str]]:
        """Download all artifacts for a build to local storage.
        
        Args:
            job_id: Job UUID for storage organization
            dataset: Dataset name
            project: Project name
            commit_hash: Git commit hash
            compiler: Compiler name
            optimizations: Filter to specific optimization levels
            
        Returns:
            List of tuples: (local_path, sha256, size, optimization, s3_key)
        """
        discovered = self.discover_artifacts(dataset, project, commit_hash, compiler)
        results = []
        logger.debug(
            "download_all_artifacts: discovered opts=%s filter=%s",
            list(discovered.keys()),
            optimizations,
        )
        
        for opt, artifacts in discovered.items():
            # Filter if specific optimizations requested
            if optimizations and opt not in optimizations:
                logger.debug("Skipping opt %s due to filter", opt)
                continue
            
            for artifact in artifacts:
                logger.info(f"Downloading {artifact['key']} -> {job_id}/{opt.value}/")
                
                content = self.minio.download_artifact(artifact["key"])
                if content is None:
                    logger.warning(f"Skipping missing artifact: {artifact['key']}")
                    continue
                
                path, sha256, size = self.storage.save_artifact(
                    job_id=job_id,
                    optimization=opt,
                    filename=artifact["filename"],
                    content=content,
                )
                
                results.append((path, sha256, size, opt, artifact["key"]))
                logger.debug(
                    "Downloaded artifact %s (%s bytes, sha=%s) -> %s",
                    artifact["key"],
                    size,
                    sha256,
                    path,
                )
        
        return results
    
    def download_single_artifact(
        self,
        job_id: UUID,
        s3_key: str,
        optimization: OptimizationLevel,
    ) -> Optional[tuple[Path, str, int]]:
        """Download a single artifact.
        
        Args:
            job_id: Job UUID
            s3_key: Full S3 key
            optimization: Optimization level
            
        Returns:
            Tuple of (path, sha256, size) or None
        """
        filename = s3_key.split("/")[-1]
        content = self.minio.download_artifact(s3_key)
        
        if content is None:
            return None
        
        return self.storage.save_artifact(
            job_id=job_id,
            optimization=optimization,
            filename=filename,
            content=content,
        )
