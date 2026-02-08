"""
Builder Worker
Consumes build jobs from Redis queue and executes builds.
"""
import os
import sys
import json
import time
import hashlib
import redis
import psycopg2
from pathlib import Path
from typing import Optional
import logging

# Add parent directory to path to import build_logic
sys.path.insert(0, str(Path(__file__).parent))
from build_logic import BuildJob, Compiler, OptLevel, BuildStatus
from synthetic_builder import SyntheticBuildJob, BinaryVariant


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BuildWorker:
    """
    Worker that pulls build jobs from Redis and executes them.
    """
    
    def __init__(
        self,
        redis_host: str = "redis",
        redis_port: int = 6379,
        db_host: str = "postgres",
        db_port: int = 5432,
        db_name: str = "reforge",
        db_user: str = "reforge",
        db_password: str = "reforge_pw",
        workspace_root: str = "/tmp/reforge_builds",
        artifacts_path: str = "/files/artifacts"
    ):
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.db_config = {
            "host": db_host,
            "port": db_port,
            "database": db_name,
            "user": db_user,
            "password": db_password
        }
        self.workspace_root = workspace_root
        self.artifacts_path = Path(artifacts_path)
        
        # Initialize connections
        self.redis_client: Optional["redis.Redis"] = None
        self.db_conn: Optional["psycopg2.extensions.connection"] = None
    
    def connect(self):
        """Establish Redis and PostgreSQL connections"""
        logger.info("Connecting to Redis...")
        self.redis_client = redis.Redis(
            host=self.redis_host,
            port=self.redis_port,
            decode_responses=True
        )
        self.redis_client.ping()
        logger.info("Redis connected")
        
        logger.info("Connecting to PostgreSQL...")
        self.db_conn = psycopg2.connect(**self.db_config)
        logger.info("PostgreSQL connected")
    
    def run(self):
        """Main worker loop"""
        self.connect()
        
        logger.info("Builder worker started, waiting for jobs...")
        queue_name = "builder:queue"
        
        while True:
            try:
                # Blocking pop from Redis queue (timeout 5 seconds)
                if self.redis_client is None:
                    raise RuntimeError("Redis client not connected")
                
                result = self.redis_client.blpop([queue_name], timeout=5)
                
                if result is None:
                    continue
                
                # result is a tuple: (queue_name, value)
                _, job_data = result  # type: ignore
                job = json.loads(job_data)
                
                logger.info(f"Received job: {job['job_id']}")
                self.process_job(job)
                
            except KeyboardInterrupt:
                logger.info("Worker shutting down...")
                break
            except Exception as e:
                logger.error(f"Error in worker loop: {e}", exc_info=True)
                time.sleep(5)  # Backoff on error
    
    def process_job(self, job_data: dict):
        """
        Process a single build job.
        Handles both git repository builds and synthetic source builds.
        """
        job_id = job_data["job_id"]
        job_type = job_data.get("job_type", "git_build")
        
        logger.info(f"Processing {job_type} job {job_id}")
        
        try:
            if job_type == "synthetic_build":
                self.process_synthetic_build(job_data)
            elif job_type == "git_build":
                self.process_git_build(job_data)
            else:
                logger.error(f"Unknown job type: {job_type}")
        
        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}", exc_info=True)
            # TODO: Update database with failure status
    
    def process_synthetic_build(self, job_data: dict):
        """
        Process a synthetic source code build job.
        
        This compiles a single C/C++ source file at multiple optimization levels
        and creates debug, release, and stripped variants for testing.
        """
        job_id = job_data["job_id"]
        name = job_data["name"]
        
        logger.info(f"Starting synthetic build: {name}")
        
        # Create build job
        compilers_list = [Compiler(c) for c in job_data["compilers"]]
        optimizations_list = [OptLevel(o) for o in job_data["optimizations"]]
        
        build_job = SyntheticBuildJob(
            name=name,
            source_code=job_data["source_code"],
            test_category=job_data["test_category"],
            language=job_data.get("language", "c"),
            compilers=compilers_list, #type: ignore
            optimizations=optimizations_list, #type: ignore
            artifacts_dir=self.artifacts_path / "synthetic" / name,
            timeout=30
        )
        
        # Execute build
        artifacts, errors = build_job.execute()
        
        # Save manifest
        build_job.save_manifest()
        
        # Clean up workspace
        build_job.cleanup_workspace()
        
        # Insert to database
        if artifacts:
            self.insert_synthetic_build(job_data, artifacts)
        
        logger.info(f"Synthetic build complete: {len(artifacts)} artifacts, {len(errors)} errors")
    
    def process_git_build(self, job_data: dict):
        """
        Process a git repository build job.
        
        TODO: Implement git builds using BuildJob from build_logic
        """
        job_id = job_data["job_id"]
        logger.info(f"Git build not yet implemented: {job_id}")
        
        # TODO: Implement
        # build_job = BuildJob(
        #     job_id=job_id,
        #     repo_url=job_data["repo_url"],
        #     commit_ref=job_data["commit_ref"],
        #     compiler=Compiler(job_data["compiler"]),
        #     optimizations=[OptLevel(o) for o in job_data["optimizations"]],
        #     workspace_root=self.workspace_root
        # )
        # results = build_job.execute()
        # self.save_artifacts(job_id, results)
        # self.update_database(job_id, results)
    
    def insert_synthetic_build(self, job_data: dict, artifacts):
        """Insert synthetic code and binaries to database"""
        if self.db_conn is None:
            logger.error("Database not connected")
            return
        
        cursor = None
        try:
            cursor = self.db_conn.cursor()
            
            # Calculate source hash
            source_hash = hashlib.sha256(job_data["source_code"].encode()).hexdigest()
            
            # Insert synthetic_code record
            cursor.execute("""
                INSERT INTO reforge.synthetic_code (name, source_code, source_hash, test_category, language)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (name) DO UPDATE SET
                    source_code = EXCLUDED.source_code,
                    source_hash = EXCLUDED.source_hash,
                    test_category = EXCLUDED.test_category,
                    language = EXCLUDED.language
                RETURNING id
            """, (
                job_data["name"],
                job_data["source_code"],
                source_hash,
                job_data["test_category"],
                job_data.get("language", "c")
            ))
            
            result = cursor.fetchone()
            if result is None:
                logger.error("Failed to insert synthetic_code")
                return
            
            synthetic_id = result[0]
            logger.info(f"Inserted synthetic_code: {synthetic_id}")
            
            # Insert binaries
            for artifact in artifacts:
                # Calculate actual binary file hash
                binary_hash = hashlib.sha256(open(artifact.binary_path, 'rb').read()).hexdigest()
                
                cursor.execute("""
                    INSERT INTO reforge.binaries (
                        synthetic_code_id,
                        file_path,
                        file_hash,
                        file_size,
                        compiler,
                        optimization_level,
                        has_debug_info,
                        is_stripped,
                        variant_type
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (file_hash) DO NOTHING
                """, (
                    synthetic_id,
                    str(artifact.binary_path),
                    binary_hash,
                    artifact.file_size,
                    artifact.compiler.value,
                    artifact.optimization.value,
                    artifact.has_debug_info,
                    artifact.is_stripped,
                    artifact.variant.value
                ))
            
            self.db_conn.commit()
            logger.info(f"Inserted {len(artifacts)} binaries for synthetic_code {synthetic_id}")
            
        except Exception as e:
            logger.error(f"Database insertion failed: {e}", exc_info=True)
            if self.db_conn:
                self.db_conn.rollback()
        finally:
            if cursor:
                cursor.close()


if __name__ == "__main__":
    # Read config from environment
    worker = BuildWorker(
        redis_host=os.getenv("REDIS_HOST", "redis"),
        redis_port=int(os.getenv("REDIS_PORT", "6379")),
        db_host=os.getenv("POSTGRES_HOST", "postgres"),
        db_port=int(os.getenv("POSTGRES_PORT", "5432")),
        db_name=os.getenv("POSTGRES_DB", "reforge"),
        db_user=os.getenv("POSTGRES_USER", "reforge"),
        db_password=os.getenv("POSTGRES_PASSWORD", "reforge_pw"),
        workspace_root=os.getenv("BUILDER_WORKSPACE", "/tmp/reforge_builds"),
        artifacts_path=os.getenv("ARTIFACTS_PATH", "/files/artifacts")
    )
    
    worker.run()
