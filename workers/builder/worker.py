"""
Builder Worker — builder_synth_v1

Consumes synthetic build jobs from Redis queue and executes them.
Produces ELF binaries + BuildReceipt, then persists results to PostgreSQL.

No git builds. See LOCK.md.
"""
import os
import sys
import json
import time
import logging
from pathlib import Path
from typing import Optional

import redis
import psycopg2

from receipt import OptLevel, VariantType
from synthetic_builder import SyntheticBuildJob

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("builder_worker")


class BuildWorker:
    """
    Worker that pulls synthetic build jobs from Redis and executes them.
    Results are persisted to PostgreSQL and artifacts written to disk.
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
        artifacts_path: str = "/files/artifacts",
    ):
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.db_config = {
            "host": db_host,
            "port": db_port,
            "database": db_name,
            "user": db_user,
            "password": db_password,
        }
        self.workspace_root = Path(workspace_root)
        self.artifacts_path = Path(artifacts_path)

        self.redis_client: Optional[redis.Redis] = None
        self.db_conn: Optional[psycopg2.extensions.connection] = None

    def connect(self):
        """Establish Redis and PostgreSQL connections."""
        logger.info("Connecting to Redis...")
        self.redis_client = redis.Redis(
            host=self.redis_host,
            port=self.redis_port,
            decode_responses=True,
        )
        self.redis_client.ping()
        logger.info("Redis connected")

        logger.info("Connecting to PostgreSQL...")
        self.db_conn = psycopg2.connect(**self.db_config)
        logger.info("PostgreSQL connected")

    def run(self):
        """Main worker loop — blocking pop from Redis queue."""
        self.connect()
        logger.info("Builder worker v1 started, waiting for jobs...")
        queue_name = "builder:queue"

        while True:
            try:
                if self.redis_client is None:
                    raise RuntimeError("Redis client not connected")

                result = self.redis_client.blpop([queue_name], timeout=5)
                if result is None:
                    continue

                _, job_data = result  # type: ignore
                job = json.loads(job_data)

                job_type = job.get("job_type", "")
                if job_type != "synthetic_build":
                    logger.warning(f"Unknown job type '{job_type}', skipping")
                    continue

                logger.info(f"Received synthetic build job: {job['job_id']}")
                self.process_synthetic_build(job)

            except KeyboardInterrupt:
                logger.info("Worker shutting down...")
                break
            except Exception as e:
                logger.error(f"Error in worker loop: {e}", exc_info=True)
                time.sleep(5)

    # -----------------------------------------------------------------
    # Synthetic build processing
    # -----------------------------------------------------------------

    def process_synthetic_build(self, job_data: dict):
        """
        Process a synthetic build job:
          1. Build all cells (or single target)
          2. Persist results to database
        """
        job_id = job_data["job_id"]
        name = job_data["name"]
        logger.info(f"Starting synthetic build: {name} (job_id={job_id})")

        # Parse optimizations
        opt_list = [OptLevel(o) for o in job_data.get("optimizations", ["O0", "O1", "O2", "O3"])]

        # Parse optional single-target
        target_opt = None
        target_variant = None
        target_data = job_data.get("target")
        if target_data:
            target_opt = OptLevel(target_data["optimization"])
            target_variant = VariantType(target_data["variant"])

        # Create build job
        build_job = SyntheticBuildJob(
            job_id=job_id,
            name=name,
            files=job_data["files"],
            test_category=job_data["test_category"],
            optimizations=opt_list,
            artifacts_dir=self.artifacts_path / "synthetic" / name,
            workspace_dir=self.workspace_root / name,
            timeout=120,
        )

        # Execute
        receipt = build_job.execute(
            target_opt=target_opt,
            target_variant=target_variant,
        )

        # Cleanup workspace
        build_job.cleanup_workspace()

        # Persist to database
        self.persist_results(job_data, receipt)

        logger.info(
            f"Synthetic build complete: {name} — "
            f"status={receipt.job.status}, "
            f"cells={len(receipt.builds)}"
        )

    # -----------------------------------------------------------------
    # Database persistence
    # -----------------------------------------------------------------

    def persist_results(self, job_data: dict, receipt):
        """Insert synthetic_code + binaries rows into PostgreSQL."""
        if self.db_conn is None:
            logger.error("Database not connected — cannot persist results")
            return

        cursor = None
        try:
            cursor = self.db_conn.cursor()

            # Build source_files JSONB from receipt
            source_files_json = json.dumps([
                {
                    "path_rel": sf.path_rel,
                    "sha256": sf.sha256,
                    "size_bytes": sf.size_bytes,
                    "role": sf.role.value,
                }
                for sf in receipt.source.files
            ])

            # Receipt summary as metadata
            metadata = {
                "profile": receipt.profile.profile_id,
                "builder_version": receipt.builder.version,
                "toolchain": receipt.toolchain.model_dump(),
                "job_status": receipt.job.status,
                "cell_count": len(receipt.builds),
                "success_count": sum(
                    1 for c in receipt.builds if c.status.value == "SUCCESS"
                ),
                "receipt_path": f"synthetic/{job_data['name']}/build_receipt.json",
            }

            # Upsert synthetic_code
            cursor.execute(
                """
                INSERT INTO reforge.synthetic_code (
                    id, name, test_category, language,
                    snapshot_sha256, status, file_count,
                    source_files, metadata
                ) VALUES (
                    %s::uuid, %s, %s, %s,
                    %s, %s, %s,
                    %s::jsonb, %s::jsonb
                )
                ON CONFLICT (name) DO UPDATE SET
                    test_category = EXCLUDED.test_category,
                    language = EXCLUDED.language,
                    snapshot_sha256 = EXCLUDED.snapshot_sha256,
                    status = EXCLUDED.status,
                    file_count = EXCLUDED.file_count,
                    source_files = EXCLUDED.source_files,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
                RETURNING id
                """,
                (
                    job_data["job_id"],
                    job_data["name"],
                    job_data["test_category"],
                    job_data.get("language", "c"),
                    receipt.source.snapshot_sha256,
                    receipt.job.status,
                    len(receipt.source.files),
                    source_files_json,
                    json.dumps(metadata),
                ),
            )

            result = cursor.fetchone()
            if result is None:
                logger.error("Failed to insert synthetic_code")
                return
            synthetic_id = result[0]

            # Delete existing binaries for this synthetic_code (full rebuild)
            cursor.execute(
                "DELETE FROM reforge.binaries WHERE synthetic_code_id = %s",
                (synthetic_id,),
            )

            # Insert binaries from receipt
            inserted = 0
            for cell in receipt.builds:
                if cell.artifact is None:
                    continue

                # Resolve full file path
                artifact_abs = self.artifacts_path / "synthetic" / job_data["name"] / cell.artifact.path_rel
                file_path = str(artifact_abs)

                has_debug = False
                is_stripped = False
                if cell.variant == "debug":
                    has_debug = (
                        cell.artifact.debug_presence is not None
                        and cell.artifact.debug_presence.has_debug_sections
                    )
                elif cell.variant == "stripped":
                    is_stripped = True

                elf_meta = cell.artifact.elf.model_dump() if cell.artifact.elf else {}

                cursor.execute(
                    """
                    INSERT INTO reforge.binaries (
                        synthetic_code_id,
                        file_path, file_hash, file_size,
                        compiler, optimization_level, variant_type,
                        architecture, has_debug_info, is_stripped,
                        elf_metadata, metadata
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s::jsonb, %s::jsonb
                    )
                    ON CONFLICT (file_hash) DO UPDATE SET
                        file_path = EXCLUDED.file_path,
                        file_size = EXCLUDED.file_size,
                        updated_at = NOW()
                    """,
                    (
                        synthetic_id,
                        file_path,
                        cell.artifact.sha256,
                        cell.artifact.size_bytes,
                        "gcc",  # profile-locked
                        cell.optimization,
                        cell.variant,
                        cell.artifact.elf.arch if cell.artifact.elf else "x86_64",
                        has_debug,
                        is_stripped,
                        json.dumps(elf_meta),
                        json.dumps({
                            "flags": [f.value for f in cell.flags],
                            "cell_status": cell.status.value,
                        }),
                    ),
                )
                inserted += 1

            self.db_conn.commit()
            logger.info(
                f"Persisted synthetic_code {synthetic_id} "
                f"with {inserted} binaries"
            )

        except Exception as e:
            logger.error(f"Database persistence failed: {e}", exc_info=True)
            if self.db_conn:
                self.db_conn.rollback()
        finally:
            if cursor:
                cursor.close()


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    worker = BuildWorker(
        redis_host=os.getenv("REDIS_HOST", "redis"),
        redis_port=int(os.getenv("REDIS_PORT", "6379")),
        db_host=os.getenv("POSTGRES_HOST", "postgres"),
        db_port=int(os.getenv("POSTGRES_PORT", "5432")),
        db_name=os.getenv("POSTGRES_DB", "reforge"),
        db_user=os.getenv("POSTGRES_USER", "reforge"),
        db_password=os.getenv("POSTGRES_PASSWORD", "reforge_pw"),
        workspace_root=os.getenv("BUILDER_WORKSPACE", "/tmp/reforge_builds"),
        artifacts_path=os.getenv("ARTIFACTS_PATH", "/files/artifacts"),
    )
    worker.run()
