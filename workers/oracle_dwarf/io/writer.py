"""
Writer — serialize oracle outputs to JSON files.

Filesystem layout per binary:
    <output_root>/<binary_stem>/oracle_report.json
    <output_root>/<binary_stem>/oracle_functions.json
"""
import json
from pathlib import Path

from oracle_dwarf.io.schema import OracleFunctionsOutput, OracleReport


def write_outputs(
    report: OracleReport,
    functions: OracleFunctionsOutput,
    output_dir: Path,
) -> Path:
    """
    Write oracle_report.json and oracle_functions.json into *output_dir*.

    Creates *output_dir* if it does not exist.
    Returns the output directory path.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    report_path = output_dir / "oracle_report.json"
    funcs_path = output_dir / "oracle_functions.json"

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

    return output_dir
