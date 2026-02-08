"""
Core build logic - extracted and simplified from Assemblage.

Handles:
- Git clone
- Build system detection (CMake, Make, Autoconf)
- Compiler flag injection (GCC/Clang with optimization levels)
- Binary discovery (ELF executables)
- Manifest generation (provenance tracking)
"""
import os
import re
import json
import hashlib
import subprocess
import tempfile
from pathlib import Path
from typing import Tuple, Set, Dict, List, Optional
from enum import Enum
from dataclasses import dataclass, asdict
from elftools.elf.elffile import ELFFile
from elftools.common.exceptions import ELFError


class BuildStatus(str, Enum):
    """Build job status"""
    QUEUED = "QUEUED"
    CLONING = "CLONING"
    BUILDING = "BUILDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


class OptLevel(str, Enum):
    """GCC/Clang optimization levels"""
    O0 = "O0"
    O1 = "O1"
    O2 = "O2"
    O3 = "O3"
    
    def to_flag(self) -> str:
        """Convert to compiler flag"""
        return f"-{self.value}"


class Compiler(str, Enum):
    """Supported compilers"""
    GCC = "gcc"
    CLANG = "clang"


@dataclass
class BuildConfig:
    """Build configuration for a single optimization level"""
    compiler: Compiler
    optimization: OptLevel
    debug_symbols: bool = True
    preserve_frame_pointer: bool = True
    save_assembly: bool = False
    
    def get_cflags(self) -> str:
        """Generate CFLAGS string"""
        flags = [self.optimization.to_flag()]
        
        if self.debug_symbols:
            flags.append("-g")
        
        if self.preserve_frame_pointer:
            flags.extend(["-fno-omit-frame-pointer", "-mno-omit-leaf-frame-pointer"])
        
        # Prevent -Werror from failing builds
        flags.append("-Wno-error")
        
        if self.save_assembly:
            flags.append("-save-temps=obj")
        
        return " ".join(flags)


@dataclass
class BuildArtifact:
    """Metadata for a single binary artifact"""
    filename: str
    filepath: str
    sha256: str
    size_bytes: int
    has_debug_info: bool
    debug_sections: List[str]
    is_executable: bool


@dataclass
class BuildResult:
    """Result of a complete build"""
    status: BuildStatus
    commit_hash: str
    artifacts: List[BuildArtifact]
    build_log: str
    error_message: Optional[str] = None


class BuildExecutor:
    """Handles the actual build process for a single optimization level"""
    
    def __init__(self, workspace_dir: str, config: BuildConfig, timeout: int = 600):
        self.workspace_dir = Path(workspace_dir)
        self.config = config
        self.timeout = timeout
        self.num_jobs = os.cpu_count() or 4
    
    def _run_command(self, cmd: str, cwd: Optional[Path] = None, timeout: Optional[int] = None) -> Tuple[str, str, int]:
        """Execute shell command and return (stdout, stderr, exit_code)"""
        if cwd is None:
            cwd = self.workspace_dir
        
        if timeout is None:
            timeout = self.timeout
        
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=str(cwd),
                capture_output=True,
                timeout=timeout,
                text=True
            )
            return result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired as e:
            return "", f"Command timed out after {timeout}s", -1
        except Exception as e:
            return "", str(e), -1
    
    def clone_repo(self, url: str, target_dir: Path) -> Tuple[bool, str]:
        """Clone git repository with submodules"""
        if target_dir.exists():
            # Pull if already exists
            cmd = "git pull --recurse-submodules"
            stdout, stderr, code = self._run_command(cmd, cwd=target_dir)
        else:
            # Fresh clone
            cmd = f"git clone --recursive {url} {target_dir}"
            stdout, stderr, code = self._run_command(cmd, cwd=self.workspace_dir.parent)
        
        if code != 0:
            return False, f"Clone failed: {stderr}"
        
        return True, "Clone successful"
    
    def get_commit_hash(self, repo_dir: Path) -> str:
        """Get current commit hash (short form)"""
        cmd = "git rev-parse --short=12 HEAD"
        stdout, stderr, code = self._run_command(cmd, cwd=repo_dir)
        
        if code == 0:
            return stdout.strip()
        return "unknown"
    
    def detect_build_system(self, repo_dir: Path) -> Optional[str]:
        """Detect build system (cmake, make, configure, bootstrap)"""
        files = list(repo_dir.rglob("*"))
        filenames = {f.name.lower() for f in files if f.is_file()}
        
        # Priority order
        if "bootstrap" in filenames or "bootstrap.sh" in filenames:
            return "bootstrap"
        
        if "configure" in filenames or "configure.ac" in filenames:
            return "configure"
        
        if "cmakelists.txt" in filenames:
            return "cmake"
        
        if "makefile" in filenames or any(f.name.lower() == "makefile.am" for f in files):
            return "make"
        
        return None
    
    def build(self, repo_dir: Path) -> Tuple[bool, str, str]:
        """Execute build process - returns (success, stdout, stderr)"""
        build_system = self.detect_build_system(repo_dir)
        
        if not build_system:
            return False, "", "No supported build system detected"
        
        # Export compiler flags
        cflags = self.config.get_cflags()
        export_flags = f'export CC={self.config.compiler.value} CXX={self.config.compiler.value}++ CFLAGS="{cflags}" CXXFLAGS="{cflags}"'
        
        # Build command based on detected system
        if build_system == "bootstrap":
            cmd = f'{export_flags} && ./bootstrap && bash ./configure && timeout {self.timeout} make -j{self.num_jobs}'
        
        elif build_system == "configure":
            cmd = f'{export_flags} && bash ./configure && timeout {self.timeout} make -j{self.num_jobs}'
        
        elif build_system == "cmake":
            build_type = "RelWithDebInfo" if self.config.debug_symbols else "Release"
            cmake_flags = [
                f"-DCMAKE_BUILD_TYPE={build_type}",
                "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
                "-DBUILD_TESTING=OFF",
                f'-DCMAKE_C_COMPILER={self.config.compiler.value}',
                f'-DCMAKE_CXX_COMPILER={self.config.compiler.value}++',
                f'-DCMAKE_C_FLAGS="{cflags}"',
                f'-DCMAKE_CXX_FLAGS="{cflags}"',
            ]
            cmake_config = " ".join(cmake_flags)
            cmd = f'cmake -Bbuild -S . {cmake_config} && cd build && timeout {self.timeout} make -j{self.num_jobs}'
        
        elif build_system == "make":
            cmd = f'{export_flags} && timeout {self.timeout} make -j{self.num_jobs}'
        
        else:
            return False, "", f"Unsupported build system: {build_system}"
        
        stdout, stderr, code = self._run_command(cmd, cwd=repo_dir)
        
        success = code == 0
        return success, stdout, stderr
    
    def find_binaries(self, repo_dir: Path) -> Set[Path]:
        """Find all ELF executables and shared libraries"""
        binaries = set()
        
        for root, dirs, files in os.walk(repo_dir):
            # Skip .git directories
            if '.git' in dirs:
                dirs.remove('.git')
            
            for filename in files:
                filepath = Path(root) / filename
                
                # Check for assembly files if requested
                if self.config.save_assembly and filepath.suffix.lower() in ['.s', '.S', '.ii', '.bc']:
                    binaries.add(filepath)
                    continue
                
                # Check if it's an ELF file
                try:
                    with open(filepath, 'rb') as f:
                        elf = ELFFile(f)
                        # ET_EXEC (executable) or ET_DYN (shared library)
                        if elf.header['e_type'] in ['ET_EXEC', 'ET_DYN']:
                            binaries.add(filepath)
                except (ELFError, PermissionError, IsADirectoryError):
                    continue
        
        return binaries
    
    def filter_binaries(self, binaries: Set[Path]) -> Set[Path]:
        """Filter out build artifacts and keep only final binaries"""
        useless_patterns = [
            'CMakeCCompilerId', 'CMakeDetermineCompilerABI',
            'CompilerIdC', 'CompilerIdCXX', 'feature_tests',
        ]
        
        filtered = set()
        seen_real_paths = set()
        
        for binary_path in binaries:
            # Skip symlinks
            if binary_path.is_symlink():
                continue
            
            # Deduplicate by real path
            real_path = binary_path.resolve()
            if real_path in seen_real_paths:
                continue
            seen_real_paths.add(real_path)
            
            # Skip CMake probes
            if any(pattern in str(binary_path) for pattern in useless_patterns):
                continue
            
            # Skip object files
            if binary_path.suffix == '.o':
                continue
            
            filtered.add(binary_path)
        
        return filtered
    
    def check_debug_info(self, binary_path: Path) -> Tuple[bool, List[str]]:
        """Check for debug sections using readelf"""
        cmd = f"readelf -S {binary_path}"
        stdout, stderr, code = self._run_command(cmd)
        
        if code != 0:
            return False, []
        
        # Parse section names
        debug_sections = []
        debug_section_pattern = re.compile(r'\[\s*\d+\]\s+(\.\S+)')
        
        for match in debug_section_pattern.finditer(stdout):
            section_name = match.group(1)
            if section_name.startswith('.debug_'):
                debug_sections.append(section_name)
        
        has_debug = len(debug_sections) > 0
        return has_debug, debug_sections
    
    def compute_sha256(self, filepath: Path) -> str:
        """Compute SHA256 hash of file"""
        sha256 = hashlib.sha256()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def create_artifact_metadata(self, binary_path: Path) -> BuildArtifact:
        """Create metadata for a binary artifact"""
        has_debug, debug_sections = self.check_debug_info(binary_path)
        sha256 = self.compute_sha256(binary_path)
        size = binary_path.stat().st_size
        
        # Check if it's executable (not just a shared library)
        is_executable = False
        try:
            with open(binary_path, 'rb') as f:
                elf = ELFFile(f)
                is_executable = elf.header['e_type'] == 'ET_EXEC'
        except:
            pass
        
        return BuildArtifact(
            filename=binary_path.name,
            filepath=str(binary_path),
            sha256=sha256,
            size_bytes=size,
            has_debug_info=has_debug,
            debug_sections=debug_sections,
            is_executable=is_executable
        )


class BuildJob:
    """Complete build job for a repository at multiple optimization levels"""
    
    def __init__(
        self,
        job_id: str,
        repo_url: str,
        commit_ref: str = "HEAD",
        compiler: Compiler = Compiler.GCC,
        optimizations: Optional[List[OptLevel]] = None,
        workspace_root: str = "/tmp/reforge_builds"
    ):
        self.job_id = job_id
        self.repo_url = repo_url
        self.commit_ref = commit_ref
        self.compiler = compiler
        self.optimizations = optimizations or [OptLevel.O0, OptLevel.O2, OptLevel.O3]
        self.workspace_root = Path(workspace_root)
        
        # Parse repo name from URL
        self.repo_name = self._parse_repo_name(repo_url)
        self.job_workspace = self.workspace_root / job_id
    
    def _parse_repo_name(self, url: str) -> str:
        """Extract repo name from git URL"""
        # https://github.com/user/repo.git -> repo
        # https://github.com/user/repo -> repo
        match = re.search(r'/([^/]+?)(\.git)?$', url)
        if match:
            return match.group(1)
        return "unknown_repo"
    
    def execute(self) -> Dict[str, BuildResult]:
        """Execute build for all optimization levels"""
        results = {}
        
        # Create workspace
        self.job_workspace.mkdir(parents=True, exist_ok=True)
        repo_dir = self.job_workspace / self.repo_name
        
        # Clone repo once
        config = BuildConfig(compiler=self.compiler, optimization=self.optimizations[0])
        executor = BuildExecutor(str(self.job_workspace), config)
        
        clone_success, clone_msg = executor.clone_repo(self.repo_url, repo_dir)
        if not clone_success:
            # Return failure for all optimizations
            for opt in self.optimizations:
                results[opt.value] = BuildResult(
                    status=BuildStatus.FAILED,
                    commit_hash="unknown",
                    artifacts=[],
                    build_log="",
                    error_message=f"Clone failed: {clone_msg}"
                )
            return results
        
        # Get commit hash
        commit_hash = executor.get_commit_hash(repo_dir)
        
        # Build for each optimization level
        for opt_level in self.optimizations:
            config = BuildConfig(
                compiler=self.compiler,
                optimization=opt_level,
                debug_symbols=True,
                preserve_frame_pointer=True,
                save_assembly=False
            )
            
            executor = BuildExecutor(str(self.job_workspace), config)
            
            # Execute build
            build_success, stdout, stderr = executor.build(repo_dir)
            
            if not build_success:
                results[opt_level.value] = BuildResult(
                    status=BuildStatus.FAILED,
                    commit_hash=commit_hash,
                    artifacts=[],
                    build_log=f"STDOUT:\n{stdout}\n\nSTDERR:\n{stderr}",
                    error_message=f"Build failed with exit code != 0"
                )
                continue
            
            # Find and filter binaries
            all_binaries = executor.find_binaries(repo_dir)
            filtered_binaries = executor.filter_binaries(all_binaries)
            
            if not filtered_binaries:
                results[opt_level.value] = BuildResult(
                    status=BuildStatus.FAILED,
                    commit_hash=commit_hash,
                    artifacts=[],
                    build_log=f"STDOUT:\n{stdout}\n\nSTDERR:\n{stderr}",
                    error_message="No binaries found after build"
                )
                continue
            
            # Create artifact metadata
            artifacts = []
            for binary_path in filtered_binaries:
                try:
                    artifact = executor.create_artifact_metadata(binary_path)
                    artifacts.append(artifact)
                except Exception as e:
                    # Skip this artifact if metadata creation fails
                    continue
            
            results[opt_level.value] = BuildResult(
                status=BuildStatus.SUCCESS,
                commit_hash=commit_hash,
                artifacts=artifacts,
                build_log=f"STDOUT:\n{stdout}\n\nSTDERR:\n{stderr}",
                error_message=None
            )
        
        return results
    
    def generate_manifest(self, results: Dict[str, BuildResult]) -> Dict:
        """Generate manifest JSON for provenance tracking"""
        manifest = {
            "job_id": self.job_id,
            "repo_url": self.repo_url,
            "commit_ref": self.commit_ref,
            "compiler": self.compiler.value,
            "builds": {}
        }
        
        for opt_level, result in results.items():
            manifest["builds"][opt_level] = {
                "status": result.status.value,
                "commit_hash": result.commit_hash,
                "artifact_count": len(result.artifacts),
                "artifacts": [asdict(a) for a in result.artifacts],
                "error_message": result.error_message
            }
        
        return manifest


# TODO: Add methods for saving artifacts to local filesystem
# TODO: Add methods for inserting build results into PostgreSQL
