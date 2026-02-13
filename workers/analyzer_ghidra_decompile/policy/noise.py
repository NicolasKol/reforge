"""
Noise — versioned noise lists for function classification.

Drives the boolean flags:
  is_plt_or_stub, is_init_fini_aux, is_compiler_aux, is_library_like

All flags must be derivable from emitted evidence:
  section_hint, name, is_external_block, is_thunk, is_import.
"""

NOISE_LIST_VERSION = "1.0"

# ── Init / fini auxiliary names (§8.2) ────────────────────────────────

AUX_INIT_FINI_NAMES: frozenset = frozenset({
    "_init",
    "_fini",
    "_DT_INIT",
    "_DT_FINI",
    "_INIT_0",
    "_FINI_0",
})

# ── Compiler / linker inserted names (§8.2) ──────────────────────────

COMPILER_AUX_NAMES: frozenset = frozenset({
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
    "__cxa_finalize@@GLIBC_2.17",
})

# ── PLT section prefixes (§8.1) ──────────────────────────────────────

PLT_SECTION_PREFIXES = (".plt",)

# ── Stub name patterns ───────────────────────────────────────────────

STUB_NAME_PREFIXES = ("FUN_",)  # Ghidra default names for unnamed plt stubs


def classify_noise(
    name: str | None,
    section_hint: str | None,
    is_external_block: bool,
    is_thunk: bool,
    is_import: bool,
) -> tuple:
    """
    Classify a function into noise categories.

    Returns
    -------
    (is_plt_or_stub, is_init_fini_aux, is_compiler_aux, is_library_like)
    """
    name_clean = (name or "").strip()

    # PLT / stub detection
    is_plt_or_stub = False
    if section_hint and any(
        section_hint.startswith(pfx) for pfx in PLT_SECTION_PREFIXES
    ):
        is_plt_or_stub = True

    # Init / fini auxiliary
    is_init_fini_aux = name_clean in AUX_INIT_FINI_NAMES

    # Compiler auxiliary
    is_compiler_aux = name_clean in COMPILER_AUX_NAMES

    # Library-like (best-effort, §8.3)
    is_library_like = (
        is_external_block
        or is_import
        or is_plt_or_stub
        or is_init_fini_aux
        or is_compiler_aux
    )

    return is_plt_or_stub, is_init_fini_aux, is_compiler_aux, is_library_like
