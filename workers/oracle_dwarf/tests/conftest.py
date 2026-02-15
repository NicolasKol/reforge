"""
Shared pytest fixtures for oracle_dwarf tests.

Provides on-the-fly compilation of minimal C programs using gcc,
producing deterministic ELF binaries for testing.

Requirements:
  - gcc must be available
  - gcc must produce ELF binaries (Linux/WSL), not PE executables (native Windows)

Tests are automatically skipped on Windows. Use WSL or Docker instead.
"""
import hashlib
import platform
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

import pytest

# Minimal C source that compiles to a small binary with a few functions.
MINIMAL_C = textwrap.dedent("""\
    #include <stdio.h>

    int add(int a, int b) {
        int result = a + b;
        return result;
    }

    int multiply(int x, int y) {
        return x * y;
    }

    int main(void) {
        int sum = add(3, 4);
        int prod = multiply(sum, 2);
        printf("sum=%d prod=%d\\n", sum, prod);
        return 0;
    }
""")

# Source with a single function (simplest possible case)
SINGLE_FUNC_C = textwrap.dedent("""\
    int square(int n) {
        return n * n;
    }

    int main(void) {
        return square(5);
    }
""")


# Multi-function source designed to exercise higher optimization levels.
# __attribute__((noinline)) prevents GCC from inlining the function bodies,
# so they remain present as DW_TAG_subprogram DIEs even at -O2/-O3.
# The loop + conditional in complex_loop encourages the compiler to emit
# DW_AT_ranges (hot/cold block splitting) at -O2 and above.
MULTI_FUNC_C = textwrap.dedent("""\
    #include <stdio.h>

    __attribute__((noinline))
    int accumulate(const int *arr, int n) {
        int total = 0;
        for (int i = 0; i < n; i++) {
            total += arr[i];
        }
        return total;
    }

    __attribute__((noinline))
    int complex_loop(int n) {
        int sum = 0;
        for (int i = 0; i < n; i++) {
            if (i % 7 == 0) {
                /* cold branch — may be split at -O2+ */
                sum += i * 3;
            } else {
                sum += i;
            }
        }
        return sum;
    }

    __attribute__((noinline))
    int simple_add(int a, int b) {
        return a + b;
    }

    int main(void) {
        int data[] = {1, 2, 3, 4, 5};
        int a = accumulate(data, 5);
        int c = complex_loop(a);
        int s = simple_add(a, c);
        printf("result=%d\\n", s);
        return 0;
    }
""")


def _gcc_available() -> bool:
    """Check if gcc is in PATH."""
    return shutil.which("gcc") is not None


def _gcc_produces_elf() -> bool:
    """Test if gcc produces ELF binaries (Linux/WSL) vs PE executables (Windows).
    
    Returns False on native Windows where MSYS2/MinGW gcc produces PE format.
    """
    if not _gcc_available():
        return False
    
    # Quick platform check - native Windows cannot produce ELF
    if platform.system() == "Windows":
        # Could be WSL - test by compiling
        pass
    
    # Compile a minimal test program
    with tempfile.TemporaryDirectory() as tmpdir:
        test_c = Path(tmpdir) / "test.c"
        test_out = Path(tmpdir) / "test_out"
        test_c.write_text("int main() { return 0; }")
        
        try:
            subprocess.run(
                ["gcc", str(test_c), "-o", str(test_out)],
                check=True,
                capture_output=True,
                timeout=10
            )
            
            # Check both with and without .exe extension
            if test_out.exists():
                binary = test_out
            elif test_out.with_suffix(".exe").exists():
                binary = test_out.with_suffix(".exe")
            else:
                return False
            
            # Check magic bytes: ELF = 0x7F 'E' 'L' 'F', PE = 'M' 'Z'
            magic = binary.read_bytes()[:4]
            return magic[:4] == b'\x7fELF'
            
        except Exception:
            return False


def _compile(source: str, output: Path, opt: str = "O0", strip: bool = False) -> Path:
    """Compile C source to an ELF binary with gcc.
    
    Returns the actual path to the compiled binary.
    """
    src_file = output.with_suffix(".c")
    src_file.write_text(source)
    cmd = [
        "gcc",
        f"-{opt}",
        "-g", "-g3",
        "-std=c11",
        "-fno-omit-frame-pointer",
        str(src_file),
        "-o", str(output),
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=30)
    
    # Handle potential .exe extension on Windows
    if not output.exists() and output.with_suffix(".exe").exists():
        output = output.with_suffix(".exe")
    
    if strip:
        subprocess.run(["strip", "--strip-all", str(output)], check=True, timeout=10)
    
    return output


@pytest.fixture(scope="session")
def gcc_ok():
    """Skip tests if gcc is not available or doesn't produce ELF binaries.
    
    Native Windows with MSYS2/MinGW is not supported because gcc produces
    PE executables, not ELF binaries. Use WSL or Docker instead.
    """
    if not _gcc_available():
        pytest.skip("gcc not available - install gcc to run these tests")
    
    if not _gcc_produces_elf():
        pytest.skip(
            "gcc does not produce ELF binaries (likely native Windows). "
            "oracle_dwarf requires ELF binaries with DWARF debug info. "
            "Run tests in WSL: 'wsl' then 'cd /mnt/c/...' and run pytest, "
            "or use Docker: 'docker compose run --rm api pytest ...'"
        )


@pytest.fixture(scope="session")
def fixtures_dir(tmp_path_factory, gcc_ok) -> Path:
    """Session-scoped temp directory with compiled test binaries."""
    d = tmp_path_factory.mktemp("oracle_fixtures")
    return d


@pytest.fixture(scope="session")
def debug_binary_O0(fixtures_dir) -> Path:
    """Minimal C program compiled at -O0 with full debug info."""
    return _compile(MINIMAL_C, fixtures_dir / "minimal_O0", opt="O0")


@pytest.fixture(scope="session")
def debug_binary_O1(fixtures_dir) -> Path:
    """Minimal C program compiled at -O1 with full debug info."""
    return _compile(MINIMAL_C, fixtures_dir / "minimal_O1", opt="O1")


@pytest.fixture(scope="session")
def stripped_binary(fixtures_dir) -> Path:
    """Minimal C program compiled and stripped (no debug info)."""
    return _compile(MINIMAL_C, fixtures_dir / "minimal_stripped", opt="O0", strip=True)


@pytest.fixture(scope="session")
def single_func_binary(fixtures_dir) -> Path:
    """Two-function program compiled at -O0 with debug info."""
    return _compile(SINGLE_FUNC_C, fixtures_dir / "single_func", opt="O0")


@pytest.fixture
def not_elf(tmp_path) -> Path:
    """A file that is not an ELF binary."""
    p = tmp_path / "not_an_elf"
    p.write_bytes(b"This is not an ELF file.\x00\x00\x00")
    return p


# ── O2 / O3 fixtures (MULTI_FUNC_C) ─────────────────────────────────

@pytest.fixture(scope="session")
def multi_func_binary_O0(fixtures_dir) -> Path:
    """Multi-function C program compiled at -O0 (baseline for O2/O3 comparison)."""
    return _compile(MULTI_FUNC_C, fixtures_dir / "multi_O0", opt="O0")


@pytest.fixture(scope="session")
def multi_func_binary_O2(fixtures_dir) -> Path:
    """Multi-function C program compiled at -O2 with debug info."""
    return _compile(MULTI_FUNC_C, fixtures_dir / "multi_O2", opt="O2")


@pytest.fixture(scope="session")
def multi_func_binary_O3(fixtures_dir) -> Path:
    """Multi-function C program compiled at -O3 with debug info."""
    return _compile(MULTI_FUNC_C, fixtures_dir / "multi_O3", opt="O3")
