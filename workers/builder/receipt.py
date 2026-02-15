"""
BuildReceipt Schema — builder_synth_v2

Single authoritative JSON receipt per synthetic build job.
Records exactly what was built, how, and with what outcome.

No DWARF semantics, no alignment, no oracle logic.
"""
from __future__ import annotations

import hashlib
import io
import tarfile
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================

class OptLevel(str, Enum):
    """Optimization levels (exact strings, no prefix dash)."""
    O0 = "O0"
    O1 = "O1"
    O2 = "O2"
    O3 = "O3"


class VariantType(str, Enum):
    """Binary variant within a build cell."""
    DEBUG = "debug"
    RELEASE = "release"
    STRIPPED = "stripped"


class CellStatus(str, Enum):
    """Status of a single build cell."""
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


class PhaseStatus(str, Enum):
    """Status of a single phase (compile/link/strip)."""
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    SKIPPED = "SKIPPED"


class BuildFlag(str, Enum):
    """Flags raised per build cell. Builder-only, no oracle flags."""
    BUILD_FAILED = "BUILD_FAILED"
    TIMEOUT = "TIMEOUT"
    NO_ARTIFACT = "NO_ARTIFACT"
    COMPILE_UNIT_FAILED = "COMPILE_UNIT_FAILED"
    LINK_FAILED = "LINK_FAILED"
    DEBUG_EXPECTED_MISSING = "DEBUG_EXPECTED_MISSING"
    STRIP_FAILED = "STRIP_FAILED"
    STRIP_EXPECTED_MISSING = "STRIP_EXPECTED_MISSING"
    NON_ELF_OUTPUT = "NON_ELF_OUTPUT"


class FileRole(str, Enum):
    """Role of a source file within the project."""
    C_UNIT = "c_unit"
    HEADER = "header"
    OTHER = "other"


# =============================================================================
# Source Identity
# =============================================================================

class SourceFile(BaseModel):
    """A single source file in the project snapshot."""
    path_rel: str
    sha256: str
    size_bytes: int
    role: FileRole


class SourceIdentity(BaseModel):
    """Identity of the source input for this build job."""
    kind: str = "synthetic_local_files"
    entry_type: str  # "single_file" or "multi_file"
    entry_c_files: List[str]  # relative paths of .c compilation units
    files: List[SourceFile]
    snapshot_sha256: str  # hash over normalized archive of all source files
    language: str = "c"


# =============================================================================
# Toolchain Identity
# =============================================================================

class ToolchainIdentity(BaseModel):
    """Immutable record of the build environment."""
    container_id: Optional[str] = None
    gcc_version: str
    binutils_version: str  # ld --version first line
    strip_version: str  # strip --version first line
    os_release: str  # /etc/os-release PRETTY_NAME or ID+VERSION_ID
    kernel: str  # uname -r
    arch: str  # uname -m


# =============================================================================
# Profile
# =============================================================================

class ProfileV1(BaseModel):
    """The single supported build profile for v1."""
    profile_id: str = "linux-x86_64-elf-gcc-c"
    compiler: str = "gcc"
    output_format: str = "ELF"
    arch: str = "x86_64"
    language: str = "c"
    link_libs: List[str] = Field(
        default=["-lm"],
        description="Allowed link libraries baked into the profile"
    )


# =============================================================================
# Compile Policy
# =============================================================================

class VariantDelta(BaseModel):
    """Per-variant compile policy delta."""
    add_cflags: List[str] = []
    dwarf_presence_check: bool = False
    strip: bool = False


class CompilePolicy(BaseModel):
    """Requested compilation policy for this job."""
    base_cflags: str
    include_dirs: List[str] = []
    defines: List[str] = []
    link_libs: List[str] = []
    variant_deltas: Dict[str, VariantDelta] = Field(default_factory=lambda: {
        "debug": VariantDelta(
            add_cflags=["-g"],
            dwarf_presence_check=True,
        ),
        "release": VariantDelta(
            add_cflags=[],
            dwarf_presence_check=False,
        ),
        "stripped": VariantDelta(
            add_cflags=[],
            dwarf_presence_check=False,
            strip=True,
        ),
    })


# =============================================================================
# Phase Results (compile / link / strip)
# =============================================================================

class CompileUnitResult(BaseModel):
    """Result of compiling a single .c translation unit."""
    source_path_rel: str
    object_path_rel: str
    exit_code: int
    stdout_path_rel: Optional[str] = None
    stderr_path_rel: Optional[str] = None
    duration_ms: int = 0


class CompilePhaseSummary(BaseModel):
    """Summary of the compile phase across all TUs."""
    compiled_units: int = 0
    failed_units: int = 0


class CompilePhase(BaseModel):
    """Compile phase: all .c → .o."""
    command_template: str  # representative gcc -c command
    units: List[CompileUnitResult] = []
    summary: CompilePhaseSummary = CompilePhaseSummary()
    status: PhaseStatus = PhaseStatus.SUCCESS


class LinkPhase(BaseModel):
    """Link phase: all .o → executable."""
    command: str = ""
    exit_code: int = -1
    stdout_path_rel: Optional[str] = None
    stderr_path_rel: Optional[str] = None
    duration_ms: int = 0
    status: PhaseStatus = PhaseStatus.SKIPPED


class StripPhase(BaseModel):
    """Strip phase (stripped variant only)."""
    command: str = ""
    exit_code: int = -1
    stdout_path_rel: Optional[str] = None
    stderr_path_rel: Optional[str] = None
    duration_ms: int = 0
    status: PhaseStatus = PhaseStatus.SKIPPED


# =============================================================================
# Preprocess Phase (v2)
# =============================================================================

class PreprocessUnitResult(BaseModel):
    """Result of preprocessing a single .c → .i translation unit."""
    source_path_rel: str
    output_path_rel: str
    output_sha256: Optional[str] = None
    exit_code: int
    stdout_path_rel: Optional[str] = None
    stderr_path_rel: Optional[str] = None
    duration_ms: int = 0


class PreprocessPhase(BaseModel):
    """
    Preprocess phase: all .c → .i via gcc -E.

    Top-level in the receipt (not per-cell) because preprocessing
    is optimization-independent.
    """
    command_template: str
    units: List[PreprocessUnitResult] = []
    status: PhaseStatus = PhaseStatus.SUCCESS


# =============================================================================
# ELF Metadata & Artifact
# =============================================================================

class ElfMeta(BaseModel):
    """Minimal ELF metadata — no DWARF semantics."""
    elf_type: str = ""  # ET_EXEC, ET_DYN, etc.
    arch: str = ""  # EM_X86_64, etc.
    build_id: Optional[str] = None


class DebugPresence(BaseModel):
    """Debug section presence check (debug variant only)."""
    has_debug_sections: bool = False
    debug_sections: List[str] = []


class ArtifactMeta(BaseModel):
    """Metadata for a produced binary artifact."""
    path_rel: str
    sha256: str
    size_bytes: int
    elf: ElfMeta = ElfMeta()
    debug_presence: Optional[DebugPresence] = None  # only for debug variant


# =============================================================================
# Build Cell (one optimization × variant combination)
# =============================================================================

class BuildCell(BaseModel):
    """
    Result of building one (optimization, variant) combination.
    Contains the full phase breakdown: compile → link → strip.
    """
    optimization: str
    variant: str
    status: CellStatus = CellStatus.FAILED
    flags: List[BuildFlag] = []

    # Phases
    compile: CompilePhase = CompilePhase(command_template="")
    link: LinkPhase = LinkPhase()
    strip: Optional[StripPhase] = None  # only for stripped variant

    # Artifact (only if link succeeded)
    artifact: Optional[ArtifactMeta] = None


# =============================================================================
# Top-level BuildReceipt
# =============================================================================

class BuilderInfo(BaseModel):
    """Identifies the builder package."""
    name: str = "builder_synth_v2"
    version: str = "v2"
    profile_id: str = "linux-x86_64-elf-gcc-c"
    lock_text_hash: Optional[str] = None  # sha256 of LOCK_v2.md


class JobInfo(BaseModel):
    """Job-level metadata."""
    job_id: str
    name: str
    created_at: str  # ISO 8601
    finished_at: Optional[str] = None
    status: str = "BUILDING"  # BUILDING, SUCCESS, PARTIAL, FAILED


class RequestedMatrix(BaseModel):
    """What was requested to be built."""
    optimizations: List[str]
    variants: List[str]
    compile_policy: CompilePolicy


class BuildReceipt(BaseModel):
    """
    Single authoritative receipt for a synthetic build job.

    One file per job: build_receipt.json
    Contains full provenance for all build cells.
    """
    builder: BuilderInfo = BuilderInfo()
    job: JobInfo
    source: SourceIdentity
    toolchain: ToolchainIdentity
    profile: ProfileV1 = ProfileV1()
    requested: RequestedMatrix
    preprocess: Optional[PreprocessPhase] = None  # v2: gcc -E results
    builds: List[BuildCell] = []

    def compute_status(self) -> str:
        """Derive job status from cell results."""
        if not self.builds:
            return "FAILED"
        statuses = [c.status for c in self.builds]
        if all(s == CellStatus.SUCCESS for s in statuses):
            return "SUCCESS"
        if any(s == CellStatus.SUCCESS for s in statuses):
            return "PARTIAL"
        return "FAILED"


# =============================================================================
# Helpers
# =============================================================================

def hash_file(path: Path) -> str:
    """SHA-256 of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_snapshot_hash(files: List[SourceFile], base_dir: Path) -> str:
    """
    Compute a deterministic hash over all source files.
    Sort by path_rel, then hash (path + content) for each.
    """
    h = hashlib.sha256()
    for sf in sorted(files, key=lambda f: f.path_rel):
        h.update(sf.path_rel.encode("utf-8"))
        file_path = base_dir / sf.path_rel
        if file_path.exists():
            h.update(file_path.read_bytes())
    return h.hexdigest()


def now_iso() -> str:
    """Current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()
