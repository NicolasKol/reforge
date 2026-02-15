"""
Canonical noise-name lists — single source of truth for function classification.

Both ``analyzer_ghidra_decompile`` and ``join_oracles_to_ghidra_decompile``
import from here so the two packages can never diverge.

§8.1–§8.3 in the pipeline spec.
"""
from __future__ import annotations

NOISE_LIST_VERSION = "1.1"

# ── Init / fini auxiliary names (§8.2) ────────────────────────────────

AUX_INIT_FINI_NAMES: frozenset[str] = frozenset({
    "_init",
    "_fini",
    "_DT_INIT",
    "_DT_FINI",
    "_INIT_0",
    "_FINI_0",
})

# ── Compiler / linker inserted names (§8.2) ──────────────────────────

COMPILER_AUX_NAMES: frozenset[str] = frozenset({
    "frame_dummy",
    "register_tm_clones",
    "deregister_tm_clones",
    "__do_global_dtors_aux",
    "__libc_csu_init",
    "__libc_csu_fini",
    "__cxa_finalize",
    "__cxa_atexit",
    "__stack_chk_fail",
    "__gmon_start__",
    "_start",
    "__libc_start_main",
    "_dl_relocate_static_pie",
    "__x86.get_pc_thunk.bx",
    "__x86.get_pc_thunk.ax",
    "_ITM_registerTMCloneTable",
    "_ITM_deregisterTMCloneTable",
    # Note: version-suffixed variants (e.g. __cxa_finalize@@GLIBC_2.17)
    # are handled by normalize_glibc_name() before set lookup.
})

ALL_AUX_NAMES: frozenset[str] = AUX_INIT_FINI_NAMES | COMPILER_AUX_NAMES

# ── PLT section prefixes (§8.1) ──────────────────────────────────────

PLT_SECTION_PREFIXES: tuple[str, ...] = (".plt",)

# ── Stub name patterns ───────────────────────────────────────────────

STUB_NAME_PREFIXES: tuple[str, ...] = ("FUN_",)


# ── GLIBC version-suffix normalization ────────────────────────────────

def normalize_glibc_name(name: str) -> str:
    """Strip ``@@GLIBC_*`` version suffixes for set membership tests.

    ``__cxa_finalize@@GLIBC_2.17`` → ``__cxa_finalize``
    """
    idx = name.find("@@GLIBC_")
    if idx >= 0:
        return name[:idx]
    return name
