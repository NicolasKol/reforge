"""Storage module for job persistence and artifact management."""

import hashlib
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

from .models import (
    ArtifactInfo,
    BuildRecipe,
    BuildRequest,
    JobResponse,
    JobStatus,
    OptimizationLevel,
)


def canonical_json(obj: dict) -> str:
    """Generate canonical JSON representation for stable hashing.
    
    - Sorted keys
    - No whitespace
    - Consistent type serialization
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def compute_recipe_hash(recipe: BuildRecipe) -> str:
    """Compute stable SHA256 hash of a build recipe.
    
    Includes all fields with their defaults explicitly to ensure
    identical recipes always produce identical hashes.
    """
    # Normalize recipe to dict with all defaults explicit
    recipe_dict = {
        "compiler": recipe.compiler if isinstance(recipe.compiler, str) else recipe.compiler.value,
        "platform": recipe.platform if isinstance(recipe.platform, str) else recipe.platform.value,
        "architecture": recipe.architecture if isinstance(recipe.architecture, str) else recipe.architecture.value,
        "optimizations": sorted([
            o if isinstance(o, str) else o.value for o in recipe.optimizations
        ]),
        "build_system": recipe.build_system if isinstance(recipe.build_system, str) else recipe.build_system.value,
        "save_assembly": recipe.save_assembly,
    }
    
    canonical = canonical_json(recipe_dict)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_file_sha256(filepath: Path) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


class JobStore:
    """SQLite-backed job storage with thread-safe operations."""
    
    def __init__(self, db_path: Path):
        """Initialize job store.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False
            )
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn
    
    @contextmanager
    def _cursor(self):
        """Context manager for database cursor with auto-commit."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
    
    def _init_db(self):
        """Initialize database schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        with self._cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    recipe_hash TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    error_message TEXT,
                    error_logs TEXT,
                    assemblage_task_id INTEGER,
                    assemblage_opt_id INTEGER,
                    progress_message TEXT
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    local_path TEXT NOT NULL,
                    s3_key TEXT,
                    sha256 TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    optimization TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (job_id) REFERENCES jobs(job_id)
                )
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_artifacts_job_id ON artifacts(job_id)
            """)
    
    def create_job(self, request: BuildRequest) -> JobResponse:
        """Create a new job entry.
        
        Args:
            request: Build request parameters
            
        Returns:
            JobResponse with new job_id
        """
        job_id = uuid4()
        recipe_hash = compute_recipe_hash(request.recipe)
        now = datetime.utcnow()
        
        with self._cursor() as cursor:
            cursor.execute("""
                INSERT INTO jobs (
                    job_id, status, recipe_hash, request_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                str(job_id),
                JobStatus.QUEUED.value,
                recipe_hash,
                request.model_dump_json(),
                now.isoformat(),
            ))
        
        return JobResponse(
            job_id=job_id,
            status=JobStatus.QUEUED,
            recipe_hash=recipe_hash,
            request=request,
            created_at=now,
        )
    
    def get_job(self, job_id: UUID) -> Optional[JobResponse]:
        """Get job by ID.
        
        Args:
            job_id: Job UUID
            
        Returns:
            JobResponse or None if not found
        """
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT * FROM jobs WHERE job_id = ?",
                (str(job_id),)
            )
            row = cursor.fetchone()
            
            if not row:
                return None
            
            # Get artifacts
            cursor.execute(
                "SELECT * FROM artifacts WHERE job_id = ?",
                (str(job_id),)
            )
            artifact_rows = cursor.fetchall()
        
        return self._row_to_job_response(row, artifact_rows)
    
    def list_jobs(
        self,
        status: Optional[JobStatus] = None,
        limit: int = 50,
        offset: int = 0
    ) -> tuple[list[JobResponse], int]:
        """List jobs with optional status filter.
        
        Args:
            status: Filter by status
            limit: Maximum results
            offset: Result offset
            
        Returns:
            Tuple of (jobs, total_count)
        """
        with self._cursor() as cursor:
            if status:
                cursor.execute(
                    "SELECT COUNT(*) FROM jobs WHERE status = ?",
                    (status.value,)
                )
                total = cursor.fetchone()[0]
                
                cursor.execute("""
                    SELECT * FROM jobs WHERE status = ?
                    ORDER BY created_at DESC LIMIT ? OFFSET ?
                """, (status.value, limit, offset))
            else:
                cursor.execute("SELECT COUNT(*) FROM jobs")
                total = cursor.fetchone()[0]
                
                cursor.execute("""
                    SELECT * FROM jobs
                    ORDER BY created_at DESC LIMIT ? OFFSET ?
                """, (limit, offset))
            
            rows = cursor.fetchall()
            jobs = []
            
            for row in rows:
                cursor.execute(
                    "SELECT * FROM artifacts WHERE job_id = ?",
                    (row["job_id"],)
                )
                artifact_rows = cursor.fetchall()
                jobs.append(self._row_to_job_response(row, artifact_rows))
        
        return jobs, total
    
    def update_job_status(
        self,
        job_id: UUID,
        status: JobStatus,
        error_message: Optional[str] = None,
        error_logs: Optional[str] = None,
        progress_message: Optional[str] = None,
        assemblage_task_id: Optional[int] = None,
        assemblage_opt_id: Optional[int] = None,
    ):
        """Update job status and optional fields.
        
        Args:
            job_id: Job UUID
            status: New status
            error_message: Error message if failed
            error_logs: Raw error logs
            progress_message: Progress update message
            assemblage_task_id: Assemblage internal task ID
            assemblage_opt_id: Assemblage build option ID
        """
        now = datetime.utcnow()
        
        updates = ["status = ?"]
        params: list[str | int] = [status.value]
        
        if status in (JobStatus.CLONING, JobStatus.BUILDING):
            updates.append("started_at = COALESCE(started_at, ?)")
            params.append(now.isoformat())
        
        if status in (JobStatus.SUCCESS, JobStatus.FAILED, JobStatus.TIMEOUT, JobStatus.CANCELLED):
            updates.append("finished_at = ?")
            params.append(now.isoformat())
        
        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message)
        
        if error_logs is not None:
            updates.append("error_logs = ?")
            params.append(error_logs)
        
        if progress_message is not None:
            updates.append("progress_message = ?")
            params.append(progress_message)
        
        if assemblage_task_id is not None:
            updates.append("assemblage_task_id = ?")
            params.append(assemblage_task_id)
        
        if assemblage_opt_id is not None:
            updates.append("assemblage_opt_id = ?")
            params.append(assemblage_opt_id)
        
        params.append(str(job_id))
        
        with self._cursor() as cursor:
            cursor.execute(
                f"UPDATE jobs SET {', '.join(updates)} WHERE job_id = ?",
                params
            )
    
    def add_artifact(
        self,
        job_id: UUID,
        filename: str,
        local_path: str,
        sha256: str,
        size_bytes: int,
        optimization: OptimizationLevel,
        s3_key: Optional[str] = None,
    ):
        """Add artifact record to a job.
        
        Args:
            job_id: Job UUID
            filename: Artifact filename
            local_path: Local filesystem path
            sha256: File SHA256 hash
            size_bytes: File size
            optimization: Optimization level used
            s3_key: S3 object key if known
        """
        now = datetime.utcnow()
        opt_value = optimization if isinstance(optimization, str) else optimization.value
        
        with self._cursor() as cursor:
            cursor.execute("""
                INSERT INTO artifacts (
                    job_id, filename, local_path, s3_key, sha256,
                    size_bytes, optimization, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(job_id),
                filename,
                local_path,
                s3_key,
                sha256,
                size_bytes,
                opt_value,
                now.isoformat(),
            ))
    
    def _row_to_job_response(
        self,
        row: sqlite3.Row,
        artifact_rows: list[sqlite3.Row]
    ) -> JobResponse:
        """Convert database row to JobResponse."""
        request = BuildRequest.model_validate_json(row["request_json"])
        
        artifacts = [
            ArtifactInfo(
                filename=ar["filename"],
                local_path=ar["local_path"],
                s3_key=ar["s3_key"],
                sha256=ar["sha256"],
                size_bytes=ar["size_bytes"],
                optimization=OptimizationLevel(ar["optimization"]),
                created_at=datetime.fromisoformat(ar["created_at"]),
            )
            for ar in artifact_rows
        ]
        
        return JobResponse(
            job_id=UUID(row["job_id"]),
            status=JobStatus(row["status"]),
            recipe_hash=row["recipe_hash"],
            request=request,
            created_at=datetime.fromisoformat(row["created_at"]),
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            finished_at=datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
            artifacts=artifacts,
            artifact_count=len(artifacts),
            error_message=row["error_message"],
            error_logs=row["error_logs"],
            assemblage_task_id=row["assemblage_task_id"],
            assemblage_opt_id=row["assemblage_opt_id"],
            progress_message=row["progress_message"],
        )


class ArtifactStorage:
    """Local artifact storage manager."""
    
    def __init__(self, base_dir: Path):
        """Initialize artifact storage.
        
        Args:
            base_dir: Base directory for artifact storage
        """
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
    
    def get_job_dir(self, job_id: UUID) -> Path:
        """Get directory for a job's artifacts.
        
        Layout: <base_dir>/<job_id>/
        """
        job_dir = self.base_dir / str(job_id)
        job_dir.mkdir(parents=True, exist_ok=True)
        return job_dir
    
    def get_artifact_path(
        self,
        job_id: UUID,
        optimization: OptimizationLevel,
        filename: str
    ) -> Path:
        """Get path for an artifact file.
        
        Layout: <base_dir>/<job_id>/<optimization>/<filename>
        """
        opt_value = optimization if isinstance(optimization, str) else optimization.value
        artifact_dir = self.get_job_dir(job_id) / opt_value
        artifact_dir.mkdir(parents=True, exist_ok=True)
        return artifact_dir / filename
    
    def save_artifact(
        self,
        job_id: UUID,
        optimization: OptimizationLevel,
        filename: str,
        content: bytes
    ) -> tuple[Path, str, int]:
        """Save artifact content to local storage.
        
        Args:
            job_id: Job UUID
            optimization: Optimization level
            filename: Artifact filename
            content: Binary content
            
        Returns:
            Tuple of (path, sha256, size_bytes)
        """
        path = self.get_artifact_path(job_id, optimization, filename)
        path.write_bytes(content)
        
        sha256 = hashlib.sha256(content).hexdigest()
        size = len(content)
        
        return path, sha256, size
    
    def list_job_artifacts(self, job_id: UUID) -> list[Path]:
        """List all artifact files for a job."""
        job_dir = self.get_job_dir(job_id)
        if not job_dir.exists():
            return []
        
        artifacts = []
        for opt_dir in job_dir.iterdir():
            if opt_dir.is_dir():
                artifacts.extend(opt_dir.iterdir())
        return artifacts
    
    def cleanup_job(self, job_id: UUID):
        """Remove all artifacts for a job."""
        import shutil
        job_dir = self.base_dir / str(job_id)
        if job_dir.exists():
            shutil.rmtree(job_dir)
