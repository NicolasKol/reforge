"""
Writer — serialize oracle_ts outputs to JSON files.

Filesystem layout:
    <output_dir>/oracle_ts_report.json
    <output_dir>/oracle_ts_functions.json
    <output_dir>/extraction_recipes.json
"""
import json
from pathlib import Path

from oracle_ts.io.schema import (
    ExtractionRecipesOutput,
    OracleTsFunctions,
    OracleTsReport,
)


def write_outputs(
    report: OracleTsReport,
    functions: OracleTsFunctions,
    recipes: ExtractionRecipesOutput,
    output_dir: Path,
) -> Path:
    """
    Write oracle_ts JSON outputs into *output_dir*.

    Creates *output_dir* if it does not exist.
    Returns the output directory path.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    report_path = output_dir / "oracle_ts_report.json"
    funcs_path = output_dir / "oracle_ts_functions.json"
    recipes_path = output_dir / "extraction_recipes.json"

    report_path.write_text(
        json.dumps(
            report.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    funcs_path.write_text(
        json.dumps(
            functions.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    recipes_path.write_text(
        json.dumps(
            recipes.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    return output_dir
