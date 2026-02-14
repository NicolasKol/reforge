"""
Raw parser — parse the rich JSONL emitted by ExportDecompJsonl.java.

Responsibilities:
  - Read file line-by-line (one JSON object per line).
  - Separate function records (_type=function) from summary (_type=summary).
  - Validate minimum required fields; skip malformed lines with warning.
  - Return (RawSummary, List[RawFunctionRecord]).
"""
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Raw data containers ──────────────────────────────────────────────

@dataclass
class RawVariable:
    """Variable as emitted by the Java script."""
    name: str
    is_param: bool
    size_bytes: int
    type_str: Optional[str]
    storage_class: str
    storage_key: str
    stack_offset: Optional[int]
    register_name: Optional[str]
    addr_va: Optional[int]
    access_sites: List[int] = field(default_factory=list)
    access_sites_truncated: bool = False


@dataclass
class RawBlock:
    """Basic block as emitted by the Java script."""
    block_id: int
    start_va: int
    end_va: int
    succ_va: List[int] = field(default_factory=list)


@dataclass
class RawCall:
    """Callsite as emitted by the Java script."""
    callsite_va: int
    callsite_hex: str
    call_kind: str        # DIRECT | INDIRECT
    callee_entry_va: Optional[int]
    callee_name: Optional[str]
    is_external_target: bool
    is_import_proxy_target: bool


@dataclass
class RawFunctionRecord:
    """One function record from the raw JSONL."""
    entry_hex: str
    entry_va: int
    name: str
    namespace: Optional[str]
    is_external_block: bool
    is_thunk: bool
    is_import: bool
    body_start_va: Optional[int]
    body_end_va: Optional[int]
    size_bytes: Optional[int]
    section_hint: Optional[str]
    insn_count: int
    c_raw: Optional[str]
    error: Optional[str]
    warnings_raw: List[str] = field(default_factory=list)
    variables: List[RawVariable] = field(default_factory=list)
    blocks: List[RawBlock] = field(default_factory=list)
    calls: List[RawCall] = field(default_factory=list)


@dataclass
class RawSummary:
    """Summary trailer record from the raw JSONL."""
    ghidra_version: str = "unknown"
    java_version: str = "unknown"
    program_name: str = "unknown"
    program_arch: str = "unknown"
    total_functions: int = 0
    decompile_ok: int = 0
    decompile_fail: int = 0
    analysis_options: str = "default"
    image_base: Optional[int] = None  # Ghidra image base offset (PIE rebase)


# ── Parsing ──────────────────────────────────────────────────────────

def _parse_variable(d: Dict[str, Any]) -> RawVariable:
    """Parse a variable dict from the raw JSON."""
    # Defensive int() cast on stack_offset — JSON may deserialize as float
    raw_stack = d.get("stack_offset")
    stack_offset = int(raw_stack) if raw_stack is not None else None

    return RawVariable(
        name=d.get("name", ""),
        is_param=d.get("is_param", False),
        size_bytes=d.get("size_bytes", 0),
        type_str=d.get("type_str"),
        storage_class=d.get("storage_class", "UNKNOWN"),
        storage_key=d.get("storage_key", f"unk:{d.get('name', '')}"),
        stack_offset=stack_offset,
        register_name=d.get("register_name"),
        addr_va=d.get("addr_va"),
        access_sites=d.get("access_sites", []),
        access_sites_truncated=d.get("access_sites_truncated", False),
    )


def _parse_block(d: Dict[str, Any]) -> RawBlock:
    """Parse a basic block dict from the raw JSON."""
    return RawBlock(
        block_id=d.get("block_id", 0),
        start_va=d.get("start_va", 0),
        end_va=d.get("end_va", 0),
        succ_va=d.get("succ_va", []),
    )


def _parse_call(d: Dict[str, Any]) -> RawCall:
    """Parse a callsite dict from the raw JSON."""
    return RawCall(
        callsite_va=d.get("callsite_va", 0),
        callsite_hex=d.get("callsite_hex", "0x0"),
        call_kind=d.get("call_kind", "DIRECT"),
        callee_entry_va=d.get("callee_entry_va"),
        callee_name=d.get("callee_name"),
        is_external_target=d.get("is_external_target", False),
        is_import_proxy_target=d.get("is_import_proxy_target", False),
    )


def _parse_function(d: Dict[str, Any]) -> RawFunctionRecord:
    """Parse a function record dict from the raw JSON."""
    variables = [_parse_variable(v) for v in d.get("variables", [])]
    blocks = [_parse_block(b) for b in d.get("blocks", [])]
    calls = [_parse_call(c) for c in d.get("calls", [])]

    return RawFunctionRecord(
        entry_hex=d.get("entry_hex", "0x0"),
        entry_va=d.get("entry_va", 0),
        name=d.get("name", ""),
        namespace=d.get("namespace"),
        is_external_block=d.get("is_external_block", False),
        is_thunk=d.get("is_thunk", False),
        is_import=d.get("is_import", False),
        body_start_va=d.get("body_start_va"),
        body_end_va=d.get("body_end_va"),
        size_bytes=d.get("size_bytes"),
        section_hint=d.get("section_hint"),
        insn_count=d.get("insn_count", 0),
        c_raw=d.get("c_raw"),
        error=d.get("error"),
        warnings_raw=d.get("warnings_raw", []),
        variables=variables,
        blocks=blocks,
        calls=calls,
    )


def _parse_summary(d: Dict[str, Any]) -> RawSummary:
    """Parse the summary trailer record."""
    return RawSummary(
        ghidra_version=d.get("ghidra_version", "unknown"),
        java_version=d.get("java_version", "unknown"),
        program_name=d.get("program_name", "unknown"),
        program_arch=d.get("program_arch", "unknown"),
        total_functions=d.get("total_functions", 0),
        decompile_ok=d.get("decompile_ok", 0),
        decompile_fail=d.get("decompile_fail", 0),
        analysis_options=d.get("analysis_options", "default"),
        image_base=d.get("image_base"),
    )


def parse_raw_jsonl(
    path: str | Path,
) -> Tuple[RawSummary, List[RawFunctionRecord]]:
    """
    Parse the rich JSONL file emitted by ExportDecompJsonl.java.

    Returns
    -------
    (RawSummary, List[RawFunctionRecord])
        The summary trailer and list of function records.
        If no summary record is found, returns a default RawSummary.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Raw JSONL not found: {path}")

    functions: List[RawFunctionRecord] = []
    summary = RawSummary()
    line_num = 0

    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line_num += 1
            stripped = line.strip()
            if not stripped:
                continue

            try:
                d = json.loads(stripped)
            except json.JSONDecodeError as e:
                logger.warning(
                    "Malformed JSON at line %d in %s: %s", line_num, path, e
                )
                continue

            record_type = d.get("_type", "function")

            if record_type == "summary":
                summary = _parse_summary(d)
            elif record_type == "function":
                try:
                    func = _parse_function(d)
                    functions.append(func)
                except Exception as e:
                    logger.warning(
                        "Failed to parse function at line %d in %s: %s",
                        line_num, path, e,
                    )
            else:
                logger.warning(
                    "Unknown record type '%s' at line %d in %s",
                    record_type, line_num, path,
                )

    # Sort by entry_va ascending (determinism requirement §11)
    functions.sort(key=lambda fr: fr.entry_va)

    logger.info(
        "Parsed %d functions + summary from %s", len(functions), path
    )
    return summary, functions
