"""
Writer — serialize join_dwarf_ts outputs to JSON files.

Filesystem layout:
    <output_dir>/alignment_pairs.json
    <output_dir>/alignment_report.json
"""
import json
from pathlib import Path

from join_dwarf_ts.io.schema import AlignmentPairsOutput, AlignmentReport


def write_outputs(
    pairs: AlignmentPairsOutput,
    report: AlignmentReport,
    output_dir: Path,
) -> Path:
    """
    Write alignment_pairs.json and alignment_report.json into *output_dir*.

    Creates *output_dir* if it does not exist.
    Returns the output directory path.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    pairs_path = output_dir / "alignment_pairs.json"
    report_path = output_dir / "alignment_report.json"

    pairs_path.write_text(
        json.dumps(
            pairs.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    report_path.write_text(
        json.dumps(
            report.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    return output_dir
