"""Assemblage Database client for submitting builds via direct DB insertion.

This module encapsulates database interactions with Assemblage.
Instead of submitting to RabbitMQ, we insert directly into the Assemblage
database with status='INIT', which the coordinator automatically picks up.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

import psycopg2
import psycopg2.extensions
import psycopg2.extras

from ..models import BuildRecipe, BuildRequest, JobStatus, OptimizationLevel

logger = logging.getLogger(__name__)


# Assemblage status values
class AssemblageCloneStatus(str, Enum):
    """Assemblage clone status codes."""
    NOT_STARTED = "NOT_STARTED"
    PROCESSING = "PROCESSING"
    FAILED = "FAILED"
    SUCCESS = "SUCCESS"
    TIMEOUT = "TIMEOUT"


class AssemblageBuildStatus(str, Enum):
    """Assemblage build status codes."""
    INIT = "INIT"
    PROCESSING = "PROCESSING"
    FAILED = "FAILED"
    SUCCESS = "SUCCESS"
    TIMEOUT = "TIMEOUT"


@dataclass
class AssemblageConfig:
    """Configuration for Assemblage database connection."""
    db_host: str = "assemblage-db"
    db_port: int = 5432
    db_name: str = "assemblage"
    db_user: str = "assemblage"
    db_password: str = "assemblage_pw"
    connection_timeout: int = 10
    retry_delay: int = 5
    max_retries: int = 3


@dataclass
class TaskStatus:
    """Current status of a task from Assemblage database."""
    repo_id: int
    build_opt_id: int
    build_status: str
    clone_status: str
    build_msg: Optional[str]
    clone_msg: Optional[str]
    build_time: Optional[int]
    commit_hexsha: Optional[str]
    url: str


class AssemblageClient:
    """Client for interacting with Assemblage via database insertion.
    
    Instead of submitting to RabbitMQ directly, this inserts into the
    Assemblage database with status='INIT', which the coordinator
    automatically picks up and dispatches.
    """
    
    def __init__(self, config: AssemblageConfig):
        """Initialize Assemblage client.
        
        Args:
            config: Database connection configuration
        """
        self.config = config
        self._conn: Optional[psycopg2.extensions.connection] = None
    
    def connect(self) -> bool:
        """Establish connection to Assemblage database.
        
        Returns:
            True if connection successful
        """
        if self._conn and not self._conn.closed:
            return True
        
        for attempt in range(self.config.max_retries):
            try:
                self._conn = psycopg2.connect(
                    host=self.config.db_host,
                    port=self.config.db_port,
                    database=self.config.db_name,
                    user=self.config.db_user,
                    password=self.config.db_password,
                    connect_timeout=self.config.connection_timeout,
                )
                logger.info(f"Connected to Assemblage DB at {self.config.db_host}:{self.config.db_port}")
                return True
            except psycopg2.Error as e:
                logger.warning(f"Connection attempt {attempt + 1} failed: {e}")
                if attempt < self.config.max_retries - 1:
                    import time
                    time.sleep(self.config.retry_delay)
        
        logger.error(f"Failed to connect after {self.config.max_retries} attempts")
        return False
    
    def disconnect(self):
        """Close database connection."""
        if self._conn and not self._conn.closed:
            self._conn.close()
            self._conn = None
            logger.info("Disconnected from Assemblage DB")
    
    def check_connection(self) -> bool:
        """Check if database connection is alive.
        
        Returns:
            True if connected
        """
        try:
            if not self._conn or self._conn.closed:
                return self.connect()
            
            # Test with simple query
            with self._conn.cursor() as cur:
                cur.execute("SELECT 1")
            return True
        except Exception as e:
            logger.error(f"Connection check failed: {e}")
            return False
    
    def submit_build(
        self,
        request: BuildRequest,
        build_opt_id: int = 1,
        priority: str = "high",
    ) -> tuple[int, int]:
        """Submit build by inserting into Assemblage database.
        
        The coordinator will automatically pick up tasks with status='INIT'
        and dispatch them to builders.
        
        Args:
            request: Build request
            build_opt_id: Assemblage build option ID (1 or 2)
            priority: Priority level (low/medium/high)
            
        Returns:
            Tuple of (repo_id, build_opt_id)
        """
        if not self._conn or self._conn.closed:
            if not self.connect():
                raise ConnectionError("Cannot connect to Assemblage database")
        
        assert self._conn is not None, "Connection should be established"
        
        with self._conn.cursor() as cur:
            try:
                # Get build system value
                build_system = request.recipe.build_system
                if hasattr(build_system, 'value'):
                    build_system = build_system.value
                
                # Determine language from request or default to CPP (DB enum key)
                language = 'CPP'

                # Derive simple defaults for required columns
                repo_name = request.repo_url.rstrip('/').split('/')[-1]
                if repo_name.endswith('.git'):
                    repo_name = repo_name[:-4]
                branch = request.commit_ref or 'main'
                owner_id = 0  # unknown owner
                description = ''
                size = 0
                fork_from = 0
                forked_commit_id = 0
                deleted = False
                updated_at = datetime.utcnow()
                # Map priority to Assemblage enum values (LOW/MID/HIGH)
                priority_value = priority if isinstance(priority, str) else str(priority)
                if priority_value.lower() in ("low", "0", "false"):
                    priority_value = "LOW"
                elif priority_value.lower() in ("mid", "medium", "1"):
                    priority_value = "MID"
                else:
                    priority_value = "HIGH"
                
                # 1. Insert or get project
                cur.execute("""
                    INSERT INTO projects (url, name, owner_id, description, language, fork_from, deleted, updated_at, forked_commit_id, branch, priority, size, build_system, created_at, commit_hexsha)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (url) DO UPDATE SET url = EXCLUDED.url
                    RETURNING id
                """, (
                    request.repo_url,
                    repo_name,
                    owner_id,
                    description,
                    language,
                    fork_from,
                    deleted,
                    updated_at,
                    forked_commit_id,
                    branch,
                    priority_value,
                    size,
                    build_system,
                    datetime.utcnow(),
                    request.commit_ref or '',
                ))
                
                result = cur.fetchone()
                if not result:
                    raise ValueError("Failed to insert or retrieve project")
                repo_id = result[0]
                
                # 2. Insert build status - coordinator will dispatch this
                cur.execute("""
                    INSERT INTO b_status (
                        repo_id, build_opt_id, build_status, clone_status,
                        priority, mod_timestamp, commit_hexsha, clone_msg, build_msg, build_time
                    )
                    VALUES (%s, %s, 'INIT', 'NOT_STARTED', %s, %s, %s, '', '', 0)
                    RETURNING id
                """, (
                    repo_id,
                    build_opt_id,
                    priority_value,
                    int(datetime.utcnow().timestamp()),
                    request.commit_ref or '',
                ))
                
                result = cur.fetchone()
                if not result:
                    raise ValueError("Failed to insert build status")
                status_id = result[0]
                
                self._conn.commit()
                logger.info(f"Inserted build task: repo_id={repo_id}, status_id={status_id}, opt={build_opt_id}")
                
                return repo_id, build_opt_id
                
            except Exception as e:
                self._conn.rollback()
                logger.error(f"Failed to submit build: {e}")
                raise
    
    def get_task_status(
        self,
        repo_id: int,
        build_opt_id: int,
    ) -> Optional[TaskStatus]:
        """Query current build status from database.
        
        Args:
            repo_id: Repository ID
            build_opt_id: Build option ID
            
        Returns:
            TaskStatus or None if not found
        """
        if not self._conn or self._conn.closed:
            if not self.connect():
                return None
        
        assert self._conn is not None, "Connection should be established"
        
        with self._conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            try:
                cur.execute("""
                    SELECT
                        b.repo_id,
                        b.build_opt_id,
                        b.build_status,
                        b.clone_status,
                        b.build_msg,
                        b.clone_msg,
                        b.build_time,
                        b.commit_hexsha,
                        p.url
                    FROM b_status b
                    JOIN projects p ON b.repo_id = p.id
                    WHERE b.repo_id = %s AND b.build_opt_id = %s
                    ORDER BY b.mod_timestamp DESC, b.id DESC
                    LIMIT 1
                """, (repo_id, build_opt_id))
                
                row = cur.fetchone()
                if not row:
                    logger.debug(
                        f"No status row found for repo_id={repo_id}, build_opt_id={build_opt_id}. "
                        "Task may not be in b_status table yet."
                    )
                    return None
                
                return TaskStatus(
                    repo_id=row['repo_id'],
                    build_opt_id=row['build_opt_id'],
                    build_status=row['build_status'],
                    clone_status=row['clone_status'],
                    build_msg=row['build_msg'],
                    clone_msg=row['clone_msg'],
                    build_time=row['build_time'],
                    commit_hexsha=row['commit_hexsha'],
                    url=row['url'],
                )
                
            except Exception as e:
                logger.error(f"Failed to get task status for repo_id={repo_id}, opt={build_opt_id}: {e}", exc_info=True)
                try:
                    self._conn.rollback()
                except Exception:
                    pass
                return None
    
    def get_binaries_for_task(
        self,
        repo_id: int,
    ) -> list[dict]:
        """Get binary artifacts from database.
        
        Args:
            repo_id: Repository ID
            
        Returns:
            List of binary records
        """
        if not self._conn or self._conn.closed:
            if not self.connect():
                return []
        
        assert self._conn is not None, "Connection should be established"
        
        with self._conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            try:
                cur.execute("""
                    SELECT
                        file_name,
                        opt_level,
                        save_path,
                        sha256,
                        file_size
                    FROM binaries
                    WHERE repo_id = %s
                """, (repo_id,))
                
                return [
                    {
                        'filename': row['file_name'],
                        'optimization': row['opt_level'],
                        'save_path': row['save_path'],
                        'sha256': row['sha256'],
                        'size': row['file_size'],
                    }
                    for row in cur.fetchall()
                ]
                
            except Exception as e:
                logger.error(f"Failed to get binaries: {e}")
                return []


def map_assemblage_status_to_job_status(
    clone_status: str,
    build_status: str,
) -> JobStatus:
    """Map Assemblage status codes to bridge JobStatus.
    
    Args:
        clone_status: Clone phase status
        build_status: Build phase status
        
    Returns:
        Corresponding JobStatus
    """
    # Build status takes precedence
    if build_status == "SUCCESS":
        return JobStatus.SUCCESS
    elif build_status == "FAILED":
        return JobStatus.FAILED
    elif build_status == "TIMEOUT":
        return JobStatus.TIMEOUT
    elif build_status == "PROCESSING":
        return JobStatus.BUILDING
    
    # Check clone status
    if clone_status == "SUCCESS":
        return JobStatus.BUILDING  # Clone done, building next
    elif clone_status == "FAILED":
        return JobStatus.FAILED
    elif clone_status == "TIMEOUT":
        return JobStatus.TIMEOUT
    elif clone_status == "PROCESSING":
        return JobStatus.CLONING
    elif clone_status == "NOT_STARTED":
        return JobStatus.QUEUED
    
    return JobStatus.QUEUED
