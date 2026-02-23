"""
LLM Data Router — sanitized function records for LLM consumption.

This endpoint guarantees that **only** Ghidra-derived artefacts are served.
Ground-truth labels (DWARF names, alignment provenance, quality tiers) are
stripped by construction — the response model ``LLMInputRow`` enforces the
whitelist at Pydantic serialisation time.

Callers cannot request additional fields; there is no ``include=…`` parameter.

Context levels control how much *structural* Ghidra data is attached:

- **L0** — code only (``c_raw``)
- **L1** — code + call edges
- **L2** — code + call edges + CFG summary + variable table
"""
from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.config import settings
from data.llm_contract import (
    LLMInputRow,
    MetadataMode,
    audit_leakage_counts,
    sanitize_batch,
    sanitize_for_llm,
)
from data.loader import (
    format_calls_for_prompt,
    format_cfg_for_prompt,
    format_variables_for_prompt,
    load_functions_with_decompiled,
    load_ghidra_calls,
    load_ghidra_cfg,
    load_ghidra_variables,
)
from data.paths import discover_test_cases

log = logging.getLogger(__name__)

router = APIRouter()

SYNTHETIC_ROOT = Path(settings.ARTIFACTS_PATH) / "synthetic"

# Current architecture — constant across the dataset.
# Derived from build receipt ELF metadata: all binaries are x86-64.
_DATASET_ARCH = "x86-64"


# ─── Context level enum ──────────────────────────────────────────────────────

class ContextLevel(str, Enum):
    """Controls how much structural Ghidra data is attached to each row."""
    L0 = "L0"  # Code only
    L1 = "L1"  # Code + calls
    L2 = "L2"  # Code + calls + CFG + variables


# ─── Extended response model ─────────────────────────────────────────────────

class LLMInputRowWithContext(BaseModel):
    """LLMInputRow plus optional structural context strings.

    These extra fields contain formatted text ready for prompt injection.
    They are Ghidra-only artefacts — no ground-truth leakage.
    """
    # Embed the base sanitized row
    dwarf_function_id: str
    ghidra_func_id: Optional[str] = None
    ghidra_entry_va: Optional[int] = None
    c_raw: Optional[str] = None
    ghidra_name: Optional[str] = None
    decompile_status: Optional[str] = None
    loc_decompiled: Optional[int] = None
    cyclomatic: Optional[int] = None
    bb_count: Optional[int] = None
    arch: Optional[str] = None
    opt: Optional[str] = None

    # Bookkeeping metadata — NOT part of the sanitized LLM input.
    # Populated from the raw row after sanitisation for result-join only.
    # Must NEVER be injected into prompts.
    test_case: Optional[str] = Field(None, description="Bookkeeping only — NOT sent to LLM")
    variant: Optional[str] = Field(None, description="Bookkeeping only — NOT sent to LLM")

    # Structural context (prompt-ready text, None when not requested)
    calls_text: Optional[str] = Field(None, description="Formatted call edges (L1+)")
    cfg_text: Optional[str] = Field(None, description="Formatted CFG summary (L2)")
    variables_text: Optional[str] = Field(None, description="Formatted variable table (L2)")


@router.get(
    "/functions",
    response_model=List[LLMInputRowWithContext],
    summary="Sanitized function records for LLM consumption",
)
async def list_llm_functions(
    test_case: Optional[str] = Query(None, description="e.g. t02"),
    opt: str = Query("O0", description="Optimisation level"),
    variant: str = Query("stripped", description="Build variant"),
    tier: Optional[str] = Query(None, description="Confidence tier filter, e.g. GOLD"),
    metadata_mode: MetadataMode = Query(
        MetadataMode.STRICT,
        description="Controls which metadata the LLM may see",
    ),
    context_level: ContextLevel = Query(
        ContextLevel.L0,
        description="Structural context: L0=code, L1=+calls, L2=+calls+cfg+vars",
    ),
    limit: int = Query(500, ge=1, le=5000, description="Max rows"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """Return sanitized function records with ONLY Ghidra-derived fields.

    Ground-truth labels (``dwarf_function_name``, ``confidence_tier``, etc.)
    are stripped.  The response model enforces the whitelist at serialisation
    time — even if a bug in ``sanitize_for_llm`` lets a field through,
    Pydantic will not emit it.

    The ``metadata_mode`` parameter controls identity context:

    - ``STRICT`` — only ``c_raw`` and Ghidra diagnostics
    - ``ANALYST`` — adds ``arch`` (what a human analyst would know)
    - ``ANALYST_FULL`` — adds ``arch`` and ``opt``

    The ``context_level`` parameter controls structural Ghidra context:

    - ``L0`` — code only (default)
    - ``L1`` — code + call edges
    - ``L2`` — code + call edges + CFG summary + variable table
    """
    if test_case is None:
        try:
            all_tc = discover_test_cases(SYNTHETIC_ROOT)
        except FileNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Artifacts root not found: {SYNTHETIC_ROOT}",
            )
        raw_rows: list = []
        for tc in all_tc:
            rows = load_functions_with_decompiled(
                tc, opt, variant, tier=tier, artifacts_root=SYNTHETIC_ROOT,
            )
            raw_rows.extend(rows)
    else:
        all_tc = [test_case]
        raw_rows = load_functions_with_decompiled(
            test_case, opt, variant, tier=tier, artifacts_root=SYNTHETIC_ROOT,
        )

    # Audit: log how many forbidden keys exist in the raw data (metric)
    if raw_rows:
        leak_counts = audit_leakage_counts(raw_rows[:1])  # sample first row
        if leak_counts:
            log.debug(
                "llm_data: raw data contains %d forbidden key type(s) — "
                "all stripped by sanitize_for_llm",
                len(leak_counts),
            )

    # Paginate BEFORE sanitising (cheaper to slice raw dicts)
    page = raw_rows[offset: offset + limit]

    # Sanitize
    sanitized = sanitize_batch(page, metadata_mode, arch=_DATASET_ARCH)

    # ── Load structural context if requested ──────────────────────────────
    calls_lookup: Dict[str, Any] = {}
    cfg_lookup: Dict[str, Any] = {}
    vars_lookup: Dict[str, Any] = {}

    if context_level in (ContextLevel.L1, ContextLevel.L2):
        for tc in set(r.get("test_case", test_case or "") for r in page):
            if not tc:
                continue
            calls_lookup.update(
                load_ghidra_calls(tc, opt, variant, artifacts_root=SYNTHETIC_ROOT)
            )

    if context_level == ContextLevel.L2:
        for tc in set(r.get("test_case", test_case or "") for r in page):
            if not tc:
                continue
            cfg_lookup.update(
                load_ghidra_cfg(tc, opt, variant, artifacts_root=SYNTHETIC_ROOT)
            )
            vars_lookup.update(
                load_ghidra_variables(tc, opt, variant, artifacts_root=SYNTHETIC_ROOT)
            )

    # ── Build enriched response ───────────────────────────────────────────
    result: List[LLMInputRowWithContext] = []
    for san, raw in zip(sanitized, page):
        gfid = raw.get("ghidra_func_id", "")
        row_dict = san.model_dump()

        # Inject bookkeeping metadata from raw row (stripped by sanitiser)
        row_dict["test_case"] = raw.get("test_case")
        row_dict["variant"] = raw.get("variant")

        # Attach structural context
        if context_level in (ContextLevel.L1, ContextLevel.L2):
            row_dict["calls_text"] = format_calls_for_prompt(
                calls_lookup.get(gfid, [])
            )
        if context_level == ContextLevel.L2:
            row_dict["cfg_text"] = format_cfg_for_prompt(
                cfg_lookup.get(gfid, {})
            )
            row_dict["variables_text"] = format_variables_for_prompt(
                vars_lookup.get(gfid, [])
            )

        result.append(LLMInputRowWithContext(**row_dict))

    return result


@router.get(
    "/functions/{dwarf_function_id}",
    response_model=LLMInputRow,
    summary="Get a single sanitized function by DWARF function ID",
)
async def get_llm_function(
    dwarf_function_id: str,
    test_case: str = Query(..., description="Test case, e.g. t02"),
    opt: str = Query("O0", description="Optimisation level"),
    variant: str = Query("stripped", description="Build variant"),
    metadata_mode: MetadataMode = Query(
        MetadataMode.STRICT,
        description="Controls which metadata the LLM may see",
    ),
):
    """Look up a single function and return it sanitized."""
    raw_rows = load_functions_with_decompiled(
        test_case, opt, variant, artifacts_root=SYNTHETIC_ROOT,
    )
    for row in raw_rows:
        if row.get("dwarf_function_id") == dwarf_function_id:
            return sanitize_for_llm(row, metadata_mode, arch=_DATASET_ARCH)

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=(
            f"Function {dwarf_function_id} not found "
            f"in {test_case}/{opt}/{variant}"
        ),
    )
