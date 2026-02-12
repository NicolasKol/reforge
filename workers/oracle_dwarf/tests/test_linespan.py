"""
test_linespan — line program intersection and dominant file computation.

Tests verify invariant properties:
  - Every ACCEPT function has a non-empty line span (n_line_rows > 0).
  - line_min <= line_max for every function with a line span.
  - dominant_file_ratio is in (0, 1] for functions with line rows.
  - dominant_file is set for every ACCEPT function.
"""
from oracle_dwarf.runner import run_oracle


class TestLineSpan:
    """Line span invariants."""

    def test_accept_functions_have_line_rows(self, debug_binary_O0):
        """Every ACCEPT function must have at least one line row."""
        _, functions = run_oracle(str(debug_binary_O0))

        accepted = [f for f in functions.functions if f.verdict == "ACCEPT"]
        assert len(accepted) > 0

        for func in accepted:
            assert func.n_line_rows > 0, (
                f"ACCEPT function {func.name!r} has 0 line rows"
            )

    def test_line_min_le_line_max(self, debug_binary_O0):
        """line_min must be <= line_max when both are set."""
        _, functions = run_oracle(str(debug_binary_O0))

        for func in functions.functions:
            if func.line_min is not None and func.line_max is not None:
                assert func.line_min <= func.line_max, (
                    f"{func.name}: line_min={func.line_min} > line_max={func.line_max}"
                )

    def test_dominant_file_ratio_range(self, debug_binary_O0):
        """dominant_file_ratio must be in (0.0, 1.0] when rows exist."""
        _, functions = run_oracle(str(debug_binary_O0))

        for func in functions.functions:
            if func.n_line_rows > 0:
                assert 0.0 < func.dominant_file_ratio <= 1.0, (
                    f"{func.name}: bad ratio {func.dominant_file_ratio}"
                )

    def test_dominant_file_set_for_accept(self, debug_binary_O0):
        """ACCEPT functions must have dominant_file set."""
        _, functions = run_oracle(str(debug_binary_O0))

        accepted = [f for f in functions.functions if f.verdict == "ACCEPT"]
        for func in accepted:
            assert func.dominant_file is not None, (
                f"ACCEPT function {func.name!r} has no dominant_file"
            )

    def test_single_file_dominant(self, debug_binary_O0):
        """For a single-file program, dominant_file_ratio should be 1.0
        for user-defined functions."""
        _, functions = run_oracle(str(debug_binary_O0))

        user_funcs = [
            f for f in functions.functions
            if f.name in ("add", "multiply", "main") and f.verdict == "ACCEPT"
        ]
        for func in user_funcs:
            # Single-file source: all line rows should point to one file
            assert func.dominant_file_ratio == 1.0, (
                f"{func.name}: expected ratio 1.0, got {func.dominant_file_ratio}"
            )

    def test_output_schema_contract(self, debug_binary_O0):
        """Verify runtime contract fields are present in the report."""
        report, functions = run_oracle(str(debug_binary_O0))

        # Report contract
        assert report.package_name == "oracle_dwarf"
        assert report.oracle_version == "v0.1"
        assert report.schema_version == "0.3"
        assert report.profile_id == "linux-x86_64-gcc-O0O1O2O3"
        assert report.binary_sha256
        assert report.timestamp

        # Functions output contract
        assert functions.package_name == "oracle_dwarf"
        assert functions.oracle_version == "v0.1"
        assert functions.schema_version == "0.3"
        assert functions.binary_sha256 == report.binary_sha256

    # ── v0.2 line_rows tests ─────────────────────────────────────────

    def test_line_rows_populated_for_accept(self, debug_binary_O0):
        """ACCEPT functions must have non-empty line_rows list."""
        _, functions = run_oracle(str(debug_binary_O0))

        accepted = [f for f in functions.functions if f.verdict == "ACCEPT"]
        assert len(accepted) > 0

        for func in accepted:
            assert len(func.line_rows) > 0, (
                f"ACCEPT function {func.name!r} has empty line_rows"
            )

    def test_line_rows_empty_for_reject(self, debug_binary_O0):
        """REJECT functions must have empty line_rows."""
        _, functions = run_oracle(str(debug_binary_O0))

        rejected = [f for f in functions.functions if f.verdict == "REJECT"]
        for func in rejected:
            assert len(func.line_rows) == 0, (
                f"REJECT function {func.name!r} should have empty line_rows"
            )

    def test_line_rows_count_sum_equals_n_line_rows(self, debug_binary_O0):
        """sum(row.count) must equal n_line_rows for every function."""
        _, functions = run_oracle(str(debug_binary_O0))

        for func in functions.functions:
            row_sum = sum(r.count for r in func.line_rows)
            if func.verdict == "REJECT":
                assert row_sum == 0
            else:
                assert row_sum == func.n_line_rows, (
                    f"{func.name}: sum(line_rows.count)={row_sum} "
                    f"!= n_line_rows={func.n_line_rows}"
                )

    def test_file_row_counts_consistent(self, debug_binary_O0):
        """file_row_counts must match aggregated line_rows by file."""
        _, functions = run_oracle(str(debug_binary_O0))

        for func in functions.functions:
            if func.verdict == "REJECT":
                assert func.file_row_counts == {}
                continue

            # Aggregate line_rows by file
            from collections import Counter
            expected = Counter()
            for r in func.line_rows:
                expected[r.file] += r.count
            assert dict(expected) == func.file_row_counts, (
                f"{func.name}: file_row_counts mismatch"
            )

    def test_line_rows_sorted_deterministically(self, debug_binary_O0):
        """line_rows must be sorted by (file, line) for reproducibility."""
        _, functions = run_oracle(str(debug_binary_O0))

        for func in functions.functions:
            if len(func.line_rows) < 2:
                continue
            keys = [(r.file, r.line) for r in func.line_rows]
            assert keys == sorted(keys), (
                f"{func.name}: line_rows not sorted by (file, line)"
            )
