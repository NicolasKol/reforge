"""Integration tests for the full join pipeline."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from join_oracles_to_ghidra_decompile.io.loader import cross_validate_sha256
from join_oracles_to_ghidra_decompile.io.schema import (
    JoinedFunctionRow,
    JoinReport,
)
from join_oracles_to_ghidra_decompile.runner import run_join_oracles_ghidra
from join_oracles_to_ghidra_decompile.tests.conftest import TEST_SHA256


class TestIntegrationEndToEnd:
    """Full pipeline: fixtures → runner → verify outputs."""

    def test_runner_returns_correct_types(self, fixture_dirs):
        report, funcs, vars_ = run_join_oracles_ghidra(
            oracle_dir=fixture_dirs["oracle_dir"],
            alignment_dir=fixture_dirs["alignment_dir"],
            ghidra_dir=fixture_dirs["ghidra_dir"],
            receipt_path=fixture_dirs["receipt_path"],
            binary_sha256=TEST_SHA256,
        )
        assert isinstance(report, JoinReport)
        assert isinstance(funcs, list)
        assert all(isinstance(f, JoinedFunctionRow) for f in funcs)

    def test_runner_writes_outputs(self, fixture_dirs):
        report, funcs, vars_ = run_join_oracles_ghidra(
            oracle_dir=fixture_dirs["oracle_dir"],
            alignment_dir=fixture_dirs["alignment_dir"],
            ghidra_dir=fixture_dirs["ghidra_dir"],
            receipt_path=fixture_dirs["receipt_path"],
            binary_sha256=TEST_SHA256,
            output_dir=fixture_dirs["output_dir"],
        )
        out = fixture_dirs["output_dir"]
        assert (out / "join_report.json").exists()
        assert (out / "joined_functions.jsonl").exists()
        assert (out / "joined_variables.jsonl").exists()

    def test_sha256_in_all_rows(self, fixture_dirs):
        _, funcs, _ = run_join_oracles_ghidra(
            oracle_dir=fixture_dirs["oracle_dir"],
            alignment_dir=fixture_dirs["alignment_dir"],
            ghidra_dir=fixture_dirs["ghidra_dir"],
            receipt_path=fixture_dirs["receipt_path"],
            binary_sha256=TEST_SHA256,
        )
        for f in funcs:
            assert f.binary_sha256 == TEST_SHA256

    def test_all_dwarf_ids_present(self, fixture_dirs):
        _, funcs, _ = run_join_oracles_ghidra(
            oracle_dir=fixture_dirs["oracle_dir"],
            alignment_dir=fixture_dirs["alignment_dir"],
            ghidra_dir=fixture_dirs["ghidra_dir"],
            receipt_path=fixture_dirs["receipt_path"],
            binary_sha256=TEST_SHA256,
        )
        fids = {f.dwarf_function_id for f in funcs}
        assert fids == {"cu0:0x100", "cu0:0x200", "cu0:0x300", "cu0:0x400"}

    def test_joined_rows_reference_valid_ghidra(self, fixture_dirs, ghidra_functions):
        """Every JOINED row's ghidra_func_id must exist in the Ghidra table."""
        _, funcs, _ = run_join_oracles_ghidra(
            oracle_dir=fixture_dirs["oracle_dir"],
            alignment_dir=fixture_dirs["alignment_dir"],
            ghidra_dir=fixture_dirs["ghidra_dir"],
            receipt_path=fixture_dirs["receipt_path"],
            binary_sha256=TEST_SHA256,
        )
        ghidra_ids = {gf["function_id"] for gf in ghidra_functions}
        for f in funcs:
            if f.ghidra_match_kind.startswith("JOINED"):
                assert f.ghidra_func_id in ghidra_ids, (
                    f"ghidra_func_id {f.ghidra_func_id} not in Ghidra table"
                )


class TestDeterminism:
    """Determinism: run twice → identical outputs."""

    def test_deterministic_report(self, fixture_dirs):
        r1, f1, _ = run_join_oracles_ghidra(
            oracle_dir=fixture_dirs["oracle_dir"],
            alignment_dir=fixture_dirs["alignment_dir"],
            ghidra_dir=fixture_dirs["ghidra_dir"],
            receipt_path=fixture_dirs["receipt_path"],
            binary_sha256=TEST_SHA256,
        )
        r2, f2, _ = run_join_oracles_ghidra(
            oracle_dir=fixture_dirs["oracle_dir"],
            alignment_dir=fixture_dirs["alignment_dir"],
            ghidra_dir=fixture_dirs["ghidra_dir"],
            receipt_path=fixture_dirs["receipt_path"],
            binary_sha256=TEST_SHA256,
        )

        # Exclude timestamp from comparison
        d1 = r1.model_dump(mode="json")
        d2 = r2.model_dump(mode="json")
        d1.pop("timestamp", None)
        d2.pop("timestamp", None)
        assert d1 == d2

    def test_deterministic_rows(self, fixture_dirs):
        _, f1, _ = run_join_oracles_ghidra(
            oracle_dir=fixture_dirs["oracle_dir"],
            alignment_dir=fixture_dirs["alignment_dir"],
            ghidra_dir=fixture_dirs["ghidra_dir"],
            receipt_path=fixture_dirs["receipt_path"],
            binary_sha256=TEST_SHA256,
        )
        _, f2, _ = run_join_oracles_ghidra(
            oracle_dir=fixture_dirs["oracle_dir"],
            alignment_dir=fixture_dirs["alignment_dir"],
            ghidra_dir=fixture_dirs["ghidra_dir"],
            receipt_path=fixture_dirs["receipt_path"],
            binary_sha256=TEST_SHA256,
        )

        # Row order and content must be identical
        assert len(f1) == len(f2)
        for a, b in zip(f1, f2):
            assert a.model_dump(mode="json") == b.model_dump(mode="json")

    def test_deterministic_file_output(self, fixture_dirs, tmp_path):
        """Written files must be byte-identical across runs."""
        out1 = tmp_path / "run1"
        out2 = tmp_path / "run2"

        run_join_oracles_ghidra(
            oracle_dir=fixture_dirs["oracle_dir"],
            alignment_dir=fixture_dirs["alignment_dir"],
            ghidra_dir=fixture_dirs["ghidra_dir"],
            receipt_path=fixture_dirs["receipt_path"],
            binary_sha256=TEST_SHA256,
            output_dir=out1,
        )
        run_join_oracles_ghidra(
            oracle_dir=fixture_dirs["oracle_dir"],
            alignment_dir=fixture_dirs["alignment_dir"],
            ghidra_dir=fixture_dirs["ghidra_dir"],
            receipt_path=fixture_dirs["receipt_path"],
            binary_sha256=TEST_SHA256,
            output_dir=out2,
        )

        # joined_functions.jsonl must be byte-identical
        jf1 = (out1 / "joined_functions.jsonl").read_text(encoding="utf-8")
        jf2 = (out2 / "joined_functions.jsonl").read_text(encoding="utf-8")
        assert jf1 == jf2

        # join_report.json — compare without timestamp
        rpt1 = json.loads((out1 / "join_report.json").read_text(encoding="utf-8"))
        rpt2 = json.loads((out2 / "join_report.json").read_text(encoding="utf-8"))
        rpt1.pop("timestamp", None)
        rpt2.pop("timestamp", None)
        assert rpt1 == rpt2


class TestSha256Validation:
    """Cross-validation of binary_sha256 across sources."""

    def test_mismatch_raises(self, fixture_dirs):
        """Bogus SHA256 fails at receipt lookup (no matching build entry)."""
        with pytest.raises(ValueError, match="No build entry"):
            run_join_oracles_ghidra(
                oracle_dir=fixture_dirs["oracle_dir"],
                alignment_dir=fixture_dirs["alignment_dir"],
                ghidra_dir=fixture_dirs["ghidra_dir"],
                receipt_path=fixture_dirs["receipt_path"],
                binary_sha256="0000000000000000000000000000000000000000000000000000000000000000",
            )


class TestCrossValidateSha256:
    """Unit tests for cross_validate_sha256 (same-variant & cross-variant)."""

    def test_same_variant_all_match(self):
        """No error when all four SHAs agree (same-variant)."""
        cross_validate_sha256("aaa", "aaa", "aaa", "aaa")

    def test_same_variant_oracle_mismatch(self):
        with pytest.raises(ValueError, match="oracle="):
            cross_validate_sha256("bad", "aaa", "aaa", "aaa")

    def test_same_variant_ghidra_mismatch(self):
        with pytest.raises(ValueError, match="ghidra="):
            cross_validate_sha256("aaa", "aaa", "bad", "aaa")

    def test_cross_variant_ok(self):
        """No error when oracle group matches oracle SHA and ghidra matches ghidra SHA."""
        cross_validate_sha256(
            oracle_sha="oracle_sha",
            alignment_sha="oracle_sha",
            ghidra_sha="ghidra_sha",
            oracle_receipt_sha="oracle_sha",
            ghidra_receipt_sha="ghidra_sha",
        )

    def test_cross_variant_ghidra_mismatch(self):
        """Error when ghidra SHA doesn't match ghidra receipt SHA."""
        with pytest.raises(ValueError, match="ghidra="):
            cross_validate_sha256(
                oracle_sha="oracle_sha",
                alignment_sha="oracle_sha",
                ghidra_sha="wrong_sha",
                oracle_receipt_sha="oracle_sha",
                ghidra_receipt_sha="ghidra_sha",
            )

    def test_cross_variant_alignment_mismatch(self):
        """Error when alignment SHA doesn't match oracle receipt SHA."""
        with pytest.raises(ValueError, match="alignment="):
            cross_validate_sha256(
                oracle_sha="oracle_sha",
                alignment_sha="wrong_sha",
                ghidra_sha="ghidra_sha",
                oracle_receipt_sha="oracle_sha",
                ghidra_receipt_sha="ghidra_sha",
            )
