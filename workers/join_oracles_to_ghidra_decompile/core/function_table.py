"""
Function tables — build indexed lookup structures for DWARF and Ghidra
function inventories.

Stages 1 + 2 of the join pipeline.  Pure functions, no IO.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# Regex for goto token counting in decompiled C
_GOTO_RE = re.compile(r"\bgoto\b")

# Placeholder type patterns (Ghidra default "undefined" types)
_PLACEHOLDER_TYPE_RE = re.compile(r"^undefined\d*$", re.IGNORECASE)


# ═══════════════════════════════════════════════════════════════════════════════
# DWARF function table (Stage 1)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class DwarfFunctionRow:
    """Merged view of one DWARF function from oracle + alignment."""

    # Oracle identity
    function_id: str
    name: Optional[str] = None
    name_norm: Optional[str] = None       # lowered + stripped
    decl_file: Optional[str] = None
    decl_line: Optional[int] = None
    decl_column: Optional[int] = None
    oracle_verdict: str = ""
    oracle_reasons: List[str] = field(default_factory=list)

    # Address ranges (parsed to int)
    ranges: List[Tuple[int, int]] = field(default_factory=list)   # (low, high)
    total_range_bytes: int = 0
    has_range: bool = False

    # First range for convenience (populated when has_range is True)
    low_pc: Optional[int] = None
    high_pc: Optional[int] = None

    # Alignment evidence
    align_verdict: Optional[str] = None
    align_overlap_ratio: Optional[float] = None
    align_gap_count: Optional[int] = None
    align_n_candidates: Optional[int] = None
    quality_weight: float = 0.0
    align_reason_tags: List[str] = field(default_factory=list)
    is_non_target: bool = False

    # Eligibility classification (Phase 0 — set after table build)
    eligible_for_join: bool = True
    eligible_for_gold: bool = False
    exclusion_reason: Optional[str] = None


def _parse_ranges(raw_ranges: List[dict]) -> List[Tuple[int, int]]:
    """Convert oracle range dicts with hex strings to (int, int) tuples."""
    parsed: List[Tuple[int, int]] = []
    for r in raw_ranges:
        low_str = r.get("low", "0x0")
        high_str = r.get("high", "0x0")
        try:
            low = int(low_str, 16)
            high = int(high_str, 16)
            if high > low:
                parsed.append((low, high))
        except (ValueError, TypeError):
            log.warning("Unparsable range: low=%r high=%r", low_str, high_str)
    return parsed


def _normalize_name(name: Optional[str]) -> Optional[str]:
    """Lower-case + strip whitespace for normalized comparison."""
    if name is None:
        return None
    return name.strip().lower()


def build_dwarf_function_table(
    oracle_functions_data: dict,
    alignment_pairs_data: dict,
) -> Dict[str, DwarfFunctionRow]:
    """Build an indexed DWARF function table.

    Parameters
    ----------
    oracle_functions_data:
        Parsed ``oracle_functions.json`` dict (has ``functions`` list).
    alignment_pairs_data:
        Parsed ``alignment_pairs.json`` dict (has ``pairs`` + ``non_targets``).

    Returns
    -------
    Dict mapping ``function_id`` → ``DwarfFunctionRow``.
    """
    # ── Index alignment pairs by dwarf_function_id ────────────────────────
    align_idx: Dict[str, dict] = {}
    for pair in alignment_pairs_data.get("pairs", []):
        fid = pair.get("dwarf_function_id", "")
        if fid:
            align_idx[fid] = pair

    # ── Index non-targets ─────────────────────────────────────────────────
    non_target_ids: set = set()
    for nt in alignment_pairs_data.get("non_targets", []):
        fid = nt.get("dwarf_function_id", "")
        if fid:
            non_target_ids.add(fid)
            # Also store minimal alignment info
            align_idx.setdefault(fid, {
                "verdict": "NON_TARGET",
                "overlap_ratio": None,
                "gap_count": None,
                "candidates": [],
                "reasons": nt.get("dwarf_reasons", []),
            })

    # ── Build table ───────────────────────────────────────────────────────
    table: Dict[str, DwarfFunctionRow] = {}

    for func in oracle_functions_data.get("functions", []):
        fid = func.get("function_id", "")
        if not fid:
            continue

        # Parse ranges
        raw_ranges = func.get("ranges", [])
        ranges = _parse_ranges(raw_ranges)
        total_bytes = sum(h - l for l, h in ranges)
        has_range = len(ranges) > 0 and total_bytes > 0

        # First range
        low_pc = ranges[0][0] if ranges else None
        high_pc = ranges[0][1] if ranges else None

        # Look up alignment
        ap = align_idx.get(fid, {})
        align_verdict = ap.get("verdict")
        align_candidates = ap.get("candidates", [])
        align_n_candidates = len(align_candidates) if align_candidates else None
        align_overlap_ratio = ap.get("overlap_ratio")
        align_gap_count = ap.get("gap_count")
        align_reason_tags = list(ap.get("reasons", []))

        # quality_weight: overlap_ratio / n_candidates for MATCH, else 0
        qw = 0.0
        if (
            align_verdict == "MATCH"
            and align_n_candidates
            and align_n_candidates > 0
            and align_overlap_ratio is not None
        ):
            qw = align_overlap_ratio / align_n_candidates

        # Bounds assertion — catch upstream bugs deterministically.
        _QW_EPS = 1e-9
        if align_verdict == "MATCH" and qw != 0.0:
            if not (-_QW_EPS <= qw <= 1.0 + _QW_EPS):
                raise ValueError(
                    f"quality_weight out of [0, 1] bounds: {qw:.9f} "
                    f"(function_id={fid}, overlap_ratio={align_overlap_ratio}, "
                    f"n_candidates={align_n_candidates})"
                )
            qw = max(0.0, min(qw, 1.0))  # clamp within tolerance

        name = func.get("name") or func.get("linkage_name")

        row = DwarfFunctionRow(
            function_id=fid,
            name=name,
            name_norm=_normalize_name(name),
            decl_file=func.get("decl_file"),
            decl_line=func.get("decl_line"),
            decl_column=func.get("decl_column"),
            oracle_verdict=func.get("verdict", ""),
            oracle_reasons=list(func.get("reasons", [])),
            ranges=ranges,
            total_range_bytes=total_bytes,
            has_range=has_range,
            low_pc=low_pc,
            high_pc=high_pc,
            align_verdict=align_verdict,
            align_overlap_ratio=align_overlap_ratio,
            align_gap_count=align_gap_count,
            align_n_candidates=align_n_candidates,
            quality_weight=qw,
            align_reason_tags=align_reason_tags,
            # Only mark non-target when function actually HAS ranges.
            # Rangeless functions in alignment non_targets are NO_RANGE,
            # not policy NON_TARGET — eligibility checks has_range first.
            is_non_target=fid in non_target_ids and has_range,
        )
        table[fid] = row

    return table


# ═══════════════════════════════════════════════════════════════════════════════
# Ghidra function table (Stage 2)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class GhidraFunctionRow:
    """Merged view of one Ghidra function with derived metrics."""

    function_id: str
    entry_va: int
    entry_hex: str = ""
    name: str = ""
    namespace: Optional[str] = None

    body_start_va: Optional[int] = None
    body_end_va: Optional[int] = None
    size_bytes: Optional[int] = None
    has_body_range: bool = False

    is_external_block: bool = False
    is_thunk: bool = False
    is_import: bool = False
    is_plt_or_stub: bool = False
    is_init_fini_aux: bool = False
    is_compiler_aux: bool = False
    is_library_like: bool = False

    decompile_status: str = ""      # OK | FAIL
    verdict: str = ""               # OK | WARN | FAIL

    # Warning tags (normalized from analyzer)
    warnings: List[str] = field(default_factory=list)

    # Proxy metrics
    c_line_count: int = 0
    goto_count: int = 0
    goto_density: float = 0.0
    temp_var_count: int = 0
    asm_insn_count: int = 0
    insn_to_c_ratio: float = 0.0

    # Per-function variable stats
    total_vars_in_func: int = 0
    placeholder_type_rate: float = 0.0

    # CFG (merged from cfg.jsonl)
    bb_count: int = 0
    edge_count: int = 0
    cyclomatic: int = 0
    cfg_completeness: str = "HIGH"
    has_indirect_jumps: bool = False

    fat_function_flag: bool = False


@dataclass
class IntervalEntry:
    """Sorted entry for the Ghidra body-range interval index."""

    body_start: int
    body_end: int
    function_id: str


def build_ghidra_function_table(
    ghidra_functions: List[dict],
    ghidra_cfg: List[dict],
    ghidra_variables: List[dict],
    image_base: int = 0,
) -> Tuple[Dict[str, GhidraFunctionRow], List[IntervalEntry]]:
    """Build an indexed Ghidra function table + interval index.

    Parameters
    ----------
    ghidra_functions:
        Rows from ``functions.jsonl``.
    ghidra_cfg:
        Rows from ``cfg.jsonl``.
    ghidra_variables:
        Rows from ``variables.jsonl``.
    image_base:
        Ghidra image-base offset to subtract from all virtual addresses.
        For PIE (ET_DYN) binaries Ghidra typically loads at 0x100000;
        subtracting brings addresses back to raw ELF VAs used by DWARF.

    Returns
    -------
    (table, interval_index)
        table:  Dict mapping ``function_id`` → ``GhidraFunctionRow``.
        interval_index:  Sorted list of ``IntervalEntry`` for body-range queries.
    """
    if image_base:
        log.info("Rebasing Ghidra addresses: subtracting image_base=0x%x", image_base)
    # ── Pre-index CFG by function_id ──────────────────────────────────────
    cfg_idx: Dict[str, dict] = {}
    for c in ghidra_cfg:
        fid = c.get("function_id", "")
        if fid:
            cfg_idx[fid] = c

    # ── Pre-aggregate variable stats by function_id ───────────────────────
    var_stats: Dict[str, Dict[str, int]] = {}
    for v in ghidra_variables:
        fid = v.get("function_id", "")
        if not fid:
            continue
        st = var_stats.setdefault(fid, {"total": 0, "temp": 0, "placeholder": 0})
        st["total"] += 1
        if v.get("var_kind") == "TEMP":
            st["temp"] += 1
        type_str = v.get("type_str", "") or ""
        if _PLACEHOLDER_TYPE_RE.match(type_str):
            st["placeholder"] += 1

    # ── Build table ───────────────────────────────────────────────────────
    table: Dict[str, GhidraFunctionRow] = {}
    interval_index: List[IntervalEntry] = []

    for gf in ghidra_functions:
        fid = gf.get("function_id", "")
        if not fid:
            continue

        entry_va = gf.get("entry_va", 0) - image_base
        body_start = gf.get("body_start_va")
        body_end = gf.get("body_end_va")
        if body_start is not None:
            body_start -= image_base
        if body_end is not None:
            body_end -= image_base
        has_body = body_start is not None and body_end is not None

        # Goto count from decompiled C
        c_raw = gf.get("c_raw", "") or ""
        goto_count = len(_GOTO_RE.findall(c_raw))
        c_line_count = gf.get("c_line_count", 0)
        goto_density = goto_count / max(c_line_count, 1)

        # CFG merge
        cfg = cfg_idx.get(fid, {})

        # Variable stats
        vs = var_stats.get(fid, {"total": 0, "temp": 0, "placeholder": 0})
        total_vars = vs["total"]
        placeholder_rate = vs["placeholder"] / max(total_vars, 1)

        row = GhidraFunctionRow(
            function_id=fid,
            entry_va=entry_va,
            entry_hex=gf.get("entry_hex", ""),
            name=gf.get("name", ""),
            namespace=gf.get("namespace"),
            body_start_va=body_start,
            body_end_va=body_end,
            size_bytes=gf.get("size_bytes"),
            has_body_range=has_body,
            is_external_block=gf.get("is_external_block", False),
            is_thunk=gf.get("is_thunk", False),
            is_import=gf.get("is_import", False),
            is_plt_or_stub=gf.get("is_plt_or_stub", False),
            is_init_fini_aux=gf.get("is_init_fini_aux", False),
            is_compiler_aux=gf.get("is_compiler_aux", False),
            is_library_like=gf.get("is_library_like", False),
            decompile_status=gf.get("decompile_status", ""),
            verdict=gf.get("verdict", ""),
            warnings=list(gf.get("warnings", [])),
            c_line_count=c_line_count,
            goto_count=goto_count,
            goto_density=goto_density,
            temp_var_count=gf.get("temp_var_count", 0),
            asm_insn_count=gf.get("asm_insn_count", 0),
            insn_to_c_ratio=gf.get("insn_to_c_ratio", 0.0),
            total_vars_in_func=total_vars,
            placeholder_type_rate=placeholder_rate,
            bb_count=cfg.get("bb_count", 0),
            edge_count=cfg.get("edge_count", 0),
            cyclomatic=cfg.get("cyclomatic", 0),
            cfg_completeness=cfg.get("cfg_completeness", "HIGH"),
            has_indirect_jumps=cfg.get("has_indirect_jumps", False),
            fat_function_flag=gf.get("fat_function_flag", False),
        )
        table[fid] = row

        # Interval index — only functions with usable body ranges
        if has_body and body_start < body_end: #type: ignore
            interval_index.append(
                IntervalEntry(
                    body_start=body_start, #type: ignore
                    body_end=body_end, #type: ignore
                    function_id=fid,
                )
            )

    # Sort interval index by start address for efficient scanning
    interval_index.sort(key=lambda e: (e.body_start, e.body_end))

    log.info(
        "Ghidra function table: %d functions, %d with body ranges",
        len(table),
        len(interval_index),
    )
    return table, interval_index


# ═══════════════════════════════════════════════════════════════════════════════
# Eligibility stamping (Phase 0)
# ═══════════════════════════════════════════════════════════════════════════════

def apply_eligibility(
    dwarf_table: Dict[str, DwarfFunctionRow],
    aux_names: tuple | frozenset = (),
) -> Dict[str, int]:
    """Stamp ``eligible_for_join``, ``eligible_for_gold``, ``exclusion_reason``
    on every row in *dwarf_table* (mutates in-place).

    Returns a counter dict of exclusion reasons for reporting.
    """
    from join_oracles_to_ghidra_decompile.policy.eligibility import (
        classify_eligibility,
    )

    reason_counts: Dict[str, int] = {}

    for row in dwarf_table.values():
        ej, eg, reason = classify_eligibility(
            has_range=row.has_range,
            is_non_target=row.is_non_target,
            oracle_verdict=row.oracle_verdict,
            dwarf_name=row.name,
            aux_names=aux_names,
        )
        row.eligible_for_join = ej
        row.eligible_for_gold = eg
        row.exclusion_reason = reason

        if reason is not None:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

    n_ej = sum(1 for r in dwarf_table.values() if r.eligible_for_join)
    n_eg = sum(1 for r in dwarf_table.values() if r.eligible_for_gold)
    log.info(
        "Eligibility: %d total, %d eligible-for-join, %d eligible-for-gold",
        len(dwarf_table), n_ej, n_eg,
    )
    return reason_counts
