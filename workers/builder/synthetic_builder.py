"""
Synthetic Data Builder
Compiles single C/C++ source files with controlled parameters for testing.
"""
import os
import json
import shutil
import subprocess
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class Compiler(str, Enum):
    """Supported compilers"""
    GCC = "gcc"
    CLANG = "clang"


class OptLevel(str, Enum):
    """Optimization levels"""
    O0 = "O0"
    O1 = "O1"
    O2 = "O2"
    O3 = "O3"
    Os = "Os"


class BinaryVariant(str, Enum):
    """Binary variants for testing"""
    DEBUG = "debug"          # Full debug symbols, not stripped
    RELEASE = "release"      # Optimized, not stripped
    STRIPPED = "stripped"    # Optimized and stripped (what LLM will analyze)


@dataclass
class SyntheticArtifact:
    """Result of compiling a synthetic source file"""
    name: str
    compiler: Compiler
    optimization: OptLevel
    variant: BinaryVariant
    binary_path: Path
    source_hash: str
    file_size: int
    has_debug_info: bool
    is_stripped: bool
    compile_flags: str
    compile_success: bool
    compile_output: str
    

class SyntheticBuildJob:
    """
    Builds a single C/C++ source file at multiple optimization levels.
    Creates variants: debug (ground truth), release, and stripped (for analysis).
    """
    
    def __init__(
        self,
        name: str,
        source_code: str,
        test_category: str,
        language: str = "c",
        compilers: Optional[List[Compiler]] = None,
        optimizations: Optional[List[OptLevel]] = None,
        workspace_dir: Optional[Path] = None,
        artifacts_dir: Optional[Path] = None,
        timeout: int = 30
    ):
        """
        Args:
            name: Unique identifier for this synthetic test case
            source_code: The C/C++ source code content
            test_category: Category (arrays, loops, strings, functions, etc.)
            language: 'c' or 'cpp'
            compilers: List of compilers to use (default: [gcc])
            optimizations: Optimization levels to build (default: [O0, O2, O3])
            workspace_dir: Temporary build directory
            artifacts_dir: Where to store final artifacts
            timeout: Compilation timeout in seconds
        """
        self.name = name
        self.source_code = source_code
        self.test_category = test_category
        self.language = language
        self.compilers = compilers or [Compiler.GCC]
        self.optimizations = optimizations or [OptLevel.O0, OptLevel.O2, OptLevel.O3]
        self.timeout = timeout
        
        # Setup directories
        self.workspace_dir = workspace_dir or Path("/tmp/synthetic_builds") / name
        self.artifacts_dir = artifacts_dir or Path("/files/artifacts/synthetic") / name
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        
        # Source file
        ext = ".c" if language == "c" else ".cpp"
        self.source_file = self.workspace_dir / f"{name}{ext}"
        
        # Results
        self.artifacts: List[SyntheticArtifact] = []
        self.errors: List[str] = []
    
    def _write_source(self):
        """Write source code to file"""
        logger.info(f"Writing source to {self.source_file}")
        self.source_file.write_text(self.source_code)
        
        # Calculate source hash for tracking
        import hashlib
        return hashlib.sha256(self.source_code.encode()).hexdigest()
    
    def _get_base_flags(self, compiler: Compiler) -> List[str]:
        """Get base compilation flags"""
        flags = []
        
        # Language standard
        if self.language == "c":
            flags.extend(["-std=c11"])
        else:
            flags.extend(["-std=c++17"])
        
        # Common flags
        flags.extend([
            "-fno-omit-frame-pointer",
            "-mno-omit-leaf-frame-pointer"
        ])
        
        return flags
    
    def _compile_variant(
        self,
        compiler: Compiler,
        optimization: OptLevel,
        variant: BinaryVariant,
        source_hash: str
    ) -> Optional[SyntheticArtifact]:
        """
        Compile a single variant (debug/release/stripped).
        
        Args:
            compiler: gcc or clang
            optimization: O0/O1/O2/O3
            variant: debug/release/stripped
            source_hash: SHA256 of source code
            
        Returns:
            SyntheticArtifact if successful, None if compilation failed
        """
        # Build output name
        output_name = f"{self.name}_{compiler.value}_{optimization.value}_{variant.value}"
        output_path = self.workspace_dir / output_name
        
        # Build flags
        flags = self._get_base_flags(compiler)
        flags.append(f"-{optimization.value}")
        
        # Variant-specific flags
        if variant == BinaryVariant.DEBUG:
            flags.extend(["-g", "-g3"])  # Maximum debug info
            has_debug = True
            is_stripped = False
        elif variant == BinaryVariant.RELEASE:
            flags.append("-g")  # Standard debug info
            has_debug = True
            is_stripped = False
        else:  # STRIPPED
            flags.append("-g")  # Compile with debug, will strip after
            has_debug = False
            is_stripped = True
        
        # Build command
        cmd = [
            compiler.value,
            *flags,
            str(self.source_file),
            "-o", str(output_path)
        ]
        
        logger.info(f"Compiling {variant.value} variant: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.workspace_dir),
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            compile_output = result.stdout + result.stderr
            
            if result.returncode != 0:
                logger.error(f"Compilation failed for {output_name}: {compile_output}")
                self.errors.append(f"{output_name}: {compile_output}")
                return None
            
            # Strip if needed
            if variant == BinaryVariant.STRIPPED:
                strip_cmd = ["strip", "--strip-all", str(output_path)]
                strip_result = subprocess.run(
                    strip_cmd,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if strip_result.returncode != 0:
                    logger.error(f"Stripping failed for {output_name}")
                    self.errors.append(f"Strip failed: {output_name}")
                    return None
            
            # Verify binary exists
            if not output_path.exists():
                logger.error(f"Binary not created: {output_path}")
                return None
            
            # Copy to artifacts directory
            artifact_subdir = self.artifacts_dir / f"{compiler.value}_{optimization.value}"
            artifact_subdir.mkdir(parents=True, exist_ok=True)
            final_path = artifact_subdir / f"{variant.value}"
            shutil.copy2(output_path, final_path)
            
            # Create artifact record
            artifact = SyntheticArtifact(
                name=self.name,
                compiler=compiler,
                optimization=optimization,
                variant=variant,
                binary_path=final_path,
                source_hash=source_hash,
                file_size=final_path.stat().st_size,
                has_debug_info=has_debug,
                is_stripped=is_stripped,
                compile_flags=" ".join(flags),
                compile_success=True,
                compile_output=compile_output
            )
            
            logger.info(f"Successfully built {output_name} -> {final_path}")
            return artifact
            
        except subprocess.TimeoutExpired:
            logger.error(f"Compilation timeout for {output_name}")
            self.errors.append(f"Timeout: {output_name}")
            return None
        except Exception as e:
            logger.error(f"Compilation error for {output_name}: {e}")
            self.errors.append(f"Error: {output_name}: {str(e)}")
            return None
    
    def execute(self) -> Tuple[List[SyntheticArtifact], List[str]]:
        """
        Execute the build job across all compilers and optimization levels.
        
        Returns:
            Tuple of (artifacts, errors)
        """
        logger.info(f"Starting synthetic build: {self.name}")
        
        # Write source file
        source_hash = self._write_source()
        
        # Build all combinations
        for compiler in self.compilers:
            for optimization in self.optimizations:
                # Build all variants
                for variant in BinaryVariant:
                    artifact = self._compile_variant(
                        compiler=compiler,
                        optimization=optimization,
                        variant=variant,
                        source_hash=source_hash
                    )
                    if artifact:
                        self.artifacts.append(artifact)
        
        logger.info(f"Build complete: {len(self.artifacts)} artifacts, {len(self.errors)} errors")
        return self.artifacts, self.errors
    
    def generate_manifest(self) -> Dict:
        """Generate JSON manifest describing this build"""
        return {
            "name": self.name,
            "test_category": self.test_category,
            "language": self.language,
            "source_code": self.source_code,
            "artifacts": [
                {
                    "compiler": a.compiler.value,
                    "optimization": a.optimization.value,
                    "variant": a.variant.value,
                    "binary_path": str(a.binary_path),
                    "source_hash": a.source_hash,
                    "file_size": a.file_size,
                    "has_debug_info": a.has_debug_info,
                    "is_stripped": a.is_stripped,
                    "compile_flags": a.compile_flags
                }
                for a in self.artifacts
            ],
            "errors": self.errors,
            "success_count": len(self.artifacts),
            "error_count": len(self.errors)
        }
    
    def save_manifest(self):
        """Save manifest to artifacts directory"""
        manifest = self.generate_manifest()
        manifest_path = self.artifacts_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))
        logger.info(f"Manifest saved to {manifest_path}")
        return manifest_path
    
    def cleanup_workspace(self):
        """Remove temporary build directory"""
        if self.workspace_dir.exists():
            shutil.rmtree(self.workspace_dir)
            logger.info(f"Cleaned up workspace: {self.workspace_dir}")


def verify_debug_symbols(binary_path: Path) -> bool:
    """
    Verify that a binary contains debug symbols.
    
    Args:
        binary_path: Path to ELF binary
        
    Returns:
        True if debug sections found
    """
    try:
        result = subprocess.run(
            ["readelf", "-S", str(binary_path)],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode != 0:
            return False
        
        # Check for debug sections
        debug_sections = [".debug_info", ".debug_line", ".debug_str"]
        output = result.stdout
        
        return any(section in output for section in debug_sections)
        
    except Exception as e:
        logger.error(f"Failed to verify debug symbols: {e}")
        return False
