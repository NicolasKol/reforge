"""
Noise — versioned noise lists for function classification.

Drives the boolean flags:
  is_plt_or_stub, is_init_fini_aux, is_compiler_aux, is_library_like

All flags must be derivable from emitted evidence:
  section_hint, name, is_external_block, is_thunk, is_import.

Canonical name sets live in ``data.noise_lists`` (single source of truth).
"""

from data.noise_lists import (
    AUX_INIT_FINI_NAMES,
    COMPILER_AUX_NAMES,
    NOISE_LIST_VERSION,
    PLT_SECTION_PREFIXES,
    STUB_NAME_PREFIXES,
    normalize_glibc_name,
)


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
    name_norm = normalize_glibc_name(name_clean)

    # PLT / stub detection
    is_plt_or_stub = False
    if section_hint and any(
        section_hint.startswith(pfx) for pfx in PLT_SECTION_PREFIXES
    ):
        is_plt_or_stub = True
    if any(name_clean.startswith(pfx) for pfx in STUB_NAME_PREFIXES):
        is_plt_or_stub = True

    # Init / fini auxiliary
    is_init_fini_aux = name_norm in AUX_INIT_FINI_NAMES

    # Compiler auxiliary
    is_compiler_aux = name_norm in COMPILER_AUX_NAMES

    # Library-like (best-effort, §8.3)
    is_library_like = (
        is_external_block
        or is_import
        or is_plt_or_stub
        or is_init_fini_aux
        or is_compiler_aux
    )

    return is_plt_or_stub, is_init_fini_aux, is_compiler_aux, is_library_like
