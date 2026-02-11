"""
Oracle runner — top-level orchestration: .i files → report + functions + recipes.

This module ties core extraction, policy verdicts, and IO together
into a single ``run_oracle_ts`` function that can be called from the
API endpoint, from a CLI, or programmatically.
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from pathlib import Path
from typing import List, Optional, Tuple

from oracle_ts.core.function_index import TsFunctionEntry, index_functions
from oracle_ts.core.node_index import index_structural_nodes
from oracle_ts.core.ts_parser import ParseResult, parse_tu
from oracle_ts.io.schema import (
    ExtractionRecipe,
    ExtractionRecipesOutput,
    FunctionCounts,
    OracleTsFunctions,
    OracleTsReport,
    ParseErrorModel,
    SpanModel,
    TsFunctionEntryModel,
    TsStructuralNode,
    TuParseReport,
)
from oracle_ts.io.writer import write_outputs
from oracle_ts.policy.profile import TsProfile
from oracle_ts.policy.verdict import Verdict, gate_tu, judge_function

logger = logging.getLogger(__name__)


# ── Conversion helpers ───────────────────────────────────────────────────────

def _span_model(si) -> SpanModel:
    """Convert a core SpanInfo to a schema SpanModel."""
    return SpanModel(
        start_byte=si.start_byte,
        end_byte=si.end_byte,
        start_line=si.start_line,
        end_line=si.end_line,
    )


def _structural_to_model(sn) -> TsStructuralNode:
    return TsStructuralNode(
        node_type=sn.node_type,
        start_line=sn.start_line,
        end_line=sn.end_line,
        start_byte=sn.start_byte,
        end_byte=sn.end_byte,
        node_hash_raw=sn.node_hash_raw,
        depth=sn.depth,
        uncertainty_flags=list(sn.uncertainty_flags),
    )


# ── Public API ───────────────────────────────────────────────────────────────

def run_oracle_ts(
    i_paths: List[Path],
    profile: TsProfile | None = None,
    output_dir: Path | None = None,
) -> Tuple[OracleTsReport, OracleTsFunctions, ExtractionRecipesOutput]:
    """
    Run the tree-sitter source oracle on one or more .i files.

    Parameters
    ----------
    i_paths : List[Path]
        Paths to preprocessed C translation units.
    profile : TsProfile, optional
        Support profile. Defaults to TsProfile.v0().
    output_dir : Path, optional
        Directory to write JSON outputs. If None, outputs are not
        written to disk.

    Returns
    -------
    (OracleTsReport, OracleTsFunctions, ExtractionRecipesOutput)
    """
    if profile is None:
        profile = TsProfile.v0()

    report = OracleTsReport(profile_id=profile.profile_id)
    functions_out = OracleTsFunctions(profile_id=profile.profile_id)
    recipes_out = ExtractionRecipesOutput(profile_id=profile.profile_id)

    counts = FunctionCounts()

    for i_path in i_paths:
        logger.info("Parsing TU: %s", i_path)

        # ── Step 1: parse ────────────────────────────────────────────
        try:
            pr: ParseResult = parse_tu(i_path)
        except Exception as e:
            logger.error("Failed to read/parse %s: %s", i_path, e)
            report.tu_reports.append(TuParseReport(
                tu_path=str(i_path),
                tu_hash="",
                parser="",
                parse_status="ERROR",
                parse_errors=[ParseErrorModel(
                    line=0, column=0, message=str(e),
                )],
                verdict=Verdict.REJECT.value,
                reasons=["TU_PARSE_ERROR"],
            ))
            continue

        # ── Step 2: TU-level gate ────────────────────────────────────
        tu_verdict, tu_reasons = gate_tu(pr)

        tu_report = TuParseReport(
            tu_path=pr.tu_path,
            tu_hash=pr.tu_hash,
            parser=pr.parser_version,
            parse_status=pr.parse_status,
            parse_errors=[
                ParseErrorModel(line=e.line, column=e.column, message=e.message)
                for e in pr.parse_errors
            ],
            verdict=tu_verdict.value,
            reasons=tu_reasons,
        )
        report.tu_reports.append(tu_report)

        # If TU is fully rejected, skip function extraction
        if tu_verdict == Verdict.REJECT:
            continue

        # ── Step 3: extract functions ────────────────────────────────
        func_entries: List[TsFunctionEntry] = index_functions(pr)

        # Build duplicate-name set
        name_counts: Counter = Counter(
            fe.name for fe in func_entries if fe.name is not None
        )
        duplicate_names = {n for n, c in name_counts.items() if c > 1}

        # ── Step 4: per-function processing ──────────────────────────
        for fe in func_entries:
            # Find the corresponding tree-sitter node for structural
            # node indexing and verdict checks
            func_node = _find_func_node(pr.tree.root_node, fe.start_byte) #type: ignore

            # Index structural nodes
            struct_nodes = []
            if func_node is not None:
                struct_nodes = index_structural_nodes(
                    func_node,
                    pr.source_bytes,
                    deep_nesting_threshold=profile.deep_nesting_threshold,
                )

            # Judge function
            fv, freasons = judge_function(
                fe,
                duplicate_names,
                struct_nodes,
                func_node if func_node is not None else pr.tree.root_node, #type: ignore
                pr.source_bytes,
                profile,
            )
            fe.verdict = fv.value
            fe.reasons = freasons

            # Build schema model
            entry_model = TsFunctionEntryModel(
                name=fe.name,
                ts_func_id=fe.ts_func_id,
                span_id=fe.span_id,
                context_hash=fe.context_hash,
                node_hash_raw=fe.node_hash_raw,
                start_line=fe.start_line,
                end_line=fe.end_line,
                start_byte=fe.start_byte,
                end_byte=fe.end_byte,
                signature_span=_span_model(fe.signature_span),
                body_span=_span_model(fe.body_span),
                preamble_span=_span_model(fe.preamble_span),
                verdict=fe.verdict,
                reasons=fe.reasons,
                structural_nodes=[_structural_to_model(sn) for sn in struct_nodes],
            )
            functions_out.functions.append(entry_model)

            # Build extraction recipe
            recipe = ExtractionRecipe(
                function_name=fe.name,
                ts_func_id=fe.ts_func_id,
                tu_path=pr.tu_path,
                function_only=SpanModel(
                    start_byte=fe.start_byte,
                    end_byte=fe.end_byte,
                    start_line=fe.start_line,
                    end_line=fe.end_line,
                ),
                function_with_file_preamble=SpanModel(
                    start_byte=0,
                    end_byte=fe.end_byte,
                    start_line=0,
                    end_line=fe.end_line,
                ),
            )
            recipes_out.recipes.append(recipe)

            # Update counts
            counts.total += 1
            if fv == Verdict.ACCEPT:
                counts.accept += 1
            elif fv == Verdict.WARN:
                counts.warn += 1
            else:
                counts.reject += 1

    report.function_counts = counts

    # ── Write outputs ────────────────────────────────────────────────
    if output_dir:
        write_outputs(report, functions_out, recipes_out, output_dir)
        logger.info("Wrote oracle_ts outputs to %s", output_dir)

    return report, functions_out, recipes_out


# ── Helpers ──────────────────────────────────────────────────────────────────

def _find_func_node(root_node, start_byte: int):
    """
    Find the function_definition node at the given start_byte
    in the root's immediate children.
    """
    for child in root_node.children:
        if child.type == "function_definition" and child.start_byte == start_byte:
            return child
    return None


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    """CLI entry point for oracle_ts."""
    parser = argparse.ArgumentParser(
        description="oracle_ts — Tree-sitter source-structure oracle for preprocessed C",
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="Paths to .i files (preprocessed C translation units)",
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=Path,
        default=None,
        help="Directory to write JSON outputs",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    i_paths = [Path(p) for p in args.inputs]
    for p in i_paths:
        if not p.exists():
            logger.error("File not found: %s", p)
            sys.exit(1)

    report, functions, recipes = run_oracle_ts(
        i_paths=i_paths,
        output_dir=args.output_dir,
    )

    # Print summary
    print(f"TUs parsed: {len(report.tu_reports)}")
    print(f"Functions: {report.function_counts.total} "
          f"(accept={report.function_counts.accept}, "
          f"warn={report.function_counts.warn}, "
          f"reject={report.function_counts.reject})")
    print(f"Recipes: {len(recipes.recipes)}")

    if args.output_dir:
        print(f"Outputs written to: {args.output_dir}")


if __name__ == "__main__":
    main()
