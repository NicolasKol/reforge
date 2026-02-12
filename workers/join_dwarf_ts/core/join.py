"""
Join orchestration — top-level join logic that ties origin maps,
candidate scoring, and verdict assignment together.

Operates on deserialized oracle outputs (Pydantic models) and .i file
content.  Produces alignment pairs and a summary report.
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Dict, List, Optional, Tuple

from join_dwarf_ts.core.candidate import (
    CandidateResult,
    TsFunctionInfo,
    detect_header_replication,
    score_candidates,
    select_best,
)
from join_dwarf_ts.core.origin_map import OriginMap, build_origin_map
from join_dwarf_ts.io.schema import (
    AlignmentPair,
    AlignmentPairsOutput,
    AlignmentReport,
    CandidateScoreModel,
    NonTargetEntry,
    PairCounts,
)
from join_dwarf_ts.policy.profile import JoinProfile
from join_dwarf_ts.policy.verdict import JoinVerdict

logger = logging.getLogger(__name__)


# ── Input data classes (from deserialized oracle JSONs) ──────────────────────

class DwarfFunctionInput:
    """Minimal DWARF function data needed for join."""

    __slots__ = (
        "function_id", "name", "verdict", "reasons",
        "line_rows", "n_line_rows",
        "decl_file", "decl_line", "decl_column", "comp_dir",
    )

    def __init__(
        self,
        function_id: str,
        name: Optional[str],
        verdict: str,
        reasons: List[str],
        line_rows: Dict[Tuple[str, int], int],
        n_line_rows: int,
        decl_file: Optional[str] = None,
        decl_line: Optional[int] = None,
        decl_column: Optional[int] = None,
        comp_dir: Optional[str] = None,
    ):
        self.function_id = function_id
        self.name = name
        self.verdict = verdict
        self.reasons = reasons
        self.line_rows = line_rows
        self.n_line_rows = n_line_rows
        self.decl_file = decl_file
        self.decl_line = decl_line
        self.decl_column = decl_column
        self.comp_dir = comp_dir


def _build_ts_function_map(
    ts_functions: List[dict],
) -> Dict[str, List[TsFunctionInfo]]:
    """Group TS functions by tu_path for efficient lookup."""
    by_tu: Dict[str, List[TsFunctionInfo]] = {}

    for f in ts_functions:
        # Determine tu_path from ts_func_id (format: tu_path:start:end:hash)
        ts_func_id = f["ts_func_id"]
        # tu_path is everything before the last three colon-separated fields
        parts = ts_func_id.rsplit(":", 3)
        tu_path = parts[0] if len(parts) == 4 else ""

        info = TsFunctionInfo(
            ts_func_id=ts_func_id,
            tu_path=tu_path,
            name=f.get("name"),
            context_hash=f.get("context_hash", ""),
            start_line=f["start_line"],
            end_line=f["end_line"],
            start_byte=f["start_byte"],
            end_byte=f["end_byte"],
        )

        if tu_path not in by_tu:
            by_tu[tu_path] = []
        by_tu[tu_path].append(info)

    return by_tu


def run_join(
    dwarf_functions: List[dict],
    dwarf_report: dict,
    ts_functions: List[dict],
    ts_report: dict,
    i_contents: Dict[str, str],
    profile: JoinProfile,
    build_receipt: Optional[dict] = None,
) -> Tuple[AlignmentPairsOutput, AlignmentReport]:
    """
    Execute the deterministic DWARF ↔ Tree-sitter join.

    Parameters
    ----------
    dwarf_functions : List[dict]
        Deserialized entries from oracle_functions.json.
    dwarf_report : dict
        Deserialized oracle_report.json.
    ts_functions : List[dict]
        Deserialized entries from oracle_ts_functions.json.
    ts_report : dict
        Deserialized oracle_ts_report.json.
    i_contents : Dict[str, str]
        Mapping of tu_path → .i file text content.
    profile : JoinProfile
        Join configuration (thresholds, excluded prefixes).
    build_receipt : dict, optional
        Deserialized build_receipt.json for provenance.

    Returns
    -------
    (AlignmentPairsOutput, AlignmentReport)
    """
    # ── Provenance anchors ───────────────────────────────────────────
    binary_sha256 = dwarf_report.get("binary_sha256", "")
    build_id = dwarf_report.get("build_id")

    tu_hashes: Dict[str, str] = {}
    for tu_rep in ts_report.get("tu_reports", []):
        tu_hashes[tu_rep["tu_path"]] = tu_rep["tu_hash"]

    # ── Build origin maps per TU ─────────────────────────────────────
    origin_maps: Dict[str, OriginMap] = {}
    origin_warnings: List[str] = []

    for tu_path, content in i_contents.items():
        om = build_origin_map(
            i_content=content,
            tu_path=tu_path,
            excluded_prefixes=profile.excluded_path_prefixes,
        )
        origin_maps[tu_path] = om
        if not om.origin_available:
            origin_warnings.append(tu_path)

    # ── Group TS functions by TU ─────────────────────────────────────
    ts_by_tu = _build_ts_function_map(ts_functions)

    # ── Reconcile i_contents keys with TS tu_paths ───────────────────
    # i_contents may use bare filenames ("arrays.i") while TS functions
    # reference full container paths ("/files/.../arrays.i").
    # Re-key origin_maps so lookups against ts_by_tu succeed.
    _resolved: Dict[str, OriginMap] = {}
    _i_basename_to_key: Dict[str, str] = {}
    for raw_key in origin_maps:
        basename = raw_key.rsplit("/", 1)[-1] if "/" in raw_key else raw_key
        _i_basename_to_key[basename] = raw_key

    for tu_path in ts_by_tu:
        if tu_path in origin_maps:
            # Direct key match (tests, or caller already aligned keys)
            _resolved[tu_path] = origin_maps[tu_path]
        else:
            # Basename fallback (production: "arrays.i" ↔ "/files/.../arrays.i")
            basename = tu_path.rsplit("/", 1)[-1] if "/" in tu_path else tu_path
            raw_key = _i_basename_to_key.get(basename)
            if raw_key is not None:
                _resolved[tu_path] = origin_maps[raw_key]
                logger.debug(
                    "resolved origin map key %r → %r (basename match)",
                    raw_key, tu_path,
                )

    # Keep unmatched origin maps (diagnostics / origin_warnings)
    _resolved_basenames = {
        k.rsplit("/", 1)[-1] if "/" in k else k for k in _resolved
    }
    for raw_key, om in origin_maps.items():
        basename = raw_key.rsplit("/", 1)[-1] if "/" in raw_key else raw_key
        if basename not in _resolved_basenames and raw_key not in _resolved:
            _resolved[raw_key] = om

    origin_maps = _resolved

    # ── Partition DWARF functions into targets vs non-targets ────────
    targets: List[DwarfFunctionInput] = []
    non_targets: List[NonTargetEntry] = []

    for df in dwarf_functions:
        verdict = df.get("verdict", "REJECT")
        if verdict in ("ACCEPT", "WARN"):
            # Build line_rows multiset
            lr: Dict[Tuple[str, int], int] = {}
            for row in df.get("line_rows", []):
                key = (row["file"], row["line"])
                lr[key] = lr.get(key, 0) + row["count"]

            targets.append(DwarfFunctionInput(
                function_id=df["function_id"],
                name=df.get("name"),
                verdict=verdict,
                reasons=df.get("reasons", []),
                line_rows=lr,
                n_line_rows=df.get("n_line_rows", 0),
                decl_file=df.get("decl_file"),
                decl_line=df.get("decl_line"),
                decl_column=df.get("decl_column"),
                comp_dir=df.get("comp_dir"),
            ))
        else:
            non_targets.append(NonTargetEntry(
                dwarf_function_id=df["function_id"],
                name=df.get("name"),
                dwarf_verdict=verdict,
                dwarf_reasons=df.get("reasons", []),
                decl_file=df.get("decl_file"),
                decl_line=df.get("decl_line"),
                decl_column=df.get("decl_column"),
                comp_dir=df.get("comp_dir"),
            ))

    # ── Join loop ────────────────────────────────────────────────────
    pairs: List[AlignmentPair] = []
    reason_counter: Counter = Counter()
    pair_counts = PairCounts()

    for dwarf_func in targets:
        # Collect candidates across all TUs
        all_candidates: List[CandidateResult] = []

        for tu_path, om in origin_maps.items():
            ts_funcs = ts_by_tu.get(tu_path, [])
            if not ts_funcs:
                continue

            tu_candidates = score_candidates(
                dwarf_evidence=dwarf_func.line_rows,
                ts_functions=ts_funcs,
                origin_map=om,
            )
            all_candidates.extend(tu_candidates)

        # Re-sort all candidates by tie-break order
        all_candidates.sort(key=lambda c: (
            -c.overlap_ratio,
            -c.overlap_count,
            c.span_size,
            c.tu_path,
            c.start_byte,
        ))

        # Select best and determine verdict
        best, near_ties, reasons = select_best(
            all_candidates,
            overlap_threshold=profile.overlap_threshold,
            epsilon=profile.epsilon,
            min_overlap_lines=profile.min_overlap_lines,
        )

        # Propagate MULTI_FILE_RANGE from DWARF
        if "MULTI_FILE_RANGE" in dwarf_func.reasons:
            reasons.append("MULTI_FILE_RANGE_PROPAGATED")

        # Check origin map availability
        if origin_warnings and best is None:
            reasons.append("ORIGIN_MAP_MISSING")

        # Header replication collision
        is_replication = False
        if best is not None and near_ties:
            is_replication = detect_header_replication(best, near_ties)
            if is_replication:
                reasons.append("HEADER_REPLICATION_COLLISION")

        # Determine final verdict
        if best is None or "NO_CANDIDATES" in reasons:
            join_verdict = JoinVerdict.NO_MATCH
        elif is_replication or (near_ties and "LOW_OVERLAP_RATIO" not in reasons):
            join_verdict = JoinVerdict.AMBIGUOUS
        elif "LOW_OVERLAP_RATIO" in reasons:
            join_verdict = JoinVerdict.NO_MATCH
        else:
            join_verdict = JoinVerdict.MATCH

        # Deduplicate reasons while preserving order
        seen_reasons = set()
        unique_reasons = []
        for r in reasons:
            if r not in seen_reasons:
                seen_reasons.add(r)
                unique_reasons.append(r)

        # Build candidate models for transparency
        candidate_models = [
            CandidateScoreModel(
                ts_func_id=c.ts_func_id,
                tu_path=c.tu_path,
                function_name=c.function_name,
                context_hash=c.context_hash,
                overlap_count=c.overlap_count,
                overlap_ratio=c.overlap_ratio,
                gap_count=c.gap_count,
            )
            for c in all_candidates
        ]

        pair = AlignmentPair(
            dwarf_function_id=dwarf_func.function_id,
            dwarf_function_name=dwarf_func.name,
            dwarf_verdict=dwarf_func.verdict,
            decl_file=dwarf_func.decl_file,
            decl_line=dwarf_func.decl_line,
            decl_column=dwarf_func.decl_column,
            comp_dir=dwarf_func.comp_dir,
            best_ts_func_id=best.ts_func_id if best else None,
            best_tu_path=best.tu_path if best else None,
            best_ts_function_name=best.function_name if best else None,
            overlap_count=best.overlap_count if best else 0,
            total_count=best.total_count if best else sum(dwarf_func.line_rows.values()),
            overlap_ratio=best.overlap_ratio if best else 0.0,
            gap_count=best.gap_count if best else sum(dwarf_func.line_rows.values()),
            verdict=join_verdict.value,
            reasons=unique_reasons,
            candidates=candidate_models,
        )
        pairs.append(pair)

        # Update counts
        if join_verdict == JoinVerdict.MATCH:
            pair_counts.match += 1
        elif join_verdict == JoinVerdict.AMBIGUOUS:
            pair_counts.ambiguous += 1
        else:
            pair_counts.no_match += 1

        for r in unique_reasons:
            reason_counter[r] += 1

    pair_counts.non_target = len(non_targets)

    # ── Assemble outputs ─────────────────────────────────────────────
    pairs_output = AlignmentPairsOutput(
        binary_sha256=binary_sha256,
        build_id=build_id,
        dwarf_profile_id=dwarf_report.get("profile_id", ""),
        ts_profile_id=ts_report.get("profile_id", ""),
        pairs=pairs,
        non_targets=non_targets,
    )

    report = AlignmentReport(
        binary_sha256=binary_sha256,
        build_id=build_id,
        dwarf_profile_id=dwarf_report.get("profile_id", ""),
        ts_profile_id=ts_report.get("profile_id", ""),
        tu_hashes=dict(sorted(tu_hashes.items())),
        pair_counts=pair_counts,
        reason_counts=dict(sorted(reason_counter.items())),
        thresholds={
            "overlap_threshold": profile.overlap_threshold,
            "epsilon": profile.epsilon,
            "min_overlap_lines": profile.min_overlap_lines,
        },
        excluded_path_prefixes=list(profile.excluded_path_prefixes),
    )

    return pairs_output, report
