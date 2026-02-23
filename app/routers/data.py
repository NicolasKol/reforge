"""
Data Router
Serves ground-truth function data (identity + decompiled C) to n8n workflows.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.config import settings
from data.loader import (
    load_functions_with_decompiled,
    _load_jsonl,
)
from data.paths import discover_test_cases, joined_functions_path
from data.schema import FunctionDataRow
from data.experiments import (
    ExperimentConfig,
    ExperimentStatus,
    REGISTRY,
    _register,
    list_experiments as _list_experiments,
    get_experiment as _get_experiment,
)

log = logging.getLogger(__name__)

router = APIRouter()

SYNTHETIC_ROOT = Path(settings.ARTIFACTS_PATH) / "synthetic"


@router.get(
    "/functions",
    response_model=List[FunctionDataRow],
    summary="List functions with decompiled C",
)
async def list_functions(
    test_case: Optional[str] = Query(None, description="e.g. t02"),
    opt: str = Query("O0", description="Optimization level"),
    variant: str = Query("stripped", description="Build variant"),
    tier: Optional[str] = Query(None, description="Confidence tier filter, e.g. GOLD"),
    limit: int = Query(500, ge=1, le=5000, description="Max rows to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """Return joined function records with decompiled C attached.

    Combines ``joined_functions.jsonl`` (DWARF ground truth) with
    ``ghidra_decompile/functions.jsonl`` (``c_raw``).  Suitable for
    feeding into n8n LLM experiment workflows.
    """
    if test_case is None:
        # Discover all test cases and aggregate
        try:
            all_tc = discover_test_cases(SYNTHETIC_ROOT)
        except FileNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Artifacts root not found: {SYNTHETIC_ROOT}",
            )
        all_rows: list = []
        for tc in all_tc:
            rows = load_functions_with_decompiled(
                tc, opt, variant, tier=tier, artifacts_root=SYNTHETIC_ROOT,
            )
            all_rows.extend(rows)
    else:
        all_rows = load_functions_with_decompiled(
            test_case, opt, variant, tier=tier, artifacts_root=SYNTHETIC_ROOT,
        )

    # Paginate
    page = all_rows[offset : offset + limit]
    return page


@router.get(
    "/functions/{dwarf_function_id}",
    response_model=FunctionDataRow,
    summary="Get a single function by DWARF function ID",
)
async def get_function(
    dwarf_function_id: str,
    test_case: str = Query(..., description="Test case, e.g. t02"),
    opt: str = Query("O0", description="Optimization level"),
    variant: str = Query("stripped", description="Build variant"),
):
    """Look up a single function record by its DWARF function ID."""
    rows = load_functions_with_decompiled(
        test_case, opt, variant, artifacts_root=SYNTHETIC_ROOT,
    )
    for row in rows:
        if row.get("dwarf_function_id") == dwarf_function_id:
            return row

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Function {dwarf_function_id} not found in {test_case}/{opt}/{variant}",
    )


@router.get(
    "/summary",
    summary="Dataset summary counts",
)
async def dataset_summary(
    variant: str = Query("stripped", description="Build variant"),
):
    """Return per-test-case, per-opt counts grouped by confidence tier.

    Useful for experiment planning — shows how many GOLD / SILVER / BRONZE
    functions are available in each cell.
    """
    try:
        all_tc = discover_test_cases(SYNTHETIC_ROOT)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifacts root not found: {SYNTHETIC_ROOT}",
        )

    opt_levels = ["O0", "O1", "O2", "O3"]
    summary: list = []

    for tc in all_tc:
        for opt in opt_levels:
            joined_path = joined_functions_path(
                SYNTHETIC_ROOT, tc, opt, variant,
            )
            rows = _load_jsonl(joined_path)
            if not rows:
                continue

            tier_counts: dict = {}
            for r in rows:
                t = r.get("confidence_tier", "") or "NONE"
                tier_counts[t] = tier_counts.get(t, 0) + 1

            summary.append({
                "test_case": tc,
                "opt": opt,
                "total": len(rows),
                **{f"n_{k.lower()}": v for k, v in sorted(tier_counts.items())},
            })

    return {"cells": summary, "total_cells": len(summary)}


# ═══════════════════════════════════════════════════════════════════════════════
# Experiment Configuration Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/experiments",
    response_model=List[ExperimentConfig],
    summary="List experiment configurations",
)
async def list_experiment_configs(
    task: Optional[str] = Query(None, description="Filter by task type, e.g. function_naming"),
    status: Optional[ExperimentStatus] = Query(None, description="Filter by status: draft, ready, completed"),
    tag: Optional[str] = Query(None, description="Filter by tag, e.g. baseline"),
):
    """Return experiment configurations defined in the project.

    n8n workflows fetch this list, let the user pick an experiment,
    then execute it — no hardcoded config in the workflow.
    """
    return _list_experiments(task=task, status=status, tag=tag)


@router.get(
    "/experiments/{experiment_id}",
    response_model=ExperimentConfig,
    summary="Get a single experiment configuration",
)
async def get_experiment_config(experiment_id: str):
    """Return a single experiment config by ID."""
    exp = _get_experiment(experiment_id)
    if exp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment '{experiment_id}' not found",
        )
    return exp


@router.post(
    "/experiments",
    response_model=ExperimentConfig,
    status_code=status.HTTP_201_CREATED,
    summary="Register an experiment configuration",
)
async def register_experiment(config: ExperimentConfig):
    """Register (or update) an experiment config in the in-memory registry.

    The notebook calls this after ``build_benchmark_matrix()`` so the API
    server knows about dynamically-generated experiments.
    """
    # Upsert: allow overwriting an existing config
    REGISTRY[config.id] = config
    log.info("Registered experiment %s", config.id)
    return config


@router.post(
    "/experiments/bulk",
    summary="Register multiple experiment configurations at once",
)
async def register_experiments_bulk(configs: List[ExperimentConfig]):
    """Bulk-register experiment configs.  Useful for pushing an entire
    benchmark matrix from the notebook to the API server in one call."""
    created = 0
    updated = 0
    for cfg in configs:
        if cfg.id in REGISTRY:
            updated += 1
        else:
            created += 1
        REGISTRY[cfg.id] = cfg
    log.info("Bulk registered %d experiments (%d new, %d updated)",
             len(configs), created, updated)
    return {"registered": len(configs), "created": created, "updated": updated}
