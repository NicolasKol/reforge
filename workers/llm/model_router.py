"""
Model-Aware Router for OpenRouter API
======================================

Different LLM providers have different API quirks when called through OpenRouter:

- **OpenAI** models: Full support for ``response_format``, ``json_object``, and ``json_schema``.
- **Anthropic** models: ``json_schema`` requires ``structured-outputs-2025-11-13`` beta header;
  ``json_object`` mode works via prompt instruction + provider routing.
- **DeepSeek** models: Newer models (v3+, R1) support ``json_object``; older ones do not.
  Reasoning models (R1) include ``<think>`` blocks that must be stripped.
- **Google Gemini** models: Support ``json_schema`` structured outputs natively.
- **Meta Llama** / **Qwen** / other open models: JSON support depends on the hosting
  provider; use ``require_parameters`` to ensure routing to capable backends.

This module provides :func:`call_llm`, a drop-in replacement for the old
``_call_openrouter`` that automatically adapts the request body, headers, and
response parsing based on the model being called.

Usage::

    from workers.llm.model_router import call_llm

    result = await call_llm(
        client, api_key, model="deepseek/deepseek-chat-v3-0324",
        prompt_text="...", temperature=0.0,
        response_format={"type": "json_object"},
    )
    # result: {"response_text": ..., "prompt_tokens": ..., ...}
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx

log = logging.getLogger(__name__)

OPENROUTER_BASE = "https://openrouter.ai/api/v1"


# ─── Provider detection ──────────────────────────────────────────────────────

class Provider(str, Enum):
    """Known model providers on OpenRouter."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"
    GOOGLE = "google"
    META = "meta-llama"
    QWEN = "qwen"
    MISTRAL = "mistralai"
    OTHER = "other"


def detect_provider(model: str) -> Provider:
    """Extract the provider from an OpenRouter model slug like 'openai/gpt-4o-mini'."""
    prefix = model.split("/")[0].lower() if "/" in model else ""
    for p in Provider:
        if p.value == prefix:
            return p
    return Provider.OTHER


# ─── Provider capability profiles ─────────────────────────────────────────────

@dataclass
class ProviderProfile:
    """Describes what a provider/model supports and how to adapt requests."""

    # Whether the model supports response_format: {"type": "json_object"}
    supports_json_mode: bool = True

    # Whether the model supports response_format: {"type": "json_schema", ...}
    supports_json_schema: bool = False

    # Whether the model is a reasoning/thinking model (e.g. DeepSeek R1, o1)
    # These may include <think>...</think> blocks in output
    is_reasoning_model: bool = False

    # Extra headers to include in the request
    extra_headers: Dict[str, str] = field(default_factory=dict)

    # Whether to add provider preferences to require parameter support
    require_parameters: bool = False

    # Whether to use a system message instead of user-only
    use_system_message: bool = False

    # Provider-specific body overrides
    body_overrides: Dict[str, Any] = field(default_factory=dict)

    # Notes for logging
    notes: str = ""


# ─── Model-specific profiles ─────────────────────────────────────────────────

# Patterns → profiles. Checked in order; first match wins.
# Pattern is matched against the full model slug (e.g. "deepseek/deepseek-r1").

_MODEL_PROFILES: List[tuple[str, ProviderProfile]] = [
    # ── OpenAI ────────────────────────────────────────────────────────────
    (r"openai/o[134]", ProviderProfile(
        supports_json_mode=True,
        supports_json_schema=True,
        is_reasoning_model=True,
        notes="OpenAI reasoning model (o-series)",
    )),
    (r"openai/", ProviderProfile(
        supports_json_mode=True,
        supports_json_schema=True,
        notes="OpenAI standard model — full JSON support",
    )),

    # ── Anthropic ─────────────────────────────────────────────────────────
    (r"anthropic/claude-opus-4", ProviderProfile(
        supports_json_mode=True,
        supports_json_schema=True,
        extra_headers={
            "x-anthropic-beta": "structured-outputs-2025-11-13",
        },
        notes="Claude Opus 4.x — structured outputs via beta header",
    )),
    (r"anthropic/claude-sonnet-4", ProviderProfile(
        supports_json_mode=True,
        supports_json_schema=True,
        extra_headers={
            "x-anthropic-beta": "structured-outputs-2025-11-13",
        },
        notes="Claude Sonnet 4.x — structured outputs via beta header",
    )),
    (r"anthropic/", ProviderProfile(
        supports_json_mode=True,
        supports_json_schema=False,
        notes="Anthropic older model — json_object via prompt instruction",
    )),

    # ── DeepSeek ──────────────────────────────────────────────────────────
    (r"deepseek/deepseek-r1", ProviderProfile(
        supports_json_mode=False,
        supports_json_schema=False,
        is_reasoning_model=True,
        notes="DeepSeek R1 — reasoning model, no native JSON mode; uses prompt-based JSON",
    )),
    (r"deepseek/deepseek-chat-v3|deepseek/deepseek-v3", ProviderProfile(
        supports_json_mode=True,
        supports_json_schema=False,
        require_parameters=True,
        notes="DeepSeek V3 — json_object supported via compatible providers",
    )),
    (r"deepseek/deepseek-coder", ProviderProfile(
        # DeepSeek Coder V2 is discontinued; this profile handles any
        # future coder models or leftover references.
        supports_json_mode=False,
        supports_json_schema=False,
        notes="DeepSeek Coder — likely discontinued; no JSON mode guarantee",
    )),
    (r"deepseek/", ProviderProfile(
        supports_json_mode=True,
        supports_json_schema=False,
        require_parameters=True,
        notes="DeepSeek model — json_object via require_parameters routing",
    )),

    # ── Google Gemini ─────────────────────────────────────────────────────
    (r"google/gemini", ProviderProfile(
        supports_json_mode=True,
        supports_json_schema=True,
        notes="Gemini — full structured output support",
    )),

    # ── Meta Llama ────────────────────────────────────────────────────────
    (r"meta-llama/", ProviderProfile(
        supports_json_mode=True,
        supports_json_schema=False,
        require_parameters=True,
        notes="Llama — json_object depends on provider; require_parameters ensures compatible routing",
    )),

    # ── Qwen ──────────────────────────────────────────────────────────────
    (r"qwen/", ProviderProfile(
        supports_json_mode=True,
        supports_json_schema=False,
        require_parameters=True,
        notes="Qwen — json_object via compatible providers",
    )),

    # ── Mistral ───────────────────────────────────────────────────────────
    (r"mistralai/", ProviderProfile(
        supports_json_mode=True,
        supports_json_schema=False,
        notes="Mistral — json_object mode supported",
    )),
]


def get_profile(model: str) -> ProviderProfile:
    """Return the best-matching capability profile for a model slug."""
    for pattern, profile in _MODEL_PROFILES:
        if re.search(pattern, model, re.IGNORECASE):
            return profile
    # Fallback: conservative defaults (no JSON mode, prompt-only)
    return ProviderProfile(
        supports_json_mode=False,
        supports_json_schema=False,
        notes="Unknown model — conservative fallback, no JSON mode",
    )


# ─── Thinking / reasoning model output cleaning ──────────────────────────────

_THINK_PATTERN = re.compile(
    r"<think>.*?</think>",
    re.DOTALL | re.IGNORECASE,
)


def strip_thinking_tags(text: str) -> str:
    """Remove ``<think>...</think>`` blocks from reasoning model output."""
    return _THINK_PATTERN.sub("", text).strip()


# ─── Core LLM caller ─────────────────────────────────────────────────────────

async def call_llm(
    client: httpx.AsyncClient,
    api_key: str,
    model: str,
    prompt_text: str,
    *,
    temperature: float = 0.0,
    max_tokens: Optional[int] = None,
    response_format: Optional[Dict[str, Any]] = None,
    timeout: float = 120.0,
) -> Dict[str, Any]:
    """Call an LLM through OpenRouter with model-aware parameter adaptation.

    This is the single call-point for all models. It:

    1. Detects the provider and loads capability profile
    2. Adapts ``response_format`` based on model support
    3. Adds provider routing preferences (``require_parameters``, etc.)
    4. Adds provider-specific headers (Anthropic beta, etc.)
    5. Strips reasoning tokens from thinking models
    6. Returns a uniform result dict

    Parameters
    ----------
    client : httpx.AsyncClient
        Shared HTTP client.
    api_key : str
        OpenRouter API key.
    model : str
        Full OpenRouter model slug (e.g. ``"openai/gpt-4o-mini"``).
    prompt_text : str
        The fully rendered prompt to send.
    temperature : float
        Sampling temperature.
    max_tokens : int | None
        Max completion tokens.
    response_format : dict | None
        Desired response format. Will be adapted or dropped based on model
        capabilities. Supported values:
        - ``{"type": "json_object"}``
        - ``{"type": "json_schema", "json_schema": {...}}``
    timeout : float
        Request timeout in seconds.

    Returns
    -------
    dict
        Keys: ``response_text``, ``prompt_tokens``, ``completion_tokens``,
        ``total_tokens``, ``latency_ms``, ``provider_used``, ``model_notes``.
    """
    profile = get_profile(model)
    provider = detect_provider(model)

    log.debug("Model %s → provider=%s, profile=%s", model, provider.value, profile.notes)

    # ── Build headers ─────────────────────────────────────────────────────
    headers: Dict[str, str] = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    headers.update(profile.extra_headers)

    # ── Build request body ────────────────────────────────────────────────
    body: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt_text}],
        "temperature": temperature,
    }

    if max_tokens is not None:
        body["max_tokens"] = max_tokens

    # ── Adapt response_format ─────────────────────────────────────────────
    actual_format = _adapt_response_format(response_format, profile, model)
    if actual_format is not None:
        body["response_format"] = actual_format

    # ── Provider preferences ──────────────────────────────────────────────
    provider_prefs: Dict[str, Any] = {}
    if actual_format is not None and profile.require_parameters:
        provider_prefs["require_parameters"] = True
    if provider_prefs:
        body["provider"] = provider_prefs

    # ── Apply body overrides ──────────────────────────────────────────────
    body.update(profile.body_overrides)

    # ── Make the call ─────────────────────────────────────────────────────
    t0 = time.perf_counter()
    resp = await client.post(
        f"{OPENROUTER_BASE}/chat/completions",
        headers=headers,
        json=body,
        timeout=timeout,
    )
    latency_ms = int((time.perf_counter() - t0) * 1000)

    if resp.status_code == 400:
        detail = resp.text[:500]
        log.error(
            "400 from OpenRouter for model=%s. Detail: %s\n"
            "Profile notes: %s\n"
            "Body keys sent: %s",
            model, detail, profile.notes, list(body.keys()),
        )
    resp.raise_for_status()

    data = resp.json()
    choice = data.get("choices", [{}])[0]
    usage = data.get("usage", {})
    raw_text = choice.get("message", {}).get("content", "").strip()

    # ── Clean reasoning model output ──────────────────────────────────────
    if profile.is_reasoning_model:
        cleaned = strip_thinking_tags(raw_text)
        if cleaned != raw_text:
            log.debug("Stripped thinking tags from %s response (%d → %d chars)",
                      model, len(raw_text), len(cleaned))
        raw_text = cleaned

    return {
        "response_text": raw_text,
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
        "latency_ms": latency_ms,
        "provider_used": provider.value,
        "model_notes": profile.notes,
    }


def _adapt_response_format(
    requested: Optional[Dict[str, Any]],
    profile: ProviderProfile,
    model: str,
) -> Optional[Dict[str, Any]]:
    """Downgrade or remove response_format based on model capabilities.

    Adaptation cascade:
    1. If model supports the requested format → pass through
    2. If json_schema requested but unsupported → downgrade to json_object
    3. If json_object requested but unsupported → remove (use prompt-only JSON)
    """
    if requested is None:
        return None

    fmt_type = requested.get("type", "")

    if fmt_type == "json_schema":
        if profile.supports_json_schema:
            log.debug("Model %s: using json_schema (native support)", model)
            return requested
        elif profile.supports_json_mode:
            log.info("Model %s: downgrading json_schema → json_object", model)
            return {"type": "json_object"}
        else:
            log.info("Model %s: dropping response_format (no JSON support); "
                     "relying on prompt instructions", model)
            return None

    if fmt_type == "json_object":
        if profile.supports_json_mode:
            log.debug("Model %s: using json_object mode", model)
            return requested
        else:
            log.info("Model %s: dropping json_object (unsupported); "
                     "relying on prompt instructions", model)
            return None

    # Unknown format type — pass through and hope for the best
    log.warning("Model %s: unknown response_format type '%s', passing through",
                model, fmt_type)
    return requested


# ─── Model availability checker ──────────────────────────────────────────────

async def check_model_available(
    client: httpx.AsyncClient,
    api_key: str,
    model: str,
) -> Dict[str, Any]:
    """Quick availability check for a model on OpenRouter.

    Returns
    -------
    dict
        Keys: ``available`` (bool), ``model``, ``name``, ``context_length``,
        ``pricing``, ``error`` (if not available).
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        resp = await client.get(
            f"{OPENROUTER_BASE}/models",
            headers=headers,
            timeout=15.0,
        )
        resp.raise_for_status()
        models_data = resp.json().get("data", [])

        for m in models_data:
            if m.get("id") == model:
                return {
                    "available": True,
                    "model": model,
                    "name": m.get("name", ""),
                    "context_length": m.get("context_length", 0),
                    "pricing": m.get("pricing", {}),
                }
        return {
            "available": False,
            "model": model,
            "error": f"Model '{model}' not found in OpenRouter model list",
        }
    except Exception as exc:
        return {
            "available": False,
            "model": model,
            "error": str(exc),
        }


async def list_available_models(
    client: httpx.AsyncClient,
    api_key: str,
    *,
    provider_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List all available models on OpenRouter, optionally filtered by provider.

    Returns
    -------
    list[dict]
        Each dict has: ``id``, ``name``, ``context_length``, ``pricing``,
        ``supported_parameters``.
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    resp = await client.get(
        f"{OPENROUTER_BASE}/models",
        headers=headers,
        timeout=15.0,
    )
    resp.raise_for_status()
    models = resp.json().get("data", [])

    if provider_filter:
        models = [m for m in models if m.get("id", "").startswith(provider_filter + "/")]

    return [
        {
            "id": m.get("id"),
            "name": m.get("name"),
            "context_length": m.get("context_length"),
            "pricing": m.get("pricing", {}),
        }
        for m in models
    ]
