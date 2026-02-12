"""
Oracle runner — top-level orchestration: binary → report + functions.

This module ties core extraction, policy verdicts, and IO together
into a single ``run_oracle`` function that can be called from the
API endpoint or from a CLI.
"""
import logging
from pathlib import Path
from typing import Tuple

from oracle_dwarf.core.elf_reader import ElfMeta, read_elf
from oracle_dwarf.core.dwarf_loader import DwarfLoader
from oracle_dwarf.core.function_index import index_functions
from oracle_dwarf.core.line_mapper import compute_line_span, resolve_file_index
from oracle_dwarf.io.schema import (
    FunctionCounts,
    LineRowEntry,
    OracleFunctionEntry,
    OracleFunctionsOutput,
    OracleReport,
    RangeModel,
)
from oracle_dwarf.io.writer import write_outputs
from oracle_dwarf.policy.profile import Profile
from oracle_dwarf.policy.verdict import (
    BinaryRejectReason,
    Verdict,
    gate_binary,
    judge_function,
)

logger = logging.getLogger(__name__)


def run_oracle(
    binary_path: str,
    profile: Profile | None = None,
    output_dir: Path | None = None,
) -> Tuple[OracleReport, OracleFunctionsOutput]:
    """
    Run the DWARF oracle on a single binary.

    Parameters
    ----------
    binary_path : str
        Path to the ELF binary (should be a debug variant).
    profile : Profile, optional
        Support profile.  Defaults to Profile.v0().
    output_dir : Path, optional
        Directory to write JSON outputs.  If None, outputs are not
        written to disk (useful for API responses).

    Returns
    -------
    (OracleReport, OracleFunctionsOutput)
    """
    if profile is None:
        profile = Profile.v0()

    # ── Step 1: read ELF metadata ────────────────────────────────────
    try:
        meta = read_elf(binary_path)
    except Exception as e:
        # Cannot even open as ELF → binary-level REJECT
        report = OracleReport(
            profile_id=profile.profile_id,
            binary_path=binary_path,
            binary_sha256="",
            verdict=Verdict.REJECT.value,
            reasons=[BinaryRejectReason.DWARF_PARSE_ERROR.value],
        )
        functions = OracleFunctionsOutput(
            profile_id=profile.profile_id,
            binary_path=binary_path,
            binary_sha256="",
        )
        if output_dir:
            write_outputs(report, functions, output_dir)
        return report, functions

    # ── Step 2: binary-level gate ────────────────────────────────────
    binary_verdict, binary_reasons = gate_binary(meta, profile)

    if binary_verdict == Verdict.REJECT:
        report = OracleReport(
            profile_id=profile.profile_id,
            binary_path=binary_path,
            binary_sha256=meta.file_sha256,
            build_id=meta.build_id,
            verdict=binary_verdict.value,
            reasons=binary_reasons,
        )
        functions = OracleFunctionsOutput(
            profile_id=profile.profile_id,
            binary_path=binary_path,
            binary_sha256=meta.file_sha256,
        )
        if output_dir:
            write_outputs(report, functions, output_dir)
        return report, functions

    # ── Step 3: extract functions + line spans ───────────────────────
    func_entries: list[OracleFunctionEntry] = []
    counts = FunctionCounts()

    try:
        with DwarfLoader(binary_path) as loader:
            for cu_handle in loader.iter_cus():
                raw_funcs = index_functions(
                    cu_handle.cu, cu_handle.cu_offset, loader.dwarf
                )
                for fe in raw_funcs:
                    # compute line span
                    span = compute_line_span(
                        cu_handle.cu,
                        loader.dwarf,
                        cu_handle.comp_dir,
                        fe.ranges,
                    )

                    # apply policy
                    fv, freasons = judge_function(fe, span, profile)

                    # Build line_rows for ACCEPT/WARN (v0.2).
                    # REJECT functions have no ranges so line_rows stays empty.
                    func_line_rows: list[LineRowEntry] = []
                    func_file_row_counts: dict[str, int] = {}
                    if fv in (Verdict.ACCEPT, Verdict.WARN):
                        func_line_rows = sorted(
                            [
                                LineRowEntry(file=f, line=l, count=c)
                                for (f, l), c in span.line_rows.items()
                            ],
                            key=lambda r: (r.file, r.line),
                        )
                        func_file_row_counts = dict(
                            sorted(span.file_row_counts.items())
                        )

                    # Resolve decl_file from index (v0.3)
                    resolved_decl_file = None
                    decl_missing_reason = None
                    if fe.decl_file_index is not None:
                        resolved_decl_file = resolve_file_index(
                            fe.decl_file_index,
                            cu_handle.cu,
                            loader.dwarf,
                            cu_handle.comp_dir,
                        )
                        if resolved_decl_file is None:
                            decl_missing_reason = "FILE_INDEX_UNRESOLVABLE"
                    else:
                        decl_missing_reason = "NO_DECL_FILE_ATTR"

                    cu_id = f"cu{cu_handle.cu_offset:#x}"

                    entry = OracleFunctionEntry(
                        function_id=fe.function_id,
                        die_offset=hex(fe.die_offset),
                        cu_offset=hex(fe.cu_offset),
                        name=fe.name,
                        linkage_name=fe.linkage_name,
                        decl_file=resolved_decl_file,
                        decl_line=fe.decl_line,
                        decl_column=fe.decl_column,
                        comp_dir=cu_handle.comp_dir,
                        cu_id=cu_id,
                        decl_missing_reason=decl_missing_reason,
                        ranges=[
                            RangeModel(low=hex(r.low), high=hex(r.high))
                            for r in fe.ranges
                        ],
                        dominant_file=span.dominant_file,
                        dominant_file_ratio=span.dominant_file_ratio,
                        line_min=span.line_min,
                        line_max=span.line_max,
                        n_line_rows=span.n_line_rows,
                        line_rows=func_line_rows,
                        file_row_counts=func_file_row_counts,
                        verdict=fv.value,
                        reasons=freasons,
                    )
                    func_entries.append(entry)

                    counts.total += 1
                    if fv == Verdict.ACCEPT:
                        counts.accept += 1
                    elif fv == Verdict.WARN:
                        counts.warn += 1
                    else:
                        counts.reject += 1

    except Exception as e:
        logger.error("DWARF parse error on %s: %s", binary_path, e, exc_info=True)
        report = OracleReport(
            profile_id=profile.profile_id,
            binary_path=binary_path,
            binary_sha256=meta.file_sha256,
            build_id=meta.build_id,
            verdict=Verdict.REJECT.value,
            reasons=[BinaryRejectReason.DWARF_PARSE_ERROR.value],
        )
        functions = OracleFunctionsOutput(
            profile_id=profile.profile_id,
            binary_path=binary_path,
            binary_sha256=meta.file_sha256,
        )
        if output_dir:
            write_outputs(report, functions, output_dir)
        return report, functions

    # ── Step 4: assemble outputs ─────────────────────────────────────
    # Binary-level verdict is ACCEPT if gate passed; aggregate function
    # verdicts don't change the binary verdict (they're per-function).
    report = OracleReport(
        profile_id=profile.profile_id,
        binary_path=binary_path,
        binary_sha256=meta.file_sha256,
        build_id=meta.build_id,
        verdict=binary_verdict.value,
        reasons=binary_reasons,
        function_counts=counts,
    )

    functions = OracleFunctionsOutput(
        profile_id=profile.profile_id,
        binary_path=binary_path,
        binary_sha256=meta.file_sha256,
        functions=func_entries,
    )

    if output_dir:
        write_outputs(report, functions, output_dir)

    return report, functions
