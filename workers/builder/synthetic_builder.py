"""
Synthetic ELF Builder — builder_synth_v2

Compile synthetic C source files to ELF binaries with GCC across multiple
optimization levels and three variants (debug / release / stripped).
Additionally emit preprocessed translation units (.i) via gcc -E.

Produces:
  - ELF binaries on disk in a stable layout
  - Preprocessed .i files (one per TU, optimization-independent)
  - Per-phase logs (compile/link/strip/preprocess stdout+stderr)
  - A single BuildReceipt JSON for provenance

Scope: "Compile synthetic C to ELF with GCC; emit artifacts,
        preprocessed TUs, and receipt.
        No DWARF semantics, no alignment, no repo builds."

See LOCK_v2.md for the full scope contract.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from elftools.elf.elffile import ELFFile
from elftools.common.exceptions import ELFError

from receipt import (
    ArtifactMeta,
    BuildCell,
    BuilderInfo,
    BuildFlag,
    BuildReceipt,
    CellStatus,
    CompilePhase,
    CompilePhaseSummary,
    CompilePolicy,
    CompileUnitResult,
    DebugPresence,
    ElfMeta,
    FileRole,
    JobInfo,
    LinkPhase,
    OptLevel,
    PhaseStatus,
    PreprocessPhase,
    PreprocessUnitResult,
    ProfileV1,
    RequestedMatrix,
    SourceFile,
    SourceIdentity,
    StripPhase,
    ToolchainIdentity,
    VariantDelta,
    VariantType,
    compute_snapshot_hash,
    hash_file,
    now_iso,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Profile — v1 constants
# =============================================================================

PROFILE = ProfileV1()

# Base flags baked into the profile
BASE_CFLAGS = "-std=c11 -Wno-error -fno-omit-frame-pointer -mno-omit-leaf-frame-pointer -no-pie"

VARIANT_DELTAS: Dict[str, VariantDelta] = {
    "debug": VariantDelta(add_cflags=["-g"], dwarf_presence_check=True),
    "release": VariantDelta(add_cflags=[], dwarf_presence_check=False),
    "stripped": VariantDelta(add_cflags=[], dwarf_presence_check=False, strip=True),
}

DEFAULT_OPTIMIZATIONS = [OptLevel.O0, OptLevel.O1, OptLevel.O2, OptLevel.O3]
DEFAULT_VARIANTS = [VariantType.DEBUG, VariantType.RELEASE, VariantType.STRIPPED]


# =============================================================================
# Toolchain Discovery (runs once per worker lifetime)
# =============================================================================

_cached_toolchain: Optional[ToolchainIdentity] = None


def _run_quiet(cmd: List[str], timeout: int = 5) -> str:
    """Run a command and return stdout, swallowing errors."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return "unknown"


def capture_toolchain() -> ToolchainIdentity:
    """Capture immutable toolchain identity. Cached after first call."""
    global _cached_toolchain
    if _cached_toolchain is not None:
        return _cached_toolchain

    # GCC version — first line of gcc --version
    gcc_raw = _run_quiet(["gcc", "--version"])
    gcc_version = gcc_raw.splitlines()[0] if gcc_raw else "unknown"

    # Binutils / ld
    ld_raw = _run_quiet(["ld", "--version"])
    ld_version = ld_raw.splitlines()[0] if ld_raw else "unknown"

    # strip
    strip_raw = _run_quiet(["strip", "--version"])
    strip_version = strip_raw.splitlines()[0] if strip_raw else "unknown"

    # OS
    os_release = "unknown"
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if line.startswith("PRETTY_NAME="):
                os_release = line.split("=", 1)[1].strip('"')
                break
    except Exception:
        pass

    kernel = _run_quiet(["uname", "-r"])
    arch = _run_quiet(["uname", "-m"])

    # Container ID (best-effort)
    container_id = os.environ.get("HOSTNAME", None)

    _cached_toolchain = ToolchainIdentity(
        container_id=container_id,
        gcc_version=gcc_version,
        binutils_version=ld_version,
        strip_version=strip_version,
        os_release=os_release,
        kernel=kernel,
        arch=arch,
    )
    return _cached_toolchain


# =============================================================================
# ELF Validation
# =============================================================================

def validate_elf(path: Path) -> Tuple[bool, ElfMeta]:
    """
    Validate that a file is a valid ELF binary and extract metadata.
    Returns (is_valid, meta).  No DWARF parsing.
    """
    try:
        with open(path, "rb") as f:
            elf = ELFFile(f)
            elf_type = elf.header["e_type"]
            machine = elf.header["e_machine"]

            # Extract build-id if present
            build_id = None
            for section in elf.iter_sections():
                if section.name == ".note.gnu.build-id":
                    try:
                        for note in section.iter_notes():
                            if note["n_type"] == "NT_GNU_BUILD_ID":
                                build_id = note["n_desc"]
                    except Exception:
                        pass

            return True, ElfMeta(
                elf_type=elf_type,
                arch=machine,
                build_id=build_id,
            )
    except (ELFError, Exception) as e:
        logger.warning(f"ELF validation failed for {path}: {e}")
        return False, ElfMeta()


def check_debug_sections(path: Path) -> DebugPresence:
    """
    Check for .debug_* section presence using pyelftools.
    Presence check only — no DWARF semantic parsing.
    """
    sections: List[str] = []
    try:
        with open(path, "rb") as f:
            elf = ELFFile(f)
            for section in elf.iter_sections():
                if section.name.startswith(".debug_"):
                    sections.append(section.name)
    except Exception as e:
        logger.warning(f"Debug section check failed for {path}: {e}")

    return DebugPresence(
        has_debug_sections=len(sections) > 0,
        debug_sections=sections,
    )


# =============================================================================
# Source File Helpers
# =============================================================================

def classify_file_role(filename: str) -> FileRole:
    """Determine the role of a source file by extension."""
    ext = Path(filename).suffix.lower()
    if ext == ".c":
        return FileRole.C_UNIT
    elif ext == ".h":
        return FileRole.HEADER
    return FileRole.OTHER


def catalog_source_files(src_dir: Path) -> List[SourceFile]:
    """Walk src_dir and catalog every file with hash, size, and role."""
    files: List[SourceFile] = []
    for fpath in sorted(src_dir.rglob("*")):
        if not fpath.is_file():
            continue
        rel = fpath.relative_to(src_dir).as_posix()
        files.append(SourceFile(
            path_rel=rel,
            sha256=hash_file(fpath),
            size_bytes=fpath.stat().st_size,
            role=classify_file_role(fpath.name),
        ))
    return files


# =============================================================================
# SyntheticBuildJob
# =============================================================================

class SyntheticBuildJob:
    """
    Builds synthetic C source files into ELF binaries across the full matrix:
      (optimization) × (variant) = build cells.

    Each cell goes through phases: compile → link → [strip].
    Multi-file: all *.c under src/ are compiled as separate TUs then linked.

    Emits a single BuildReceipt JSON at job level.
    """

    def __init__(
        self,
        job_id: str,
        name: str,
        files: List[Dict[str, str]],
        test_category: str,
        optimizations: Optional[List[OptLevel]] = None,
        variants: Optional[List[VariantType]] = None,
        workspace_dir: Optional[Path] = None,
        artifacts_dir: Optional[Path] = None,
        timeout: int = 120,
    ):
        """
        Args:
            job_id: Unique job identifier (UUID string).
            name: Human-readable test case name.
            files: List of dicts with {"filename": "...", "content": "..."}.
            test_category: Category tag (arrays, loops, strings, etc.).
            optimizations: Optimization levels (default O0–O3).
            variants: Variants to build (default all three).
            workspace_dir: Temporary build root.
            artifacts_dir: Final artifact storage root.
            timeout: Per-phase timeout in seconds.
        """
        self.job_id = job_id
        self.name = name
        self.files_input = files
        self.test_category = test_category
        self.optimizations = optimizations or list(DEFAULT_OPTIMIZATIONS)
        self.variants = variants or list(DEFAULT_VARIANTS)
        self.timeout = timeout

        # Directories
        self.workspace_dir = workspace_dir or Path("/tmp/reforge_builds") / name
        self.src_dir = self.workspace_dir / "src"
        self.artifacts_dir = artifacts_dir or Path("/files/artifacts/synthetic") / name

        # Results
        self.cells: List[BuildCell] = []
        self.receipt: Optional[BuildReceipt] = None

    # -----------------------------------------------------------------
    # Source preparation
    # -----------------------------------------------------------------

    def _write_sources(self) -> Tuple[List[SourceFile], SourceIdentity]:
        """Write all input files to src/ and build the SourceIdentity."""
        self.src_dir.mkdir(parents=True, exist_ok=True)

        for f in self.files_input:
            dest = self.src_dir / f["filename"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(f["content"])

        # Catalog
        source_files = catalog_source_files(self.src_dir)
        c_units = [sf.path_rel for sf in source_files if sf.role == FileRole.C_UNIT]
        entry_type = "single_file" if len(c_units) <= 1 else "multi_file"
        snapshot_sha256 = compute_snapshot_hash(source_files, self.src_dir)

        identity = SourceIdentity(
            entry_type=entry_type,
            entry_c_files=c_units,
            files=source_files,
            snapshot_sha256=snapshot_sha256,
        )
        return source_files, identity

    def _snapshot_sources(self):
        """Copy source snapshot to artifacts dir for reproducibility."""
        dest = self.artifacts_dir / "src"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(self.src_dir, dest)

    # -----------------------------------------------------------------
    # Cell directory layout
    # -----------------------------------------------------------------

    def _cell_dir(self, opt: OptLevel, variant: VariantType) -> Path:
        """Return and create the artifact directory for a cell."""
        d = self.artifacts_dir / opt.value / variant.value
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _ensure_subdirs(self, cell_dir: Path):
        """Create obj/, bin/, logs/ under a cell directory."""
        (cell_dir / "obj").mkdir(exist_ok=True)
        (cell_dir / "bin").mkdir(exist_ok=True)
        (cell_dir / "logs").mkdir(exist_ok=True)

    # -----------------------------------------------------------------
    # Build phases
    # -----------------------------------------------------------------

    def _preprocess_units(
        self,
        c_files: List[str],
    ) -> PreprocessPhase:
        """
        Preprocess each .c → .i via gcc -E (optimization-independent).

        Outputs land in artifacts_dir/preprocess/{stem}.i.
        Preprocessing failure is non-fatal — logged but does not abort.
        """
        pp_dir = self.artifacts_dir / "preprocess"
        pp_dir.mkdir(exist_ok=True)
        logs_dir = pp_dir / "logs"
        logs_dir.mkdir(exist_ok=True)

        # Minimal cflags: language standard + include paths only
        pp_cflags = ["-std=c11"]
        cmd_template = "gcc -std=c11 -I src -E <source> -o preprocess/<stem>.i"

        units: List[PreprocessUnitResult] = []
        failed = 0

        for c_rel in c_files:
            src_path = self.src_dir / c_rel
            stem = Path(c_rel).stem
            out_path = pp_dir / f"{stem}.i"

            cmd = ["gcc"] + pp_cflags + [
                "-I", str(self.src_dir),
                "-E", str(src_path),
                "-o", str(out_path),
            ]

            stdout_file = logs_dir / f"preprocess.{stem}.stdout"
            stderr_file = logs_dir / f"preprocess.{stem}.stderr"

            t0 = time.monotonic()
            stdout_content = ""
            stderr_content = ""
            try:
                result = subprocess.run(
                    cmd,
                    cwd=str(self.workspace_dir),
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                )
                duration = int((time.monotonic() - t0) * 1000)
                exit_code = result.returncode
                stdout_content = result.stdout
                stderr_content = result.stderr
            except subprocess.TimeoutExpired:
                duration = int((time.monotonic() - t0) * 1000)
                exit_code = -1
                stderr_content = f"TIMEOUT after {self.timeout}s"
            except Exception as e:
                duration = int((time.monotonic() - t0) * 1000)
                exit_code = -1
                stderr_content = str(e)

            # Only write log files if they have content
            stdout_rel = None
            stderr_rel = None
            if stdout_content:
                stdout_file.write_text(stdout_content)
                stdout_rel = stdout_file.relative_to(self.artifacts_dir).as_posix()
            if stderr_content:
                stderr_file.write_text(stderr_content)
                stderr_rel = stderr_file.relative_to(self.artifacts_dir).as_posix()

            if exit_code != 0:
                failed += 1

            # Hash the .i output if it was produced
            out_sha = None
            out_rel = f"preprocess/{stem}.i"
            if exit_code == 0 and out_path.exists():
                out_sha = hash_file(out_path)

            units.append(PreprocessUnitResult(
                source_path_rel=c_rel,
                output_path_rel=out_rel,
                output_sha256=out_sha,
                exit_code=exit_code,
                stdout_path_rel=stdout_rel,
                stderr_path_rel=stderr_rel,
                duration_ms=duration,
            ))

        pp_status = PhaseStatus.SUCCESS
        if failed == len(c_files):
            pp_status = PhaseStatus.FAILED
        elif failed > 0:
            pp_status = PhaseStatus.FAILED

        return PreprocessPhase(
            command_template=cmd_template,
            units=units,
            status=pp_status,
        )

    def _compile_units(
        self,
        c_files: List[str],
        opt: OptLevel,
        variant: VariantType,
        cell_dir: Path,
    ) -> CompilePhase:
        """
        Compile each .c → .o in isolation.
        Returns a CompilePhase with per-unit results.
        """
        obj_dir = cell_dir / "obj"
        logs_dir = cell_dir / "logs"

        # Build cflags
        delta = VARIANT_DELTAS[variant.value]
        cflags_list = BASE_CFLAGS.split() + [f"-{opt.value}"] + delta.add_cflags
        cflags_str = " ".join(cflags_list)

        # Template command for receipt
        cmd_template = f"gcc {cflags_str} -I src -c <source> -o <object>"

        units: List[CompileUnitResult] = []
        failed = 0

        for c_rel in c_files:
            src_path = self.src_dir / c_rel
            obj_name = Path(c_rel).stem + ".o"
            obj_path = obj_dir / obj_name

            cmd = ["gcc"] + cflags_list + [
                "-I", str(self.src_dir),
                "-c", str(src_path),
                "-o", str(obj_path),
            ]

            stdout_file = logs_dir / f"compile.{Path(c_rel).stem}.stdout"
            stderr_file = logs_dir / f"compile.{Path(c_rel).stem}.stderr"

            t0 = time.monotonic()
            stdout_content = ""
            stderr_content = ""
            try:
                result = subprocess.run(
                    cmd,
                    cwd=str(self.workspace_dir),
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                )
                duration = int((time.monotonic() - t0) * 1000)
                exit_code = result.returncode
                stdout_content = result.stdout
                stderr_content = result.stderr
            except subprocess.TimeoutExpired:
                duration = int((time.monotonic() - t0) * 1000)
                exit_code = -1
                stderr_content = f"TIMEOUT after {self.timeout}s"
            except Exception as e:
                duration = int((time.monotonic() - t0) * 1000)
                exit_code = -1
                stderr_content = str(e)

            # Only write log files if they have content
            stdout_rel = None
            stderr_rel = None
            if stdout_content:
                stdout_file.write_text(stdout_content)
                stdout_rel = stdout_file.relative_to(self.artifacts_dir).as_posix()
            if stderr_content:
                stderr_file.write_text(stderr_content)
                stderr_rel = stderr_file.relative_to(self.artifacts_dir).as_posix()

            if exit_code != 0:
                failed += 1

            # Paths relative to artifacts_dir for receipt portability
            obj_rel = obj_path.relative_to(self.artifacts_dir).as_posix()

            units.append(CompileUnitResult(
                source_path_rel=c_rel,
                object_path_rel=obj_rel,
                exit_code=exit_code,
                stdout_path_rel=stdout_rel,
                stderr_path_rel=stderr_rel,
                duration_ms=duration,
            ))

        compile_status = PhaseStatus.SUCCESS
        if failed == len(c_files):
            compile_status = PhaseStatus.FAILED
        elif failed > 0:
            # Some units failed — still attempt link with whatever succeeded
            compile_status = PhaseStatus.FAILED

        return CompilePhase(
            command_template=cmd_template,
            units=units,
            summary=CompilePhaseSummary(
                compiled_units=len(c_files) - failed,
                failed_units=failed,
            ),
            status=compile_status,
        )

    def _link(
        self,
        obj_dir: Path,
        cell_dir: Path,
    ) -> Tuple[LinkPhase, Optional[Path]]:
        """
        Link all .o files in obj_dir into a single executable.
        Returns (LinkPhase, path_to_binary_or_None).
        """
        logs_dir = cell_dir / "logs"
        bin_dir = cell_dir / "bin"
        output_path = bin_dir / self.name

        # Gather .o files
        objects = sorted(obj_dir.glob("*.o"))
        if not objects:
            phase = LinkPhase(
                command="(no objects to link)",
                exit_code=-1,
                status=PhaseStatus.FAILED,
            )
            return phase, None

        cmd = ["gcc", "-no-pie"] + [str(o) for o in objects] + ["-o", str(output_path)]
        # Append allowed link libs from profile
        cmd += PROFILE.link_libs

        cmd_str = " ".join(cmd)

        stdout_file = logs_dir / "link.stdout"
        stderr_file = logs_dir / "link.stderr"

        t0 = time.monotonic()
        stdout_content = ""
        stderr_content = ""
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.workspace_dir),
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            duration = int((time.monotonic() - t0) * 1000)
            exit_code = result.returncode
            stdout_content = result.stdout
            stderr_content = result.stderr
        except subprocess.TimeoutExpired:
            duration = int((time.monotonic() - t0) * 1000)
            exit_code = -1
            stderr_content = f"TIMEOUT after {self.timeout}s"
        except Exception as e:
            duration = int((time.monotonic() - t0) * 1000)
            exit_code = -1
            stderr_content = str(e)

        # Only write log files if they have content
        stdout_rel = None
        stderr_rel = None
        if stdout_content:
            stdout_file.write_text(stdout_content)
            stdout_rel = stdout_file.relative_to(self.artifacts_dir).as_posix()
        if stderr_content:
            stderr_file.write_text(stderr_content)
            stderr_rel = stderr_file.relative_to(self.artifacts_dir).as_posix()

        status = PhaseStatus.SUCCESS if exit_code == 0 else PhaseStatus.FAILED
        phase = LinkPhase(
            command=cmd_str,
            exit_code=exit_code,
            stdout_path_rel=stdout_rel,
            stderr_path_rel=stderr_rel,
            duration_ms=duration,
            status=status,
        )

        bin_path = output_path if exit_code == 0 and output_path.exists() else None
        return phase, bin_path

    def _strip(
        self,
        binary_path: Path,
        cell_dir: Path,
    ) -> StripPhase:
        """
        Strip all symbols from a binary (stripped variant only).
        Modifies the binary in-place.
        """
        logs_dir = cell_dir / "logs"
        cmd = ["strip", "--strip-all", str(binary_path)]
        cmd_str = " ".join(cmd)

        stdout_file = logs_dir / "strip.stdout"
        stderr_file = logs_dir / "strip.stderr"

        t0 = time.monotonic()
        stdout_content = ""
        stderr_content = ""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            duration = int((time.monotonic() - t0) * 1000)
            exit_code = result.returncode
            stdout_content = result.stdout
            stderr_content = result.stderr
        except subprocess.TimeoutExpired:
            duration = int((time.monotonic() - t0) * 1000)
            exit_code = -1
            stderr_content = "TIMEOUT"
        except Exception as e:
            duration = int((time.monotonic() - t0) * 1000)
            exit_code = -1
            stderr_content = str(e)

        # Only write log files if they have content
        stdout_rel = None
        stderr_rel = None
        if stdout_content:
            stdout_file.write_text(stdout_content)
            stdout_rel = stdout_file.relative_to(self.artifacts_dir).as_posix()
        if stderr_content:
            stderr_file.write_text(stderr_content)
            stderr_rel = stderr_file.relative_to(self.artifacts_dir).as_posix()

        status = PhaseStatus.SUCCESS if exit_code == 0 else PhaseStatus.FAILED
        return StripPhase(
            command=cmd_str,
            exit_code=exit_code,
            stdout_path_rel=stdout_rel,
            stderr_path_rel=stderr_rel,
            duration_ms=duration,
            status=status,
        )

    # -----------------------------------------------------------------
    # Build a single cell
    # -----------------------------------------------------------------

    def _build_cell(
        self,
        opt: OptLevel,
        variant: VariantType,
        c_files: List[str],
    ) -> BuildCell:
        """Build one (optimization, variant) cell through all phases."""
        cell_dir = self._cell_dir(opt, variant)
        self._ensure_subdirs(cell_dir)
        flags: List[BuildFlag] = []

        logger.info(f"Building cell {opt.value}/{variant.value}")

        # Phase 1: Compile
        compile_phase = self._compile_units(c_files, opt, variant, cell_dir)
        if compile_phase.summary.failed_units > 0:
            flags.append(BuildFlag.COMPILE_UNIT_FAILED)

        # Phase 2: Link (only if at least one object compiled)
        link_phase = LinkPhase(status=PhaseStatus.SKIPPED)
        binary_path: Optional[Path] = None
        if compile_phase.summary.compiled_units > 0:
            link_phase, binary_path = self._link(cell_dir / "obj", cell_dir)
            if link_phase.status != PhaseStatus.SUCCESS:
                flags.append(BuildFlag.LINK_FAILED)
        else:
            link_phase = LinkPhase(
                command="(skipped — no objects)",
                exit_code=-1,
                status=PhaseStatus.SKIPPED,
            )
            flags.append(BuildFlag.LINK_FAILED)

        # Phase 3: Strip (stripped variant only)
        strip_phase: Optional[StripPhase] = None
        if variant == VariantType.STRIPPED and binary_path is not None:
            strip_phase = self._strip(binary_path, cell_dir)
            if strip_phase.status != PhaseStatus.SUCCESS:
                flags.append(BuildFlag.STRIP_FAILED)

        # Artifact metadata
        artifact: Optional[ArtifactMeta] = None
        if binary_path is not None and binary_path.exists():
            is_valid, elf_meta = validate_elf(binary_path)

            if not is_valid:
                flags.append(BuildFlag.NON_ELF_OUTPUT)
            else:
                # Debug presence check (debug variant only)
                debug_pres = None
                if variant == VariantType.DEBUG:
                    debug_pres = check_debug_sections(binary_path)
                    if not debug_pres.has_debug_sections:
                        flags.append(BuildFlag.DEBUG_EXPECTED_MISSING)

                # Strip verification (stripped variant only)
                if variant == VariantType.STRIPPED:
                    strip_check = check_debug_sections(binary_path)
                    if strip_check.has_debug_sections:
                        flags.append(BuildFlag.STRIP_EXPECTED_MISSING)

                artifact = ArtifactMeta(
                    path_rel=binary_path.relative_to(self.artifacts_dir).as_posix(),
                    sha256=hash_file(binary_path),
                    size_bytes=binary_path.stat().st_size,
                    elf=elf_meta,
                    debug_presence=debug_pres,
                )
        else:
            flags.append(BuildFlag.NO_ARTIFACT)

        # Determine cell status
        if BuildFlag.NO_ARTIFACT in flags or BuildFlag.NON_ELF_OUTPUT in flags:
            cell_status = CellStatus.FAILED
            flags.append(BuildFlag.BUILD_FAILED)
        elif any(f in flags for f in (BuildFlag.COMPILE_UNIT_FAILED, BuildFlag.LINK_FAILED)):
            cell_status = CellStatus.FAILED
            flags.append(BuildFlag.BUILD_FAILED)
        else:
            cell_status = CellStatus.SUCCESS

        return BuildCell(
            optimization=opt.value,
            variant=variant.value,
            status=cell_status,
            flags=flags,
            compile=compile_phase,
            link=link_phase,
            strip=strip_phase,
            artifact=artifact,
        )

    # -----------------------------------------------------------------
    # Execute full job
    # -----------------------------------------------------------------

    def execute(
        self,
        target_opt: Optional[OptLevel] = None,
        target_variant: Optional[VariantType] = None,
    ) -> BuildReceipt:
        """
        Execute the full build matrix or a single-target rebuild.

        Args:
            target_opt: If set, build only this optimization level.
            target_variant: If set, build only this variant.

        Returns:
            The completed BuildReceipt.
        """
        created_at = now_iso()
        logger.info(f"Starting synthetic build job: {self.name} (job_id={self.job_id})")

        # 1. Write sources and build identity
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        source_files, source_identity = self._write_sources()
        self._snapshot_sources()

        # 2. Capture toolchain
        toolchain = capture_toolchain()

        # 2.5 Preprocess phase (v2): gcc -E per TU, optimization-independent
        c_files_early = source_identity.entry_c_files
        preprocess_phase = self._preprocess_units(c_files_early)
        if preprocess_phase.status != PhaseStatus.SUCCESS:
            logger.warning(
                "Preprocess phase had failures (non-fatal), continuing build"
            )

        # 3. Determine build matrix
        opts_to_build = [target_opt] if target_opt else self.optimizations
        variants_to_build = [target_variant] if target_variant else self.variants

        # 4. Build compile policy for receipt
        compile_policy = CompilePolicy(
            base_cflags=BASE_CFLAGS,
            include_dirs=["src"],
            defines=[],
            link_libs=PROFILE.link_libs,
            variant_deltas=VARIANT_DELTAS,
        )

        # 5. Build each cell
        c_files = source_identity.entry_c_files
        cells: List[BuildCell] = []

        for opt in opts_to_build:
            for variant in variants_to_build:
                cell = self._build_cell(opt, variant, c_files)  # type: ignore[arg-type]
                cells.append(cell)

        self.cells = cells

        # 6. Assemble receipt
        finished_at = now_iso()

        # Hash LOCK_v2.md if available (fall back to LOCK.md)
        lock_hash = None
        lock_path = Path(__file__).parent / "LOCK_v2.md"
        if not lock_path.exists():
            lock_path = Path(__file__).parent / "LOCK.md"
        if lock_path.exists():
            lock_hash = hash_file(lock_path)

        receipt = BuildReceipt(
            builder=BuilderInfo(lock_text_hash=lock_hash),
            job=JobInfo(
                job_id=self.job_id,
                name=self.name,
                created_at=created_at,
                finished_at=finished_at,
            ),
            source=source_identity,
            toolchain=toolchain,
            requested=RequestedMatrix(
                optimizations=[o.value for o in self.optimizations],
                variants=[v.value for v in self.variants],
                compile_policy=compile_policy,
            ),
            preprocess=preprocess_phase,
            builds=cells,
        )

        # Derive job status
        receipt.job.status = receipt.compute_status()

        self.receipt = receipt

        # 7. Save receipt (single authoritative location)
        self._save_receipt(receipt)

        logger.info(
            f"Build job {self.job_id} finished: {receipt.job.status} "
            f"({len(cells)} cells)"
        )
        return receipt

    def _save_receipt(self, receipt: BuildReceipt):
        """Save the single authoritative build_receipt.json."""
        receipt_path = self.artifacts_dir / "build_receipt.json"
        receipt_path.write_text(receipt.model_dump_json(indent=2))
        logger.info(f"Receipt saved: {receipt_path}")

    def cleanup_workspace(self):
        """Remove temporary build workspace (not artifacts)."""
        if self.workspace_dir.exists():
            shutil.rmtree(self.workspace_dir)
            logger.info(f"Cleaned up workspace: {self.workspace_dir}")
