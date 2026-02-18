"""
Results Router
Persists and retrieves LLM experiment results as JSONL files.
Includes job_id-based idempotency and run registry.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.config import settings
from data.loader import load_functions_with_decompiled
from data.paths import discover_test_cases
from data.reporting import generate_report
from data.schema import LLMResultRow, RunRecord
from data.scoring import score_experiment

log = logging.getLogger(__name__)

router = APIRouter()

# Results live alongside artifacts:  <ARTIFACTS_PATH>/results/llm/<experiment_id>/results.jsonl
RESULTS_ROOT = Path(settings.ARTIFACTS_PATH) / "results" / "llm"
RUNS_ROOT = Path(settings.ARTIFACTS_PATH) / "results" / "runs"
SYNTHETIC_ROOT = Path(settings.ARTIFACTS_PATH) / "synthetic"


# ═══════════════════════════════════════════════════════════════════════════════
# Job-ID Dedupe Index  (in-memory, rebuilt from JSONL on startup)
# ═══════════════════════════════════════════════════════════════════════════════

_job_index: Dict[str, Set[str]] = {}   # experiment_id → set of job_ids
_job_lock = Lock()


def _ensure_index(experiment_id: str) -> Set[str]:
    """Load or return the in-memory job_id index for an experiment."""
    with _job_lock:
        if experiment_id not in _job_index:
            path = _results_path(experiment_id)
            ids: Set[str] = set()
            if path.exists():
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                row = json.loads(line)
                                jid = row.get("job_id")
                                if jid:
                                    ids.add(jid)
                            except json.JSONDecodeError:
                                continue
            _job_index[experiment_id] = ids
        return _job_index[experiment_id]


# ═══════════════════════════════════════════════════════════════════════════════
# Path helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _results_path(experiment_id: str) -> Path:
    """Canonical JSONL path for an experiment."""
    return RESULTS_ROOT / experiment_id / "results.jsonl"


def _run_path(run_id: str) -> Path:
    """Canonical JSON path for a run record."""
    return RUNS_ROOT / f"{run_id}.json"


# ═══════════════════════════════════════════════════════════════════════════════
# Result Endpoints (with idempotency)
# ═══════════════════════════════════════════════════════════════════════════════

@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Append one LLM result row (idempotent by job_id)",
)
async def post_result(row: LLMResultRow):
    """Append a single result row. Skips silently if job_id already exists."""
    index = _ensure_index(row.experiment_id)

    if row.job_id in index:
        return {
            "status": "ok",
            "experiment_id": row.experiment_id,
            "run_id": row.run_id,
            "rows_written": 0,
            "rows_skipped": 1,
        }

    path = _results_path(row.experiment_id)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "a", encoding="utf-8") as f:
        f.write(row.model_dump_json() + "\n")

    with _job_lock:
        index.add(row.job_id)

    log.info("appended result to %s (run=%s, job=%s)", path, row.run_id, row.job_id)
    return {
        "status": "ok",
        "experiment_id": row.experiment_id,
        "run_id": row.run_id,
        "rows_written": 1,
        "rows_skipped": 0,
    }


@router.post(
    "/batch",
    status_code=status.HTTP_201_CREATED,
    summary="Append multiple LLM result rows (idempotent by job_id)",
)
async def post_results_batch(rows: List[LLMResultRow]):
    """Append a batch of result rows.  Deduplicates by job_id within batch and
    against previously stored rows.  All rows must share the same experiment_id."""
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty batch",
        )

    experiment_id = rows[0].experiment_id
    if any(r.experiment_id != experiment_id for r in rows):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="All rows in a batch must share the same experiment_id",
        )

    index = _ensure_index(experiment_id)

    # Partition into new vs duplicate
    new_rows: List[LLMResultRow] = []
    seen_in_batch: Set[str] = set()
    skipped = 0

    for row in rows:
        if row.job_id in index or row.job_id in seen_in_batch:
            skipped += 1
        else:
            new_rows.append(row)
            seen_in_batch.add(row.job_id)

    if new_rows:
        path = _results_path(experiment_id)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "a", encoding="utf-8") as f:
            for row in new_rows:
                f.write(row.model_dump_json() + "\n")

        with _job_lock:
            index.update(seen_in_batch)

    log.info(
        "batch to %s: %d written, %d skipped",
        experiment_id, len(new_rows), skipped,
    )
    return {
        "status": "ok",
        "experiment_id": experiment_id,
        "rows_written": len(new_rows),
        "rows_skipped": skipped,
    }


@router.get(
    "",
    summary="List experiments with stored results",
)
async def list_result_experiments():
    """Return a list of experiment IDs that have stored results."""
    if not RESULTS_ROOT.exists():
        return {"experiments": []}

    experiments = []
    for d in sorted(RESULTS_ROOT.iterdir()):
        if d.is_dir():
            results_file = d / "results.jsonl"
            row_count = 0
            if results_file.exists():
                with open(results_file, encoding="utf-8") as f:
                    row_count = sum(1 for line in f if line.strip())
            experiments.append({
                "experiment_id": d.name,
                "row_count": row_count,
            })

    return {"experiments": experiments}


# ═══════════════════════════════════════════════════════════════════════════════
# Run Registry Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

class CreateRunRequest(BaseModel):
    run_id: str
    experiment_id: str
    models: List[str] = Field(default_factory=list)
    repeats: int = 1
    filters: Dict[str, Any] = Field(default_factory=dict)
    planned_jobs: int = 0


class UpdateRunRequest(BaseModel):
    status: Optional[str] = None
    completed_jobs: Optional[int] = None
    increment_completed_jobs: Optional[int] = None


class RunErrorRequest(BaseModel):
    workflow_name: str = ""
    node_name: str = ""
    message: str = ""
    stack: str = ""
    context: Dict[str, Any] = Field(default_factory=dict)


@router.post(
    "/runs",
    status_code=status.HTTP_201_CREATED,
    summary="Register a new benchmarking run",
)
async def create_run(req: CreateRunRequest):
    """Create a run record.  Returns the frozen run configuration."""
    path = _run_path(req.run_id)
    if path.exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run '{req.run_id}' already exists",
        )

    now = datetime.now(timezone.utc).isoformat()
    record = RunRecord(
        run_id=req.run_id,
        experiment_id=req.experiment_id,
        status="pending",
        models=req.models,
        repeats=req.repeats,
        filters=req.filters,
        planned_jobs=req.planned_jobs,
        created_at=now,
        updated_at=now,
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(record.model_dump_json(indent=2))

    log.info("created run %s for experiment %s", req.run_id, req.experiment_id)
    return record.model_dump()


@router.get(
    "/runs",
    summary="List all registered runs",
)
async def list_runs(
    experiment_id: Optional[str] = Query(default=None),
    run_status: Optional[str] = Query(default=None, alias="status"),
):
    """List run records, optionally filtered by experiment_id and status."""
    if not RUNS_ROOT.exists():
        return {"runs": []}

    runs = []
    for f in sorted(RUNS_ROOT.glob("*.json")):
        try:
            record = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if experiment_id and record.get("experiment_id") != experiment_id:
            continue
        if run_status and record.get("status") != run_status:
            continue
        runs.append(record)

    return {"runs": runs}


@router.get(
    "/runs/{run_id}",
    summary="Get a specific run record",
)
async def get_run(run_id: str):
    """Return a single run record by ID."""
    path = _run_path(run_id)
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found",
        )
    return json.loads(path.read_text(encoding="utf-8"))


@router.patch(
    "/runs/{run_id}",
    summary="Update run status or progress",
)
async def update_run(run_id: str, req: UpdateRunRequest):
    """Update a run's status or completed_jobs count."""
    path = _run_path(run_id)
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found",
        )

    record = json.loads(path.read_text(encoding="utf-8"))
    if req.status is not None:
        record["status"] = req.status
    if req.increment_completed_jobs is not None:
        record["completed_jobs"] = record.get("completed_jobs", 0) + req.increment_completed_jobs
    elif req.completed_jobs is not None:
        record["completed_jobs"] = req.completed_jobs
    record["updated_at"] = datetime.now(timezone.utc).isoformat()

    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)

    return record


@router.post(
    "/runs/{run_id}/errors",
    status_code=status.HTTP_201_CREATED,
    summary="Append an error to a run",
)
async def add_run_error(run_id: str, error: RunErrorRequest):
    """Capture an error that occurred during the run."""
    path = _run_path(run_id)
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found",
        )

    record = json.loads(path.read_text(encoding="utf-8"))
    record.setdefault("errors", []).append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "workflow_name": error.workflow_name,
        "node_name": error.node_name,
        "message": error.message,
        "stack": error.stack,
        "context": error.context,
    })
    record["updated_at"] = datetime.now(timezone.utc).isoformat()

    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)

    log.warning("error captured for run %s: %s", run_id, error.message)
    return {"status": "ok", "error_count": len(record["errors"])}


# ═══════════════════════════════════════════════════════════════════════════════
# Scoring & Reporting (before wildcard /{experiment_id} routes)
# ═══════════════════════════════════════════════════════════════════════════════


def _read_results_jsonl(experiment_id: str) -> List[Dict[str, Any]]:
    """Read all result rows from an experiment's JSONL file."""
    path = _results_path(experiment_id)
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _scored_path(experiment_id: str) -> Path:
    """Canonical JSONL path for scored results."""
    return RESULTS_ROOT / experiment_id / "scored_results.jsonl"


def _build_gt_lookup(
    rows: List[Dict[str, Any]],
) -> Dict[str, str]:
    """Build a ground-truth lookup from the data layer.

    Scans the result rows for unique (test_case, opt) pairs, loads the
    full function data for each, and returns a map of
    ``dwarf_function_id → dwarf_function_name``.

    This is the **post-hoc join** — ground truth is fetched *after*
    predictions are recorded, never during the LLM pipeline.
    """
    # Collect unique (test_case, opt) combos present in results
    combos: Set[tuple] = set()
    for r in rows:
        tc = r.get("test_case")
        opt = r.get("opt")
        if tc and opt:
            combos.add((tc, opt))

    gt_map: Dict[str, str] = {}
    for tc, opt in combos:
        try:
            funcs = load_functions_with_decompiled(
                test_case=tc,
                opt=opt,
                variant="stripped",
                artifacts_root=SYNTHETIC_ROOT,
            )
            for fn in funcs:
                fid = fn.get("dwarf_function_id", "")
                name = fn.get("dwarf_function_name")
                if fid and name:
                    gt_map[fid] = name
        except Exception as exc:
            log.warning(
                "could not load GT for %s/%s: %s", tc, opt, exc,
            )
    return gt_map


def _build_stable_key_lookup(
    rows: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Build a stable-key lookup for cross-opt pairing.

    Returns a map of ``dwarf_function_id → {stable_key, decl_file,
    decl_line, decl_column, dwarf_function_name_norm, confidence_tier,
    quality_weight, overlap_ratio, bb_count, cyclomatic, loc_decompiled}``.

    The stable_key is ``test_case|decl_file|decl_line|decl_column|name_norm``
    and is consistent across optimization levels (unlike ``dwarf_function_id``
    which shifts ~86% between O0 and O1).
    """
    combos: Set[tuple] = set()
    for r in rows:
        tc = r.get("test_case")
        opt = r.get("opt")
        if tc and opt:
            combos.add((tc, opt))

    sk_map: Dict[str, Dict[str, Any]] = {}
    for tc, opt in combos:
        try:
            funcs = load_functions_with_decompiled(
                test_case=tc,
                opt=opt,
                variant="stripped",
                artifacts_root=SYNTHETIC_ROOT,
            )
            for fn in funcs:
                fid = fn.get("dwarf_function_id", "")
                if not fid:
                    continue

                decl_file = fn.get("decl_file", "")
                decl_line = fn.get("decl_line", "")
                decl_column = fn.get("decl_column", "")
                name = fn.get("dwarf_function_name", "")
                name_norm = fn.get("dwarf_function_name_norm", name.lower() if name else "")

                # Build stable key (matches metrics.py _add_merge_key logic)
                if decl_file and decl_line:
                    stable_key = f"{tc}|{decl_file}|{decl_line}|{decl_column}|{name_norm}"
                else:
                    # No declaration info → use sentinel (not stable across opts)
                    stable_key = f"_unstable_{tc}_{opt}_{fid}"

                sk_map[fid] = {
                    "stable_key": stable_key,
                    "decl_file": decl_file,
                    "decl_line": decl_line,
                    "decl_column": decl_column,
                    "dwarf_function_name_norm": name_norm,
                    "confidence_tier": fn.get("confidence_tier", ""),
                    "quality_weight": fn.get("quality_weight"),
                    "overlap_ratio": fn.get("overlap_ratio"),
                    "bb_count": fn.get("bb_count"),
                    "cyclomatic": fn.get("cyclomatic"),
                    "loc_decompiled": fn.get("loc_decompiled"),
                }
        except Exception as exc:
            log.warning(
                "could not load stable keys for %s/%s: %s", tc, opt, exc,
            )
    return sk_map


# ═══════════════════════════════════════════════════════════════════════════════
# Repair endpoint — fix results where runner didn't parse top-k responses
# ═══════════════════════════════════════════════════════════════════════════════


@router.post(
    "/{experiment_id}/repair",
    summary="Repair top-k results: parse response_text into predictions",
)
async def repair_results(experiment_id: str):
    """One-time repair for experiments run before the top-k parser was deployed.

    Problem: the old runner stored the raw JSON response as ``predicted_name``
    instead of parsing it into top-1 name + predictions metadata.

    Fix: re-parse ``response_text`` with parse_topk_response, update
    ``predicted_name`` to the top-1 candidate, and store predictions in metadata.
    Then overwrites ``results.jsonl`` with the repaired rows.
    """
    from workers.llm.response_parser import parse_topk_response

    results_path = _results_path(experiment_id)
    if not results_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No results found for experiment '{experiment_id}'",
        )

    rows = _read_results_jsonl(experiment_id)
    if not rows:
        return {"status": "ok", "experiment_id": experiment_id, "repaired": 0}

    repaired_count = 0
    for row in rows:
        response_text = row.get("response_text", "")
        predicted_name = row.get("predicted_name", "")

        # Only repair rows where predicted_name looks like raw JSON
        # (starts with { or contains "predictions")
        needs_repair = (
            predicted_name.lstrip().startswith("{")
            or '"predictions"' in predicted_name
        )
        if not needs_repair:
            continue

        parsed = parse_topk_response(response_text or predicted_name, k=3)

        # Update predicted_name to top-1 candidate
        if parsed.predictions:
            row["predicted_name"] = parsed.predictions[0]["name"]
        else:
            row["predicted_name"] = predicted_name  # leave as-is if parse fails

        # Store predictions in metadata
        metadata = row.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        metadata["predictions"] = parsed.predictions
        metadata["parse_ok"] = parsed.parse_ok
        if parsed.parse_error:
            metadata["parse_error"] = parsed.parse_error
        metadata["all_candidate_names"] = [
            p["name"] for p in parsed.predictions
        ]
        metadata["top_k"] = 3
        row["metadata"] = metadata

        repaired_count += 1

    # Overwrite results.jsonl with repaired rows
    with open(results_path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, default=str) + "\n")

    # Clear job index so it gets rebuilt
    with _job_lock:
        _job_index.pop(experiment_id, None)

    log.info("repaired %d/%d rows for %s", repaired_count, len(rows), experiment_id)
    return {
        "status": "ok",
        "experiment_id": experiment_id,
        "total_rows": len(rows),
        "repaired": repaired_count,
    }


@router.post(
    "/{experiment_id}/score",
    summary="Score all results for an experiment",
)
async def score_results(experiment_id: str):
    """Run the deterministic scorer on stored results.

    Reads ``results.jsonl``, scores each row, and writes
    ``scored_results.jsonl`` alongside.  Idempotent — re-running
    overwrites the scored file.

    Ground truth is joined **post-hoc** from the data layer using
    ``dwarf_function_id``.  The LLM pipeline never sees GT labels.
    """
    results_path = _results_path(experiment_id)
    if not results_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No results found for experiment '{experiment_id}'",
        )

    rows = _read_results_jsonl(experiment_id)
    if not rows:
        return {"status": "ok", "experiment_id": experiment_id, "scored": 0}

    # ── Post-hoc GT join ──────────────────────────────────────────────
    # If results lack ground_truth_name (leak-proof pipeline), look it
    # up from the data layer now.
    needs_gt = any(not r.get("ground_truth_name") for r in rows)
    if needs_gt:
        gt_map = _build_gt_lookup(rows)
        for row in rows:
            if not row.get("ground_truth_name"):
                fid = row.get("dwarf_function_id", "")
                row["ground_truth_name"] = gt_map.get(fid, "")

    # ── Stable key enrichment (for cross-opt pairing) ─────────────────
    sk_map = _build_stable_key_lookup(rows)
    for row in rows:
        fid = row.get("dwarf_function_id", "")
        sk_data = sk_map.get(fid)
        if sk_data:
            metadata = row.get("metadata", {})
            if not isinstance(metadata, dict):
                metadata = {}
            metadata["stable_key"] = sk_data["stable_key"]
            metadata["confidence_tier"] = sk_data["confidence_tier"]
            metadata["quality_weight"] = sk_data["quality_weight"]
            metadata["overlap_ratio"] = sk_data["overlap_ratio"]
            metadata["bb_count"] = sk_data["bb_count"]
            metadata["cyclomatic"] = sk_data["cyclomatic"]
            metadata["loc_decompiled"] = sk_data["loc_decompiled"]
            row["metadata"] = metadata

    scored = score_experiment(rows)

    out_path = _scored_path(experiment_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for row in scored:
            f.write(json.dumps(row, default=str) + "\n")

    n = len(scored)
    em = sum(1 for r in scored if r.get("exact_match_norm", False))
    avg_f1 = sum(r.get("token_f1", 0.0) for r in scored) / n
    trivial = sum(1 for r in scored if r.get("is_trivial_prediction", False))

    log.info("scored %d rows for %s → %s", n, experiment_id, out_path)
    return {
        "status": "ok",
        "experiment_id": experiment_id,
        "scored": n,
        "exact_match_rate": round(em / n, 4),
        "mean_token_f1": round(avg_f1, 4),
        "trivial_count": trivial,
        "scorer_version": scored[0].get("scorer_version", "unknown"),
    }


@router.get(
    "/{experiment_id}/scores",
    summary="Get scored results for an experiment",
)
async def get_scored_results(
    experiment_id: str,
    limit: int = Query(1000, ge=1, le=10000),
    offset: int = Query(0, ge=0),
):
    """Return scored result rows from ``scored_results.jsonl``."""
    path = _scored_path(experiment_id)
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No scored results for '{experiment_id}'. "
                f"Run POST /results/{experiment_id}/score first."
            ),
        )

    rows: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i < offset:
                continue
            if len(rows) >= limit:
                break
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    return {
        "experiment_id": experiment_id,
        "rows": rows,
        "count": len(rows),
        "offset": offset,
    }


@router.get(
    "/{experiment_id}/report",
    summary="Generate stratified report for an experiment",
)
async def get_experiment_report(
    experiment_id: str,
    run_id: Optional[str] = Query(None, description="Filter by run_id"),
):
    """Generate and return a stratified JSON report from scored results.

    Loads scored results, enriches them with function metadata (post-hoc)
    for stratification by confidence tier and quality weight, then
    aggregates metrics across multiple dimensions.
    """
    scored_path_ = _scored_path(experiment_id)
    if not scored_path_.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No scored results for '{experiment_id}'. "
                f"Run POST /results/{experiment_id}/score first."
            ),
        )

    # Read scored rows
    scored_rows: List[Dict[str, Any]] = []
    with open(scored_path_, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                row = json.loads(line)
                if run_id and row.get("run_id") != run_id:
                    continue
                scored_rows.append(row)

    if not scored_rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No scored rows found (run_id={run_id})",
        )

    # Load function metadata for stratification (post-hoc)
    function_metadata: List[Dict[str, Any]] = []
    try:
        all_tc = discover_test_cases(SYNTHETIC_ROOT)
        # Collect relevant opt levels from scored rows
        opt_levels = {r.get("opt", "O0") for r in scored_rows}
        for tc in all_tc:
            for opt in opt_levels:
                rows = load_functions_with_decompiled(
                    tc, opt, "stripped", artifacts_root=SYNTHETIC_ROOT,
                )
                function_metadata.extend(rows)
    except Exception:
        log.warning(
            "Could not load function metadata for stratification — "
            "report will lack tier/quality_weight breakdowns",
        )

    report = generate_report(
        experiment_id=experiment_id,
        run_id=run_id,
        scored_rows=scored_rows,
        function_metadata=function_metadata if function_metadata else None,
    )

    return report


@router.get(
    "/{experiment_id}/completed-ids",
    summary="Get completed function IDs for resume support",
)
async def get_completed_ids(
    experiment_id: str,
    run_id: str = Query(..., description="Run ID to filter by"),
):
    """Return the set of ``dwarf_function_id`` values already predicted.

    The LLM worker calls this before each run to skip already-completed
    functions, enabling full run resume.
    """
    rows = _read_results_jsonl(experiment_id)
    completed = list({
        r["dwarf_function_id"]
        for r in rows
        if r.get("run_id") == run_id and r.get("dwarf_function_id")
    })

    return {
        "run_id": run_id,
        "experiment_id": experiment_id,
        "completed_ids": completed,
        "count": len(completed),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Experiment Results (must be AFTER /runs and /score routes to avoid wildcard clash)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/{experiment_id}",
    summary="Get all results for an experiment",
)
async def get_experiment_results(
    experiment_id: str,
    limit: int = Query(1000, ge=1, le=10000),
    offset: int = Query(0, ge=0),
):
    """Read and return result rows from the experiment's JSONL file."""
    path = _results_path(experiment_id)
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No results found for experiment '{experiment_id}'",
        )

    rows = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i < offset:
                continue
            if len(rows) >= limit:
                break
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    return {
        "experiment_id": experiment_id,
        "rows": rows,
        "count": len(rows),
        "offset": offset,
    }
