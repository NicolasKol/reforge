"""
test_functions — function enumeration and range normalization.

Tests verify invariant properties rather than exact values:
  - Every ACCEPT function has at least one non-empty address range.
  - Every ACCEPT function has a valid function_id.
  - Declaration-only subprograms are REJECT with DECLARATION_ONLY.
  - Known user-defined functions appear by name in the index.
"""
from oracle_dwarf.runner import run_oracle
from oracle_dwarf.policy.verdict import Verdict


class TestFunctionIndex:
    """Function enumeration invariants."""

    def test_user_functions_present(self, debug_binary_O0):
        """User-defined functions from MINIMAL_C must appear in the index."""
        report, functions = run_oracle(str(debug_binary_O0))

        assert report.verdict == "ACCEPT"
        names = {f.name for f in functions.functions if f.name is not None}

        # The source defines: add, multiply, main
        assert "add" in names
        assert "multiply" in names
        assert "main" in names

    def test_accept_functions_have_valid_ranges(self, debug_binary_O0):
        """Every ACCEPT function must have at least one [low, high) range
        where low < high."""
        _, functions = run_oracle(str(debug_binary_O0))

        accepted = [f for f in functions.functions if f.verdict == "ACCEPT"]
        assert len(accepted) > 0, "Expected at least one ACCEPT function"

        for func in accepted:
            assert len(func.ranges) >= 1, (
                f"ACCEPT function {func.name!r} has no ranges"
            )
            for r in func.ranges:
                low = int(r.low, 16)
                high = int(r.high, 16)
                assert high > low, (
                    f"Invalid range for {func.name}: [{r.low}, {r.high})"
                )

    def test_accept_functions_have_function_id(self, debug_binary_O0):
        """Every function entry must have a stable, non-empty function_id."""
        _, functions = run_oracle(str(debug_binary_O0))

        for func in functions.functions:
            assert func.function_id
            assert "cu" in func.function_id
            assert "die" in func.function_id

    def test_declaration_only_rejected(self, debug_binary_O0):
        """Declaration-only DIEs (if any) must be REJECT DECLARATION_ONLY."""
        _, functions = run_oracle(str(debug_binary_O0))

        decl_only = [
            f for f in functions.functions
            if "DECLARATION_ONLY" in f.reasons
        ]
        for f in decl_only:
            assert f.verdict == "REJECT"

    def test_no_duplicate_function_ids(self, debug_binary_O0):
        """Function IDs must be unique within a binary."""
        _, functions = run_oracle(str(debug_binary_O0))

        ids = [f.function_id for f in functions.functions]
        assert len(ids) == len(set(ids)), "Duplicate function_id detected"

    def test_o1_also_works(self, debug_binary_O1):
        """Oracle must also process O1 binaries without errors."""
        report, functions = run_oracle(str(debug_binary_O1))

        assert report.verdict == "ACCEPT"
        names = {f.name for f in functions.functions if f.name is not None}
        # main should still be present; add/multiply may be inlined at O1
        assert "main" in names

    def test_single_func_binary(self, single_func_binary):
        """Minimal two-function program: square and main."""
        _, functions = run_oracle(str(single_func_binary))

        names = {f.name for f in functions.functions if f.name is not None}
        assert "square" in names
        assert "main" in names
