"""
Tests for join_dwarf_ts.io.loader — version validation and file loading.
"""
import json

import pytest

from join_dwarf_ts.io.loader import load_dwarf_outputs, load_ts_outputs


class TestDwarfVersionValidation:
    """load_dwarf_outputs() rejects schema versions below 0.2."""

    def _write_pair(self, tmp_path, report_sv, functions_sv):
        """Write a minimal oracle_dwarf report + functions file pair."""
        report = {
            "schema_version": report_sv,
            "binary_sha256": "abc",
            "build_id": "dead",
            "verdict": "ACCEPT",
        }
        functions = {
            "schema_version": functions_sv,
            "functions": [],
        }
        rp = tmp_path / "oracle_report.json"
        fp = tmp_path / "oracle_functions.json"
        rp.write_text(json.dumps(report), encoding="utf-8")
        fp.write_text(json.dumps(functions), encoding="utf-8")
        return rp, fp

    def test_valid_version_loads(self, tmp_path):
        rp, fp = self._write_pair(tmp_path, "0.2", "0.2")
        report, functions = load_dwarf_outputs(rp, fp)
        assert report["schema_version"] == "0.2"
        assert isinstance(functions, list)

    def test_higher_version_loads(self, tmp_path):
        rp, fp = self._write_pair(tmp_path, "0.3", "0.3")
        report, functions = load_dwarf_outputs(rp, fp)
        assert report["schema_version"] == "0.3"

    def test_report_below_minimum_raises(self, tmp_path):
        rp, fp = self._write_pair(tmp_path, "0.1", "0.2")
        with pytest.raises(ValueError, match="schema_version 0.1"):
            load_dwarf_outputs(rp, fp)

    def test_functions_below_minimum_raises(self, tmp_path):
        rp, fp = self._write_pair(tmp_path, "0.2", "0.1")
        with pytest.raises(ValueError, match="schema_version 0.1"):
            load_dwarf_outputs(rp, fp)


class TestTsVersionValidation:
    """load_ts_outputs() rejects schema versions below 0.1."""

    def _write_pair(self, tmp_path, report_sv, functions_sv):
        report = {
            "schema_version": report_sv,
            "profile_id": "ts-c-v0",
        }
        functions = {
            "schema_version": functions_sv,
            "functions": [],
        }
        rp = tmp_path / "oracle_ts_report.json"
        fp = tmp_path / "oracle_ts_functions.json"
        rp.write_text(json.dumps(report), encoding="utf-8")
        fp.write_text(json.dumps(functions), encoding="utf-8")
        return rp, fp

    def test_valid_version_loads(self, tmp_path):
        rp, fp = self._write_pair(tmp_path, "0.1", "0.1")
        report, functions = load_ts_outputs(rp, fp)
        assert report["schema_version"] == "0.1"

    def test_below_minimum_raises(self, tmp_path):
        rp, fp = self._write_pair(tmp_path, "0.0", "0.1")
        with pytest.raises(ValueError, match="schema_version 0.0"):
            load_ts_outputs(rp, fp)
