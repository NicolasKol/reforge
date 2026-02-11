"""Tests for verdict logic."""
from pathlib import Path

from oracle_ts.core.function_index import index_functions
from oracle_ts.core.ts_parser import parse_tu
from oracle_ts.policy.verdict import Verdict, gate_tu
from oracle_ts.runner import run_oracle_ts


class TestGateTu:
    """Tests for TU-level gate."""

    def test_clean_tu_accepted(self, simple_i_file: Path):
        """Clean .i file gets TU-level ACCEPT."""
        pr = parse_tu(simple_i_file)
        verdict, reasons = gate_tu(pr)
        assert verdict == Verdict.ACCEPT
        assert reasons == []

    def test_error_tu_not_rejected_if_partial(self, parse_error_i_file: Path):
        """TU with errors but valid children gets WARN, not REJECT."""
        pr = parse_tu(parse_error_i_file)
        verdict, reasons = gate_tu(pr)
        # Should be WARN (partial parse) not REJECT
        assert verdict in (Verdict.WARN, Verdict.ACCEPT)


class TestFunctionVerdicts:
    """Integration tests for per-function verdicts via runner."""

    def test_simple_all_accept(self, simple_i_file: Path, tmp_path: Path):
        """Simple file — all functions get ACCEPT."""
        report, funcs, recipes = run_oracle_ts(
            [simple_i_file], output_dir=tmp_path / "out"
        )
        for f in funcs.functions:
            assert f.verdict == "ACCEPT", f"{f.name}: {f.reasons}"

    def test_duplicate_names_warn(self, duplicate_names_i_file: Path, tmp_path: Path):
        """Duplicate function names produce WARN with DUPLICATE_FUNCTION_NAME."""
        report, funcs, recipes = run_oracle_ts(
            [duplicate_names_i_file], output_dir=tmp_path / "out"
        )
        warned = [f for f in funcs.functions if "DUPLICATE_FUNCTION_NAME" in f.reasons]
        assert len(warned) >= 2  # both 'compute' functions

    def test_deep_nesting_warn(self, deep_nesting_i_file: Path, tmp_path: Path):
        """Deeply nested function produces WARN with DEEP_NESTING."""
        report, funcs, recipes = run_oracle_ts(
            [deep_nesting_i_file], output_dir=tmp_path / "out"
        )
        assert any("DEEP_NESTING" in f.reasons for f in funcs.functions)

    def test_anonymous_struct_warn(self, anonymous_struct_i_file: Path, tmp_path: Path):
        """Anonymous struct in function produces WARN."""
        report, funcs, recipes = run_oracle_ts(
            [anonymous_struct_i_file], output_dir=tmp_path / "out"
        )
        assert any("ANONYMOUS_AGGREGATE_PRESENT" in f.reasons for f in funcs.functions)

    def test_extension_warn(self, extension_i_file: Path, tmp_path: Path):
        """GCC __attribute__ produces NONSTANDARD_EXTENSION_PATTERN warn."""
        report, funcs, recipes = run_oracle_ts(
            [extension_i_file], output_dir=tmp_path / "out"
        )
        assert any("NONSTANDARD_EXTENSION_PATTERN" in f.reasons for f in funcs.functions)

    def test_output_files_written(self, simple_i_file: Path, tmp_path: Path):
        """JSON output files are created."""
        out = tmp_path / "output"
        run_oracle_ts([simple_i_file], output_dir=out)
        assert (out / "oracle_ts_report.json").exists()
        assert (out / "oracle_ts_functions.json").exists()
        assert (out / "extraction_recipes.json").exists()

    def test_recipe_count_matches_functions(self, simple_i_file: Path, tmp_path: Path):
        """One extraction recipe per function."""
        report, funcs, recipes = run_oracle_ts(
            [simple_i_file], output_dir=tmp_path / "out"
        )
        assert len(recipes.recipes) == len(funcs.functions)

    def test_function_counts(self, simple_i_file: Path):
        """Function counts are correct."""
        report, funcs, recipes = run_oracle_ts([simple_i_file])
        assert report.function_counts.total == 3
        assert report.function_counts.accept == 3
        assert report.function_counts.warn == 0
        assert report.function_counts.reject == 0

    def test_multi_tu(self, simple_i_file: Path, multi_func_i_file: Path):
        """Multiple TUs processed together."""
        report, funcs, recipes = run_oracle_ts(
            [simple_i_file, multi_func_i_file]
        )
        assert len(report.tu_reports) == 2
        assert report.function_counts.total == 6  # 3 + 3
