"""
Writer — serialize analyzer outputs to JSON / JSONL files.

Filesystem layout per binary:
    <output_dir>/report.json
    <output_dir>/functions.jsonl
    <output_dir>/variables.jsonl
    <output_dir>/cfg.jsonl
    <output_dir>/calls.jsonl

JSONL files: one compact JSON object per line, sort_keys=True.
report.json: indented JSON with sort_keys=True.
"""
import json
from pathlib import Path
from typing import List

from analyzer_ghidra_decompile.io.schema import (
    GhidraCallEntry,
    GhidraCfgEntry,
    GhidraFunctionEntry,
    GhidraReport,
    GhidraVariableEntry,
)


def _write_jsonl(items: List, path: Path) -> None:
    """Write a list of Pydantic models as JSONL (one compact line per record)."""
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            if hasattr(item, "model_dump"):
                d = item.model_dump(mode="json")
            else:
                d = item
            f.write(json.dumps(d, sort_keys=True) + "\n")


def write_outputs(
    report: GhidraReport,
    functions: List[GhidraFunctionEntry],
    variables: List[GhidraVariableEntry],
    cfg: List[GhidraCfgEntry],
    calls: List[GhidraCallEntry],
    output_dir: Path,
) -> Path:
    """
    Write all five output files into *output_dir*.

    Creates *output_dir* if it does not exist.
    Returns the output directory path.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # report.json — indented
    report_path = output_dir / "report.json"
    report_path.write_text(
        json.dumps(
            report.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    # functions.jsonl — sorted by entry_va (already sorted by runner)
    _write_jsonl(functions, output_dir / "functions.jsonl")

    # variables.jsonl — sorted by (function_id, var_kind, storage_key)
    _write_jsonl(variables, output_dir / "variables.jsonl")

    # cfg.jsonl — sorted by entry_va
    _write_jsonl(cfg, output_dir / "cfg.jsonl")

    # calls.jsonl — sorted by (caller_entry_va, callsite_va)
    _write_jsonl(calls, output_dir / "calls.jsonl")

    return output_dir
