# llm

Async LLM experiment runner for function naming and source recovery tasks.

## Purpose

Drives end-to-end LLM experiments by fetching function data from the API, building prompts from templates, calling OpenRouter with async concurrency, and posting results back. Supports resumable runs and batch result submission.

## Usage

```bash
python -m workers.llm.runner \
    --experiment exp01_funcnaming_gpt4omini_gold_O0 \
    --api-base http://localhost:8080 \
    --concurrency 5
```

From Python:

```python
from workers.llm.runner import run_experiment

summary = await run_experiment(
    experiment_id="exp01_funcnaming_gpt4omini_gold_O0",
    api_base="http://localhost:8080",
)
```

## Components

- `runner.py` — Main experiment driver with async orchestration
- `model_router.py` — OpenRouter client with retry logic
- `prompt.py` — Prompt builder from templates
- `response_parser.py` — Parses LLM responses to extract predictions
- `prompt_templates/` — Jinja2 templates for function naming and recovery tasks
