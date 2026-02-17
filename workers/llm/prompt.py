"""
Prompt template loader and renderer for LLM experiments.

Templates live in ``workers/llm/prompt_templates/<template_id>.txt``
and use ``{{ placeholder }}``-style substitution.

Supported placeholders:

- ``{{ c_raw }}``       — Ghidra decompiled C code (always required)
- ``{{ calls }}``       — Call relationships (L1+)
- ``{{ cfg_summary }}`` — Control-flow summary (L2)
- ``{{ variables }}``   — Variable table (L2)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

_TEMPLATES_DIR = Path(__file__).parent / "prompt_templates"


def load_template(template_id: str) -> str:
    """Load a prompt template by ID.

    Parameters
    ----------
    template_id : str
        Template filename without extension, e.g. ``"function_naming_v2_L0"``.

    Returns
    -------
    str
        Raw template text with ``{{ … }}`` placeholders.

    Raises
    ------
    FileNotFoundError
        If the template file does not exist.
    """
    path = _TEMPLATES_DIR / f"{template_id}.txt"
    if not path.exists():
        raise FileNotFoundError(
            f"Prompt template not found: {path}  "
            f"(available: {[p.stem for p in _TEMPLATES_DIR.glob('*.txt')]})"
        )
    return path.read_text(encoding="utf-8")


def render_prompt(
    template: str,
    c_raw: str,
    *,
    calls: Optional[str] = None,
    cfg_summary: Optional[str] = None,
    variables: Optional[str] = None,
) -> str:
    """Substitute placeholders in *template* with context data.

    Parameters
    ----------
    template : str
        Template text (from :func:`load_template`).
    c_raw : str
        Decompiled C source from Ghidra (required).
    calls : str | None
        Formatted call-relationship text for ``{{ calls }}``.
    cfg_summary : str | None
        Formatted CFG summary for ``{{ cfg_summary }}``.
    variables : str | None
        Formatted variable table for ``{{ variables }}``.

    Returns
    -------
    str
        Fully rendered prompt ready for the LLM.
    """
    result = template.replace("{{ c_raw }}", c_raw)
    if calls is not None:
        result = result.replace("{{ calls }}", calls)
    else:
        result = result.replace("{{ calls }}", "(no call data available)")
    if cfg_summary is not None:
        result = result.replace("{{ cfg_summary }}", cfg_summary)
    else:
        result = result.replace("{{ cfg_summary }}", "(no CFG data available)")
    if variables is not None:
        result = result.replace("{{ variables }}", variables)
    else:
        result = result.replace("{{ variables }}", "(no variable data available)")
    return result
