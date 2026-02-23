"""Tests for data.llm_contract — whitelist/deny-list enforcement."""
from __future__ import annotations

import pytest

from data.llm_contract import (
    FORBIDDEN_KEYS,
    FORBIDDEN_PREFIXES,
    LLMInputRow,
    MetadataMode,
    audit_leakage_counts,
    sanitize_for_llm,
    scan_c_raw_for_gt_leak,
    validate_no_leakage,
)


# ── Fixture: a realistic raw row as returned by load_functions_with_decompiled
@pytest.fixture()
def full_raw_row() -> dict:
    """A FunctionDataRow-shaped dict with ALL fields, including forbidden."""
    return {
        # Identity (allowed)
        "dwarf_function_id": "func_001",
        "ghidra_func_id": "ghidra_001",
        "ghidra_entry_va": 0x00401000,
        # Ghidra artefacts (allowed)
        "c_raw": "int FUN_00401000(void) { return 42; }",
        "ghidra_name": "FUN_00401000",
        "decompile_status": "COMPLETE",
        "loc_decompiled": 3,
        "cyclomatic": 1,
        "bb_count": 1,
        # Context (allowed)
        "test_case": "t02",
        "opt": "O0",
        "variant": "stripped",
        # ── FORBIDDEN — ground-truth labels ──
        "dwarf_function_name": "calculate_sum",
        "dwarf_function_name_norm": "calculate_sum",
        # ── FORBIDDEN — source declaration ──
        "decl_file": "math.c",
        "decl_line": 42,
        "decl_column": 1,
        # ── FORBIDDEN — alignment / join provenance ──
        "confidence_tier": "GOLD",
        "quality_weight": 1.0,
        "is_high_confidence": True,
        "eligible_for_gold": True,
        "ghidra_match_kind": "JOINED_STRONG",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# validate_no_leakage
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidateNoLeakage:
    """validate_no_leakage must catch every forbidden key."""

    def test_catches_dwarf_name(self):
        payload = {"c_raw": "code", "dwarf_function_name": "secret"}
        assert "dwarf_function_name" in validate_no_leakage(payload)

    def test_catches_prefix_pattern(self):
        payload = {"c_raw": "code", "decl_foo_bar": "leak"}
        leaked = validate_no_leakage(payload)
        assert "decl_foo_bar" in leaked

    def test_clean_payload(self):
        payload = {"c_raw": "code", "ghidra_func_id": "g001"}
        assert validate_no_leakage(payload) == []

    def test_catches_all_explicit_keys(self, full_raw_row):
        """Every key in FORBIDDEN_KEYS that appears in the raw row is caught."""
        leaked = set(validate_no_leakage(full_raw_row))
        expected = FORBIDDEN_KEYS & set(full_raw_row.keys())
        assert expected <= leaked

    def test_future_field_regression(self):
        """A new field matching a forbidden prefix is caught even if not
        explicitly listed in FORBIDDEN_KEYS."""
        payload = {"dwarf_function_name_v2": "new_leak"}
        assert len(validate_no_leakage(payload)) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# sanitize_for_llm
# ═══════════════════════════════════════════════════════════════════════════════


class TestSanitizeForLLM:
    """sanitize_for_llm must strip forbidden fields and respect modes."""

    def test_strips_forbidden_keys(self, full_raw_row):
        result = sanitize_for_llm(full_raw_row, MetadataMode.STRICT)
        result_dict = result.model_dump()
        for key in FORBIDDEN_KEYS:
            assert key not in result_dict, f"forbidden key {key!r} survived"

    def test_preserves_whitelist(self, full_raw_row):
        result = sanitize_for_llm(full_raw_row, MetadataMode.STRICT)
        assert result.c_raw == full_raw_row["c_raw"]
        assert result.ghidra_func_id == full_raw_row["ghidra_func_id"]
        assert result.dwarf_function_id == full_raw_row["dwarf_function_id"]
        assert result.ghidra_name == full_raw_row["ghidra_name"]
        assert result.cyclomatic == full_raw_row["cyclomatic"]

    def test_mode_strict_no_arch_no_opt(self, full_raw_row):
        result = sanitize_for_llm(full_raw_row, MetadataMode.STRICT, arch="x86-64")
        assert result.arch is None
        assert result.opt is None

    def test_mode_analyst_has_arch_no_opt(self, full_raw_row):
        result = sanitize_for_llm(full_raw_row, MetadataMode.ANALYST, arch="x86-64")
        assert result.arch == "x86-64"
        assert result.opt is None

    def test_mode_analyst_full_has_both(self, full_raw_row):
        result = sanitize_for_llm(full_raw_row, MetadataMode.ANALYST_FULL, arch="x86-64")
        assert result.arch == "x86-64"
        assert result.opt == "O0"

    def test_pydantic_blocks_extra_fields(self):
        """LLMInputRow(extra='forbid') rejects undeclared fields."""
        with pytest.raises(Exception):
            LLMInputRow( #type: ignore
                dwarf_function_id="f1",
                c_raw="code",
                dwarf_function_name="SHOULD_FAIL", #type: ignore
            )

    def test_output_keys_are_subset_of_whitelist(self, full_raw_row):
        result = sanitize_for_llm(full_raw_row, MetadataMode.ANALYST_FULL, arch="x86-64")
        output_keys = set(result.model_dump(exclude_none=True).keys())
        allowed = set(LLMInputRow.model_fields.keys())
        assert output_keys <= allowed


# ═══════════════════════════════════════════════════════════════════════════════
# audit_leakage_counts
# ═══════════════════════════════════════════════════════════════════════════════


class TestAuditLeakageCounts:
    def test_counts_across_rows(self):
        rows = [
            {"dwarf_function_name": "a"},
            {"dwarf_function_name": "b", "decl_file": "c"},
            {"c_raw": "clean"},
        ]
        counts = audit_leakage_counts(rows)
        assert counts["dwarf_function_name"] == 2
        assert counts["decl_file"] == 1
        assert "c_raw" not in counts

    def test_empty_rows(self):
        assert audit_leakage_counts([]) == {}


# ═══════════════════════════════════════════════════════════════════════════════
# scan_c_raw_for_gt_leak
# ═══════════════════════════════════════════════════════════════════════════════


class TestScanCRawForGTLeak:
    def test_detects_name_in_code(self):
        c = 'void FUN_001(void) { printf("calculate_sum done"); }'
        assert scan_c_raw_for_gt_leak(c, "calculate_sum") is True

    def test_no_leak(self):
        c = "int FUN_001(void) { return 42; }"
        assert scan_c_raw_for_gt_leak(c, "calculate_sum") is False

    def test_short_name_ignored(self):
        c = "int add(int a, int b) { return a + b; }"
        # "add" is ≤4 chars → skip to avoid false positive
        assert scan_c_raw_for_gt_leak(c, "add") is False

    def test_empty_inputs(self):
        assert scan_c_raw_for_gt_leak("", "name") is False
        assert scan_c_raw_for_gt_leak("code", "") is False

    def test_case_insensitive(self):
        c = "void FUN_001(void) { CALCULATE_SUM(); }"
        assert scan_c_raw_for_gt_leak(c, "calculate_sum") is True
