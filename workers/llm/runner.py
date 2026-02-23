"""
Async LLM Experiment Runner
============================

Standalone worker that drives an experiment end-to-end:

1. Fetch experiment config from the API
2. Fetch sanitized functions (leak-proof)
3. Fetch already-completed IDs (for resume)
4. Build prompts from the template
5. Call OpenRouter (OpenAI-compatible) with async concurrency
6. POST result rows back to the API in batches
7. Trigger scoring + report generation

Usage (CLI)::

    python -m workers.llm.runner \\
        --experiment exp01_funcnaming_gpt4omini_gold_O0 \\
        --api-base http://localhost:8080 \\
        --concurrency 5

Usage (notebook / async)::

    from workers.llm.runner import run_experiment
    summary = await run_experiment("exp01_...", api_base="http://localhost:8080")
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from workers.llm.prompt import load_template, render_prompt
from workers.llm.response_parser import parse_topk_response
from workers.llm.model_router import (
    call_llm,
    check_model_available,
    get_profile,
    detect_provider,
    strip_thinking_tags,
)

log = logging.getLogger(__name__)

# ─── Defaults ────────────────────────────────────────────────────────────────

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
DEFAULT_CONCURRENCY = 5
BATCH_POST_SIZE = 10  # rows per POST to /results/batch


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _job_id(
    experiment_id: str,
    run_id: str,
    dwarf_function_id: str,
    model: str,
    prompt_template_id: str,
    temperature: float,
) -> str:
    """Deterministic job ID for idempotency."""
    key = "|".join([
        experiment_id, run_id, dwarf_function_id,
        model, prompt_template_id, str(temperature),
    ])
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _ts() -> str:
    """ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


# ─── API helpers (async) ─────────────────────────────────────────────────────

async def _fetch_experiment(client: httpx.AsyncClient, api_base: str, experiment_id: str) -> Dict[str, Any]:
    """GET /data/experiments/{id}."""
    resp = await client.get(f"{api_base}/data/experiments/{experiment_id}")
    resp.raise_for_status()
    return resp.json()


async def _fetch_functions(
    client: httpx.AsyncClient,
    api_base: str,
    *,
    opt: str,
    tier: str,
    metadata_mode: str,
    context_level: str = "L0",
    limit: int,
    test_case: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """GET /llm/functions with pagination to fetch all rows."""
    params: Dict[str, Any] = {
        "opt": opt,
        "tier": tier,
        "metadata_mode": metadata_mode,
        "context_level": context_level,
        "limit": limit if limit > 0 else 5000,
        "offset": 0,
    }
    if test_case:
        params["test_case"] = test_case

    resp = await client.get(f"{api_base}/llm/functions", params=params)
    resp.raise_for_status()
    return resp.json()


async def _fetch_completed_ids(
    client: httpx.AsyncClient,
    api_base: str,
    experiment_id: str,
    run_id: str,
) -> set[str]:
    """GET /results/{experiment_id}/completed-ids?run_id=..."""
    resp = await client.get(
        f"{api_base}/results/{experiment_id}/completed-ids",
        params={"run_id": run_id},
    )
    if resp.status_code == 404:
        return set()
    resp.raise_for_status()
    data = resp.json()
    return set(data.get("completed_ids", []))


async def _post_batch(
    client: httpx.AsyncClient,
    api_base: str,
    rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """POST /results/batch."""
    resp = await client.post(f"{api_base}/results/batch", json=rows)
    if resp.status_code == 422:
        log.error("Batch 422 detail: %s", resp.text[:500])
    resp.raise_for_status()
    return resp.json()


async def _trigger_scoring(
    client: httpx.AsyncClient,
    api_base: str,
    experiment_id: str,
) -> Dict[str, Any]:
    """POST /results/{experiment_id}/score."""
    resp = await client.post(f"{api_base}/results/{experiment_id}/score")
    resp.raise_for_status()
    return resp.json()


async def _fetch_report(
    client: httpx.AsyncClient,
    api_base: str,
    experiment_id: str,
) -> Dict[str, Any]:
    """GET /results/{experiment_id}/report."""
    resp = await client.get(f"{api_base}/results/{experiment_id}/report")
    resp.raise_for_status()
    return resp.json()


# ─── OpenRouter call ─────────────────────────────────────────────────────────
# Now delegated to workers.llm.model_router.call_llm for model-aware routing.
# The call_llm function automatically:
#   - Detects the provider (OpenAI, Anthropic, DeepSeek, Google, etc.)
#   - Adapts response_format based on model capabilities
#   - Adds provider-specific headers (Anthropic beta, etc.)
#   - Routes to compatible providers via require_parameters
#   - Strips <think> tags from reasoning model output


# ─── Core runner ──────────────────────────────────────────────────────────────

async def run_experiment(
    experiment_id: str,
    *,
    api_base: str = "http://localhost:8080",
    openrouter_key: Optional[str] = None,
    run_id: Optional[str] = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Execute an experiment end-to-end.

    Parameters
    ----------
    experiment_id : str
        Experiment ID from the registry.
    api_base : str
        Base URL of the Reforge API.
    openrouter_key : str | None
        OpenRouter API key. Falls back to ``OPENROUTER_API_KEY`` env var.
    run_id : str | None
        Unique run ID. Auto-generated if not provided.
    concurrency : int
        Max concurrent LLM calls (asyncio.Semaphore).
    dry_run : bool
        If True, build prompts but skip LLM calls and result posting.

    Returns
    -------
    dict
        Summary with keys: experiment_id, run_id, total, completed, skipped,
        new, errors, dry_run, report (if scoring succeeded).
    """
    # ── Resolve API key ───────────────────────────────────────────────────
    if openrouter_key is None:
        openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not openrouter_key and not dry_run:
        raise ValueError(
            "No OpenRouter API key provided. Set OPENROUTER_API_KEY env var "
            "or pass openrouter_key= argument."
        )

    # ── Generate run_id ───────────────────────────────────────────────────
    if run_id is None:
        run_id = f"run-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"

    log.info("=== Run %s for %s ===", run_id, experiment_id)

    # ── Progress helper (tqdm if available, else print) ───────────────────
    try:
        from tqdm.asyncio import tqdm as async_tqdm  # type: ignore[import-untyped]
        _has_tqdm = True
    except ImportError:
        async_tqdm = None  # type: ignore[assignment]
        _has_tqdm = False

    async with httpx.AsyncClient(timeout=60.0) as client:
        # 1. Fetch experiment config
        exp = await _fetch_experiment(client, api_base, experiment_id)
        model = exp["model"]
        temperature = exp.get("temperature", 0.0)
        max_tokens = exp.get("max_tokens")
        prompt_template_id = exp["prompt_template_id"]
        opt = exp.get("opt", "O0")
        tier = exp.get("tier", "GOLD")
        metadata_mode = exp.get("metadata_mode", "STRICT")
        context_level = exp.get("context_level", "L0")
        limit = exp.get("limit", 0)
        test_case = exp.get("test_case") or None
        top_k = exp.get("top_k", 1)
        response_format = exp.get("response_format")

        log.info("Config: model=%s, opt=%s, tier=%s, limit=%d, mode=%s, ctx=%s, top_k=%d",
                 model, opt, tier, limit, metadata_mode, context_level, top_k)

        # 2. Load prompt template
        template = load_template(prompt_template_id)
        log.info("Loaded prompt template: %s", prompt_template_id)

        # 3. Fetch sanitized functions (with structural context)
        functions = await _fetch_functions(
            client, api_base,
            opt=opt, tier=tier, metadata_mode=metadata_mode,
            context_level=context_level,
            limit=limit, test_case=test_case,
        )
        log.info("Fetched %d sanitized functions", len(functions))

        if not functions:
            log.warning("No functions to process — exiting")
            return {
                "experiment_id": experiment_id,
                "run_id": run_id,
                "total": 0, "completed": 0, "skipped": 0, "new": 0,
                "errors": 0, "dry_run": dry_run,
            }

        # 4. Fetch completed IDs (resume support)
        completed_ids = await _fetch_completed_ids(
            client, api_base, experiment_id, run_id,
        )
        log.info("Already completed: %d functions", len(completed_ids))

        # 5. Filter to remaining work
        todo = [
            f for f in functions
            if f["dwarf_function_id"] not in completed_ids
        ]
        skipped = len(functions) - len(todo)
        log.info("Remaining work: %d functions (%d skipped)", len(todo), skipped)

        if not todo:
            log.info("All functions already completed — nothing to do")
            return {
                "experiment_id": experiment_id,
                "run_id": run_id,
                "total": len(functions),
                "completed": len(completed_ids),
                "skipped": skipped, "new": 0, "errors": 0,
                "dry_run": dry_run,
            }

        # ── Pre-flight: check model availability & profile ─────────────────
        profile = get_profile(model)
        prov = detect_provider(model)
        log.info("Model router: provider=%s, json_mode=%s, json_schema=%s, "
                 "reasoning=%s, notes=%s",
                 prov.value, profile.supports_json_mode,
                 profile.supports_json_schema, profile.is_reasoning_model,
                 profile.notes)

        if dry_run:
            # Build prompts to validate, but don't call LLM
            # Skip availability check — no API key needed for dry runs
            for fn in todo[:3]:
                prompt = render_prompt(
                    template,
                    fn.get("c_raw", ""),
                    calls=fn.get("calls_text"),
                    cfg_summary=fn.get("cfg_text"),
                    variables=fn.get("variables_text"),
                )
                log.info("DRY RUN prompt preview (%s):\n%s",
                         fn["dwarf_function_id"], prompt[:300])
            log.info("DRY RUN: would process %d functions with %s (ctx=%s)",
                     len(todo), model, context_level)
            return {
                "experiment_id": experiment_id,
                "run_id": run_id,
                "total": len(functions),
                "completed": len(completed_ids),
                "skipped": skipped, "new": len(todo),
                "errors": 0, "dry_run": True,
            }

        # Availability check requires a valid API key — only for real runs
        availability = await check_model_available(client, openrouter_key, model)
        if not availability.get("available"):
            err_msg = availability.get("error", "unknown")
            log.error("Model %s is NOT available on OpenRouter: %s", model, err_msg)
            raise RuntimeError(
                f"Model '{model}' is not available on OpenRouter. "
                f"Error: {err_msg}. "
                f"Update the model in the experiment config."
            )
        log.info("Model %s is available (ctx_length=%s)",
                 model, availability.get("context_length"))

        # 6. Process with concurrency limit
        sem = asyncio.Semaphore(concurrency)
        results: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []

        async def _process_one(fn: Dict[str, Any]) -> None:
            """Process a single function: render → call LLM → collect."""
            func_id = fn["dwarf_function_id"]
            prompt_text = render_prompt(
                template,
                fn.get("c_raw", ""),
                calls=fn.get("calls_text"),
                cfg_summary=fn.get("cfg_text"),
                variables=fn.get("variables_text"),
            )
            jid = _job_id(experiment_id, run_id, func_id,
                          model, prompt_template_id, temperature)

            async with sem:
                try:
                    llm_result = await call_llm(
                        client, openrouter_key, model,
                        prompt_text,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        response_format=response_format,
                    )
                except Exception as exc:
                    log.error("LLM call failed for %s: %s", func_id, exc)
                    errors.append({"dwarf_function_id": func_id, "error": str(exc)})
                    return

            # Parse response (top-k or single-name)
            response_text = llm_result["response_text"]
            if top_k > 1:
                parsed = parse_topk_response(response_text, k=top_k)
                predicted_name = parsed.predictions[0]["name"] if parsed.predictions else ""
                meta_predictions = parsed.predictions
                meta_parse_ok = parsed.parse_ok
                meta_parse_error = parsed.parse_error
                all_candidate_names = [p["name"] for p in parsed.predictions]
            else:
                predicted_name = response_text
                meta_predictions = None
                meta_parse_ok = None
                meta_parse_error = None
                all_candidate_names = None

            # Assemble result row
            row_metadata: Dict[str, Any] = {
                "metadata_mode": metadata_mode,
                "context_level": context_level,
            }
            if top_k > 1:
                row_metadata["predictions"] = meta_predictions
                row_metadata["parse_ok"] = meta_parse_ok
                row_metadata["parse_error"] = meta_parse_error
                row_metadata["all_candidate_names"] = all_candidate_names
                row_metadata["top_k"] = top_k

            row = {
                "experiment_id": experiment_id,
                "run_id": run_id,
                "job_id": jid,
                "timestamp": _ts(),
                "test_case": fn.get("test_case") or "",
                "opt": fn.get("opt") or opt,
                "dwarf_function_id": func_id,
                "ghidra_func_id": fn.get("ghidra_func_id"),
                "model": model,
                "prompt_template_id": prompt_template_id,
                "temperature": temperature,
                "prompt_text": prompt_text,
                "response_text": response_text,
                "prompt_tokens": llm_result["prompt_tokens"],
                "completion_tokens": llm_result["completion_tokens"],
                "total_tokens": llm_result["total_tokens"],
                "latency_ms": llm_result["latency_ms"],
                # predicted_name = top-1 from parsed response
                "predicted_name": predicted_name,
                # ground_truth_name left None — filled post-hoc by scorer
                "ground_truth_name": None,
                "metadata": row_metadata,
            }
            results.append(row)

        # Create tasks
        tasks = [_process_one(fn) for fn in todo]

        if _has_tqdm and async_tqdm is not None:
            # Use tqdm progress bar
            for coro in async_tqdm(  # type: ignore[misc]
                asyncio.as_completed(tasks),
                total=len(tasks),
                desc=f"LLM calls ({model})",
                unit="fn",
            ):
                await coro
        else:
            # Fallback: simple progress
            done = 0
            for coro in asyncio.as_completed(tasks):
                await coro
                done += 1
                if done % 10 == 0 or done == len(tasks):
                    print(f"  Progress: {done}/{len(tasks)}", flush=True)

        log.info("LLM calls complete: %d results, %d errors",
                 len(results), len(errors))

        # 7. POST results in batches
        written = 0
        for i in range(0, len(results), BATCH_POST_SIZE):
            batch = results[i : i + BATCH_POST_SIZE]
            try:
                resp = await _post_batch(client, api_base, batch)
                written += resp.get("rows_written", 0)
                log.info("Batch %d-%d: %d written, %d skipped",
                         i, i + len(batch),
                         resp.get("rows_written", 0),
                         resp.get("rows_skipped", 0))
            except Exception as exc:
                log.error("Batch POST failed at offset %d: %s", i, exc)
                errors.append({"batch_offset": i, "error": str(exc)})

        log.info("Total written: %d rows", written)

        # 8. Trigger scoring
        report = None
        if written > 0:
            try:
                score_resp = await _trigger_scoring(client, api_base, experiment_id)
                log.info("Scoring: %s", json.dumps(score_resp, indent=2)[:300])

                report_resp = await _fetch_report(client, api_base, experiment_id)
                report = report_resp
                log.info("Report generated for %s", experiment_id)
            except Exception as exc:
                log.warning("Scoring/report failed: %s", exc)

    summary = {
        "experiment_id": experiment_id,
        "run_id": run_id,
        "total": len(functions),
        "completed": len(completed_ids) + written,
        "skipped": skipped,
        "new": written,
        "errors": len(errors),
        "error_details": errors if errors else None,
        "dry_run": False,
        "report": report,
    }

    log.info("=== Run complete: %s ===", json.dumps({
        k: v for k, v in summary.items() if k != "report"
    }))

    return summary


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Run an LLM experiment against the Reforge API",
    )
    parser.add_argument("--experiment", required=True, help="Experiment ID")
    parser.add_argument("--api-base", default="http://localhost:8080", help="API base URL")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--run-id", default=None, help="Custom run ID (auto-generated if omitted)")
    parser.add_argument("--dry-run", action="store_true", help="Validate setup without calling LLM")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )

    summary = asyncio.run(run_experiment(
        args.experiment,
        api_base=args.api_base,
        concurrency=args.concurrency,
        run_id=args.run_id,
        dry_run=args.dry_run,
    ))

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for k, v in summary.items():
        if k == "report":
            continue
        print(f"  {k:20s}: {v}")

    if summary.get("errors", 0) > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
