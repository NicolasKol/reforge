"""
Experiment Registry
Defines LLM experiment configurations as code, versioned alongside the project.

Each ExperimentConfig describes a fully reproducible experiment run:
- which model to call and with what parameters
- which data slice to evaluate on (tier, opt, test_case)
- which prompt template to use
- what context level (L0/L1/L2) controls structural Ghidra data

Experiments are registered in the REGISTRY dict below and served via
the ``/experiments`` API endpoints.  The Python LLM worker
(``workers.llm.runner``) fetches configs at runtime.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from data.llm_contract import MetadataMode


class ExperimentStatus(str, Enum):
    """Lifecycle state of an experiment definition."""
    DRAFT = "draft"          # Still being designed, not ready to run
    READY = "ready"          # Validated, ready for execution
    RUNNING = "running"      # Currently being executed (set at runtime)
    COMPLETED = "completed"  # Has results
    LEGACY = "legacy"        # Superseded by newer experiments


class ExperimentConfig(BaseModel):
    """A fully self-contained experiment configuration.

    Everything the LLM worker needs to execute an experiment is here —
    no hardcoded values.  The runner fetches this config and executes.
    """

    # ── Identity ──────────────────────────────────────────────────────────
    id: str = Field(..., description="Unique experiment identifier, e.g. exp01_funcnaming_gpt4omini_gold_O0")
    name: str = Field(..., description="Human-readable name")
    description: str = Field("", description="What this experiment tests")
    task: str = Field(..., description="Task type: function_naming | function_purpose | variable_naming | type_recovery")
    status: ExperimentStatus = Field(ExperimentStatus.DRAFT, description="Lifecycle state")
    tags: List[str] = Field(default_factory=list, description="Categorization tags")

    # ── Model Configuration ───────────────────────────────────────────────
    model: str = Field(..., description="OpenRouter model identifier, e.g. openai/gpt-4o-mini")
    temperature: float = Field(0.0, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: Optional[int] = Field(default=None, description="Max tokens in response (None = model default)")

    # ── Prompt Configuration ──────────────────────────────────────────────
    prompt_template_id: str = Field(..., description="Template name matching files in workers/llm/prompt_templates/")

    # ── Data Slice ────────────────────────────────────────────────────────
    tier: str = Field("GOLD", description="Confidence tier filter: GOLD, SILVER, BRONZE, or empty for all")
    opt: str = Field("O0", description="Optimization level: O0, O1, O2, O3")
    test_case: str = Field(default="", description="Specific test case (empty = all test cases)")
    limit: int = Field(0, ge=0, description="Max functions to process (0 = no limit)")

    # ── LLM Input Contract ────────────────────────────────────────────────
    metadata_mode: MetadataMode = Field(
        default=MetadataMode.STRICT,
        description=(
            "Controls which contextual metadata the LLM may see beyond c_raw. "
            "STRICT = c_raw only; ANALYST = + arch; ANALYST_FULL = + arch + opt"
        ),
    )

    # ── Context Level (v2) ────────────────────────────────────────────────
    context_level: str = Field(
        default="L0",
        description=(
            "Structural Ghidra context: "
            "L0 = code only; L1 = + calls; L2 = + calls + CFG + variables"
        ),
    )

    # ── Top-K Configuration (v2.1) ────────────────────────────────────────
    top_k: int = Field(
        default=1,
        ge=1,
        le=10,
        description=(
            "Number of candidate names the LLM should return. "
            "1 = single-name (legacy), 3 = top-k analyst shortlist."
        ),
    )
    response_format: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "OpenRouter response_format parameter (e.g. {'type': 'json_object'}). "
            "Set automatically when top_k > 1."
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Experiment Registry
# ═══════════════════════════════════════════════════════════════════════════════
#
# Add experiments here.  Each entry is immutable once results exist —
# create a new experiment ID for different parameters.
#

REGISTRY: Dict[str, ExperimentConfig] = {}


def _register(exp: ExperimentConfig) -> ExperimentConfig:
    """Add an experiment to the registry. Returns the config for chaining."""
    if exp.id in REGISTRY:
        raise ValueError(f"Duplicate experiment ID: {exp.id}")
    REGISTRY[exp.id] = exp
    return exp


# ─── Tier 1: Function Naming (LEGACY — pilot tests, v1 prompts) ──────────────

_register(ExperimentConfig(
    id="exp01_funcnaming_gpt4omini_gold_O0",
    name="Function Naming · GPT-4o-mini · GOLD · O0",
    description=(
        "Baseline function naming experiment. Uses GPT-4o-mini on GOLD-tier "
        "functions at O0 optimization. Establishes performance floor for the "
        "cheapest viable model on highest-confidence data."
    ),
    task="function_naming",
    status=ExperimentStatus.LEGACY,
    tags=["legacy", "pilot", "function-naming"],
    model="openai/gpt-4o-mini",
    temperature=0.0,
    prompt_template_id="function_naming_v1",
    tier="GOLD",
    opt="O0",
    limit=50,
))

_register(ExperimentConfig(
    id="exp02_funcnaming_gpt4o_gold_O0",
    name="Function Naming · GPT-4o · GOLD · O0",
    description=(
        "Function naming with GPT-4o on GOLD-tier at O0. Measures quality "
        "uplift of a more capable model vs the GPT-4o-mini baseline."
    ),
    task="function_naming",
    status=ExperimentStatus.LEGACY,
    tags=["legacy", "pilot", "function-naming"],
    model="openai/gpt-4o",
    temperature=0.0,
    prompt_template_id="function_naming_v1",
    tier="GOLD",
    opt="O0",
    limit=50,
))

_register(ExperimentConfig(
    id="exp03_funcnaming_claude_gold_O0",
    name="Function Naming · Claude 3.5 Sonnet · GOLD · O0",
    description=(
        "Function naming with Claude 3.5 Sonnet on GOLD-tier at O0. "
        "Cross-provider comparison alongside GPT-4o and GPT-4o-mini."
    ),
    task="function_naming",
    status=ExperimentStatus.LEGACY,
    tags=["legacy", "pilot", "function-naming"],
    model="anthropic/claude-3.5-sonnet",
    temperature=0.0,
    prompt_template_id="function_naming_v1",
    tier="GOLD",
    opt="O0",
    limit=50,
))

_register(ExperimentConfig(
    id="exp04_funcnaming_gpt4omini_gold_O2",
    name="Function Naming · GPT-4o-mini · GOLD · O2",
    description=(
        "Function naming with GPT-4o-mini on GOLD-tier at O2. Tests how "
        "optimization-level complexity degrades naming accuracy vs O0 baseline."
    ),
    task="function_naming",
    status=ExperimentStatus.LEGACY,
    tags=["legacy", "pilot", "function-naming"],
    model="openai/gpt-4o-mini",
    temperature=0.0,
    prompt_template_id="function_naming_v1",
    tier="GOLD",
    opt="O2",
    limit=50,
))

_register(ExperimentConfig(
    id="exp05_funcnaming_gpt4omini_silver_O0",
    name="Function Naming · GPT-4o-mini · SILVER · O0",
    description=(
        "Function naming with GPT-4o-mini on SILVER-tier at O0. Tests "
        "performance on lower-confidence ground truth (partial DWARF matches)."
    ),
    task="function_naming",
    status=ExperimentStatus.LEGACY,
    tags=["legacy", "pilot", "function-naming"],
    model="openai/gpt-4o-mini",
    temperature=0.0,
    prompt_template_id="function_naming_v1",
    tier="SILVER",
    opt="O0",
    limit=50,
))


# ─── Helper Functions ─────────────────────────────────────────────────────────

def list_experiments(
    *,
    task: Optional[str] = None,
    status: Optional[ExperimentStatus] = None,
    tag: Optional[str] = None,
) -> List[ExperimentConfig]:
    """Return experiments matching the given filters."""
    results = list(REGISTRY.values())
    if task:
        results = [e for e in results if e.task == task]
    if status:
        results = [e for e in results if e.status == status]
    if tag:
        results = [e for e in results if tag in e.tags]
    return results


def get_experiment(experiment_id: str) -> Optional[ExperimentConfig]:
    """Return a single experiment by ID, or None."""
    return REGISTRY.get(experiment_id)


# ═══════════════════════════════════════════════════════════════════════════════
# Benchmark v2 — Programmatic experiment matrix builder
# ═══════════════════════════════════════════════════════════════════════════════
#
# Models, tiers, opts, and context levels are specified here.
# The notebook calls ``build_benchmark_matrix()`` to generate and register
# all experiment configs dynamically.
#

# Canonical model catalog for the benchmark
# NOTE: Model availability on OpenRouter changes over time.
# Run `check_model_available()` or a dry-run before launching experiments.
BENCHMARK_MODELS: Dict[str, str] = {
    # label → OpenRouter model ID
    # ── OpenAI ────────────────────────────────────────────────────────────
    "gpt4o-mini":       "openai/gpt-4o-mini",
    "gpt4o":            "openai/gpt-4o",
    "gpt51":            "openai/gpt-5.1",
    "gpt51-codex-max":  "openai/gpt-5.1-codex-max",
    # ── Anthropic ─────────────────────────────────────────────────────────
    "claude-opus46":    "anthropic/claude-opus-4.6",
    "claude-sonnet45":  "anthropic/claude-sonnet-4.5",
    # ── DeepSeek (coder-v2 is DISCONTINUED — use v3+ models) ─────────────
    "deepseek-v3":      "deepseek/deepseek-chat-v3-0324",
    "deepseek-v32":     "deepseek/deepseek-v3.2",
    "deepseek-r1":      "deepseek/deepseek-r1-0528",
    # ── Google ────────────────────────────────────────────────────────────
    "gemini3-pro":      "google/gemini-3-pro-preview",
    # ── Meta / Open-source ────────────────────────────────────────────────
    "llama31-70b":      "meta-llama/llama-3.1-70b-instruct",
    "qwen3-coder":      "qwen/qwen3-coder",
}

BENCHMARK_TIERS = ["GOLD", "SILVER", "BRONZE"]
BENCHMARK_OPTS = ["O0", "O1", "O2", "O3"]
BENCHMARK_CONTEXT_LEVELS = ["L0", "L1", "L2"]

# Map context level → prompt template (single-name)
_CONTEXT_TEMPLATE: Dict[str, str] = {
    "L0": "function_naming_v2_L0",
    "L1": "function_naming_v2_L1",
    "L2": "function_naming_v2_L2",
}

# Map context level → prompt template (top-k JSON output)
_CONTEXT_TEMPLATE_TOPK: Dict[str, str] = {
    "L2": "function_naming_topk_L2",
}

# Thesis-specific model subset (instant, coding, thinking)
# NOTE: deepseek-coder-v2-0724 was discontinued on OpenRouter.
# Replaced with deepseek-chat-v3-0324 (V3 — strong coding, cheap).
THESIS_MODELS: Dict[str, str] = {
    "gpt4o-mini":    "openai/gpt-4o-mini",              
    "deepseek-v3":   "deepseek/deepseek-chat-v3-0324",
    "claude-sonnet45":  "anthropic/claude-sonnet-4.5", 
    "llama31-70b":      "meta-llama/llama-3.1-70b-instruct",
    "deepseek-r1":      "deepseek/deepseek-r1-0528",
    "qwen3-coder":      "qwen/qwen3-coder",
    "gpt51":         "openai/gpt-5.1",                 
}


def build_benchmark_matrix(
    *,
    models: Optional[Dict[str, str]] = None,
    tiers: Optional[List[str]] = None,
    opts: Optional[List[str]] = None,
    context_levels: Optional[List[str]] = None,
    top_k: int = 1,
    register: bool = True,
) -> List[ExperimentConfig]:
    """Generate the full experiment matrix for the benchmark.

    Parameters
    ----------
    models : dict[label, model_id]
        Model catalog. Defaults to ``BENCHMARK_MODELS``.
    tiers : list[str]
        Confidence tiers. Defaults to ``["GOLD", "SILVER", "BRONZE"]``.
    opts : list[str]
        Optimization levels. Defaults to ``["O0", "O1", "O2", "O3"]``.
    context_levels : list[str]
        Context levels. Defaults to ``["L0", "L1", "L2"]``.
    register : bool
        If True, register each experiment in the global REGISTRY.

    Returns
    -------
    list[ExperimentConfig]
        All generated experiment configs.
    """
    if models is None:
        models = BENCHMARK_MODELS
    if tiers is None:
        tiers = BENCHMARK_TIERS
    if opts is None:
        opts = BENCHMARK_OPTS
    if context_levels is None:
        context_levels = BENCHMARK_CONTEXT_LEVELS

    configs: List[ExperimentConfig] = []

    for model_label, model_id in models.items():
        for tier in tiers:
            for opt in opts:
                for ctx in context_levels:
                    # Deterministic experiment ID
                    topk_suffix = f"_topk{top_k}" if top_k > 1 else ""
                    exp_id = (
                        f"bench_{model_label}_{tier.lower()}"
                        f"_{opt}_{ctx}{topk_suffix}"
                    )

                    # Skip if already registered (idempotent)
                    if exp_id in REGISTRY:
                        configs.append(REGISTRY[exp_id])
                        continue

                    # Select prompt template: top-k JSON vs single-name
                    if top_k > 1 and ctx in _CONTEXT_TEMPLATE_TOPK:
                        tmpl = _CONTEXT_TEMPLATE_TOPK[ctx]
                        resp_fmt: Optional[Dict[str, Any]] = {"type": "json_object"}
                    else:
                        tmpl = _CONTEXT_TEMPLATE[ctx]
                        resp_fmt = None

                    exp = ExperimentConfig(
                        id=exp_id,
                        name=(
                            f"Bench · {model_label} · {tier} · "
                            f"{opt} · {ctx}"
                            + (f" · top{top_k}" if top_k > 1 else "")
                        ),
                        description=(
                            f"Benchmark: {model_label} on {tier}-tier "
                            f"at {opt}, context level {ctx}. "
                            + (f"Top-{top_k} JSON output. " if top_k > 1 else "")
                            + f"v2 prompt template, no function limit."
                        ),
                        task="function_naming",
                        status=ExperimentStatus.READY,
                        tags=["benchmark-v2", f"ctx-{ctx}",
                              f"tier-{tier.lower()}", f"opt-{opt}"]
                              + ([f"topk-{top_k}"] if top_k > 1 else []),
                        model=model_id,
                        temperature=0.0,
                        prompt_template_id=tmpl,
                        tier=tier,
                        opt=opt,
                        test_case="",   # all test cases
                        limit=0,        # no limit
                        metadata_mode=MetadataMode.STRICT,
                        context_level=ctx,
                        top_k=top_k,
                        response_format=resp_fmt,
                    )
                    if register:
                        _register(exp)
                    configs.append(exp)

    return configs


def build_thesis_matrix(
    *,
    register: bool = True,
) -> List[ExperimentConfig]:
    """Build the thesis-specific experiment matrix.

    Fixed configuration:
    - 3 models: gpt4o-mini (instant), deepseek-coder2 (coding), gpt51 (thinking)
    - 3 tiers: GOLD, SILVER, BRONZE
    - 4 opts: O0, O1, O2, O3
    - Context: L2 only
    - Top-k: 3 (JSON structured output)
    - Total: 3 × 3 × 4 = 36 experiments
    """
    return build_benchmark_matrix(
        models=THESIS_MODELS,
        tiers=["GOLD", "SILVER", "BRONZE"],
        opts=["O0", "O1", "O2", "O3"],
        context_levels=["L2"],
        top_k=3,
        register=register,
    )


def estimate_benchmark_cost(
    configs: List[ExperimentConfig],
    avg_prompt_tokens: int = 800,
    avg_completion_tokens: int = 20,
    functions_per_experiment: int = 300,
) -> Dict[str, Any]:
    """Rough cost estimate for a list of experiments.

    Uses OpenRouter pricing heuristics (as of 2025-01):

    - Cheap models (gpt-4o-mini, llama, deepseek-coder): ~$0.15/M input tokens
    - Mid models (gpt-4o, claude-3.5-sonnet, gemini-3-pro): ~$2.50/M input
    - Premium (gpt-5.1, claude-opus-4.6, codex-max): ~$10.00/M input

    Returns dict with total_calls, total_tokens, estimated_cost_usd, breakdown.
    """
    # Simplified pricing tiers (input $/M tokens)
    CHEAP = {"gpt-4o-mini", "llama-3.1-70b", "deepseek-chat-v3",
             "deepseek-v3", "deepseek-r1", "qwen3-coder", "deepseek-chat"}
    MID = {"gpt-4o", "claude-3.5-sonnet", "claude-sonnet-4.5", "gemini-3-pro"}
    # PREMIUM = everything else

    def _price_per_m(model_id: str) -> float:
        for tag in CHEAP:
            if tag in model_id:
                return 0.15
        for tag in MID:
            if tag in model_id:
                return 2.50
        return 10.00

    total_calls = 0
    total_input_tokens = 0
    total_cost = 0.0
    breakdown: List[Dict[str, Any]] = []

    for cfg in configs:
        n = functions_per_experiment
        inp = n * avg_prompt_tokens
        price = _price_per_m(cfg.model) * inp / 1_000_000
        total_calls += n
        total_input_tokens += inp
        total_cost += price
        breakdown.append({
            "experiment_id": cfg.id,
            "model": cfg.model,
            "calls": n,
            "est_cost_usd": round(price, 4),
        })

    return {
        "total_experiments": len(configs),
        "total_calls": total_calls,
        "total_input_tokens": total_input_tokens,
        "estimated_cost_usd": round(total_cost, 2),
        "breakdown": breakdown,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Auto-register thesis experiments at import time so they survive API restarts
# ═══════════════════════════════════════════════════════════════════════════════
build_thesis_matrix(register=True)
