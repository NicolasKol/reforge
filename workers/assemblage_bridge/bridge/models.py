"""Pydantic models for the Assemblage Bridge API."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class OptimizationLevel(str, Enum):
    """Build optimization levels matching Assemblage's OptLevel."""
    NONE = "opt_NONE"      # -O0
    LOW = "opt_LOW"        # -O1
    MEDIUM = "opt_MEDIUM"  # -O2
    HIGH = "opt_HIGH"      # -O3


class Compiler(str, Enum):
    """Supported compilers."""
    GCC = "gcc"
    CLANG = "clang"
    MSVC = "msvc"


class Platform(str, Enum):
    """Target platforms."""
    LINUX = "linux"
    WINDOWS = "windows"
    DARWIN = "darwin"


class Architecture(str, Enum):
    """Target architectures."""
    X64 = "x64"
    X86 = "x86"


class Priority(str, Enum):
    """Build priority levels matching Assemblage PriorityStatus."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class BuildSystem(str, Enum):
    """Supported build systems."""
    CMAKE = "cmake"
    MAKE = "make"
    AUTOCONF = "autoconf"
    MESON = "meson"
    CARGO = "cargo"
    UNKNOWN = "unknown"


class BuildRecipe(BaseModel):
    """Build configuration recipe - defines how to compile the project."""
    compiler: Compiler = Field(default=Compiler.CLANG, description="Compiler to use (clang or gcc)")
    platform: Platform = Field(default=Platform.LINUX, description="Target platform")
    architecture: Architecture = Field(default=Architecture.X64, description="Target architecture")
    optimizations: list[OptimizationLevel] = Field(
        default=[OptimizationLevel.NONE, OptimizationLevel.HIGH],
        description="Optimization levels to build"
    )
    build_system: BuildSystem = Field(default=BuildSystem.CMAKE, description="Build system type")
    save_assembly: bool = Field(default=False, description="Save assembly output")

    class Config:
        use_enum_values = True


class BuildRequest(BaseModel):
    """Request to build a project from source."""
    repo_url: str = Field(..., description="Git repository URL")
    commit_ref: Optional[str] = Field(default="master", description="Commit hash, branch, or tag")
    recipe: BuildRecipe = Field(default_factory=BuildRecipe, description="Build configuration")
    priority: Priority = Field(default=Priority.HIGH, description="Build priority")
    
    @field_validator('priority', mode='before')
    @classmethod
    def convert_priority(cls, v):
        """Convert old integer priority (0-10) to Priority enum for backward compatibility."""
        if isinstance(v, int):
            # Map old integer values to new enum
            if v <= 3:
                return Priority.LOW
            elif v <= 7:
                return Priority.MEDIUM
            else:
                return Priority.HIGH
        return v


class JobStatus(str, Enum):
    """Job lifecycle states."""
    QUEUED = "QUEUED"
    CLONING = "CLONING"
    BUILDING = "BUILDING"
    UPLOADING = "UPLOADING"
    DOWNLOADING = "DOWNLOADING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"


class ArtifactInfo(BaseModel):
    """Information about a built artifact."""
    filename: str
    local_path: str
    s3_key: Optional[str] = None
    sha256: str
    size_bytes: int
    optimization: OptimizationLevel
    created_at: datetime


class JobResponse(BaseModel):
    """Response model for job status queries."""
    job_id: UUID
    status: JobStatus
    recipe_hash: str
    request: BuildRequest
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    artifacts: list[ArtifactInfo] = Field(default_factory=list)
    artifact_count: int = 0
    error_message: Optional[str] = None
    error_logs: Optional[str] = None
    assemblage_task_id: Optional[int] = None
    assemblage_opt_id: Optional[int] = None
    progress_message: Optional[str] = None


class BuildSubmitResponse(BaseModel):
    """Response when submitting a new build job."""
    job_id: UUID
    status: JobStatus
    recipe_hash: str
    message: str


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    rabbitmq_connected: bool
    minio_connected: bool
    jobs_db_ok: bool
    version: str = "1.0.0"


class JobListResponse(BaseModel):
    """Response for listing jobs."""
    jobs: list[JobResponse]
    total: int
    offset: int
    limit: int
