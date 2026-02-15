"""
Tests for join_dwarf_ts.core.join — end-to-end join orchestration.

Uses fixtures from conftest.py.
"""
from join_dwarf_ts.core.join import run_join
from join_dwarf_ts.io.schema import AlignmentPairsOutput, AlignmentReport
from join_dwarf_ts.policy.profile import JoinProfile
from join_dwarf_ts.policy.verdict import JoinVerdict


class TestRunJoin:
    """Integration tests for the full join pipeline."""

    def test_basic_join_produces_output_types(
        self, dwarf_functions, dwarf_report, ts_functions, ts_report, i_contents
    ):
        profile = JoinProfile.v0()
        pairs_out, report = run_join(
            dwarf_functions=dwarf_functions,
            dwarf_report=dwarf_report,
            ts_functions=ts_functions,
            ts_report=ts_report,
            i_contents=i_contents,
            profile=profile,
        )
        assert isinstance(pairs_out, AlignmentPairsOutput)
        assert isinstance(report, AlignmentReport)

    def test_pair_count_equals_targets(
        self, dwarf_functions, dwarf_report, ts_functions, ts_report, i_contents
    ):
        profile = JoinProfile.v0()
        pairs_out, report = run_join(
            dwarf_functions=dwarf_functions,
            dwarf_report=dwarf_report,
            ts_functions=ts_functions,
            ts_report=ts_report,
            i_contents=i_contents,
            profile=profile,
        )
        # All 3 DWARF functions are ACCEPT → 3 pairs
        assert len(pairs_out.pairs) == 3
        assert len(pairs_out.non_targets) == 0

    def test_non_targets_populated(
        self, dwarf_functions_with_reject, dwarf_report,
        ts_functions, ts_report, i_contents
    ):
        profile = JoinProfile.v0()
        pairs_out, report = run_join(
            dwarf_functions=dwarf_functions_with_reject,
            dwarf_report=dwarf_report,
            ts_functions=ts_functions,
            ts_report=ts_report,
            i_contents=i_contents,
            profile=profile,
        )
        assert len(pairs_out.pairs) == 3  # 3 ACCEPT targets
        assert len(pairs_out.non_targets) == 1
        assert pairs_out.non_targets[0].dwarf_verdict == "REJECT"

    def test_pair_counts_consistent(
        self, dwarf_functions, dwarf_report, ts_functions, ts_report, i_contents
    ):
        profile = JoinProfile.v0()
        _, report = run_join(
            dwarf_functions=dwarf_functions,
            dwarf_report=dwarf_report,
            ts_functions=ts_functions,
            ts_report=ts_report,
            i_contents=i_contents,
            profile=profile,
        )
        counts = report.pair_counts
        assert (
            counts.match + counts.ambiguous + counts.no_match
            == len(dwarf_functions)
        )

    def test_provenance_anchors(
        self, dwarf_functions, dwarf_report, ts_functions, ts_report, i_contents
    ):
        profile = JoinProfile.v0()
        pairs_out, report = run_join(
            dwarf_functions=dwarf_functions,
            dwarf_report=dwarf_report,
            ts_functions=ts_functions,
            ts_report=ts_report,
            i_contents=i_contents,
            profile=profile,
        )
        assert pairs_out.binary_sha256 == "abc123"
        assert pairs_out.build_id == "deadbeef"
        assert report.binary_sha256 == "abc123"
        assert report.dwarf_profile_id == "linux-x86_64-gcc-O0O1"
        assert report.ts_profile_id == "ts-c-v0"

    def test_tu_hashes_in_report(
        self, dwarf_functions, dwarf_report, ts_functions, ts_report, i_contents
    ):
        profile = JoinProfile.v0()
        _, report = run_join(
            dwarf_functions=dwarf_functions,
            dwarf_report=dwarf_report,
            ts_functions=ts_functions,
            ts_report=ts_report,
            i_contents=i_contents,
            profile=profile,
        )
        assert "simple.c.i" in report.tu_hashes
        assert report.tu_hashes["simple.c.i"] == "sha256:aaa111"

    def test_contract_fields(
        self, dwarf_functions, dwarf_report, ts_functions, ts_report, i_contents
    ):
        profile = JoinProfile.v0()
        pairs_out, report = run_join(
            dwarf_functions=dwarf_functions,
            dwarf_report=dwarf_report,
            ts_functions=ts_functions,
            ts_report=ts_report,
            i_contents=i_contents,
            profile=profile,
        )
        assert pairs_out.package_name == "join_dwarf_ts"
        assert pairs_out.joiner_version == "v0"
        assert pairs_out.schema_version == "0.2"
        assert report.package_name == "join_dwarf_ts"

    def test_every_pair_has_verdict(
        self, dwarf_functions, dwarf_report, ts_functions, ts_report, i_contents
    ):
        profile = JoinProfile.v0()
        pairs_out, _ = run_join(
            dwarf_functions=dwarf_functions,
            dwarf_report=dwarf_report,
            ts_functions=ts_functions,
            ts_report=ts_report,
            i_contents=i_contents,
            profile=profile,
        )
        valid_verdicts = {v.value for v in JoinVerdict}
        for pair in pairs_out.pairs:
            assert pair.verdict in valid_verdicts, (
                f"pair {pair.dwarf_function_id} has invalid verdict: {pair.verdict}"
            )

    def test_deterministic_output(
        self, dwarf_functions, dwarf_report, ts_functions, ts_report, i_contents
    ):
        """Running twice produces byte-identical outputs."""
        profile = JoinProfile.v0()
        pairs1, report1 = run_join(
            dwarf_functions=dwarf_functions,
            dwarf_report=dwarf_report,
            ts_functions=ts_functions,
            ts_report=ts_report,
            i_contents=i_contents,
            profile=profile,
        )
        pairs2, report2 = run_join(
            dwarf_functions=dwarf_functions,
            dwarf_report=dwarf_report,
            ts_functions=ts_functions,
            ts_report=ts_report,
            i_contents=i_contents,
            profile=profile,
        )
        # Compare model dumps (timestamp is the only non-deterministic field)
        d1 = pairs1.model_dump(mode="json")
        d2 = pairs2.model_dump(mode="json")
        assert d1 == d2

    def test_empty_i_contents_gives_no_match(
        self, dwarf_functions, dwarf_report, ts_functions, ts_report
    ):
        """No .i files → all targets should be NO_MATCH."""
        profile = JoinProfile.v0()
        pairs_out, report = run_join(
            dwarf_functions=dwarf_functions,
            dwarf_report=dwarf_report,
            ts_functions=ts_functions,
            ts_report=ts_report,
            i_contents={},  # empty
            profile=profile,
        )
        for pair in pairs_out.pairs:
            assert pair.verdict == JoinVerdict.NO_MATCH.value

    def test_thresholds_in_report(
        self, dwarf_functions, dwarf_report, ts_functions, ts_report, i_contents
    ):
        profile = JoinProfile.v0()
        _, report = run_join(
            dwarf_functions=dwarf_functions,
            dwarf_report=dwarf_report,
            ts_functions=ts_functions,
            ts_report=ts_report,
            i_contents=i_contents,
            profile=profile,
        )
        assert report.thresholds["overlap_threshold"] == 0.7
        assert report.thresholds["epsilon"] == 0.02
        assert "/usr/include" in report.excluded_path_prefixes

    def test_basename_key_reconciliation(
        self, dwarf_functions, dwarf_report, ts_report, i_contents
    ):
        """Bare-filename i_contents keys match full-path TS tu_paths.

        Regression test: load_i_files uses bare filenames ('simple.c.i')
        while ts_func_id encodes full container paths.  The join must
        reconcile by basename so candidates are actually scored.
        """
        # TS functions reference a full container path for tu_path
        full_path = "/files/artifacts/project/preprocess/simple.c.i"
        ts_functions_full = [
            {
                "ts_func_id": f"{full_path}:5:8:hash_add",
                "name": "add",
                "context_hash": "ctx_add",
                "start_line": 5,
                "end_line": 8,
                "start_byte": 80,
                "end_byte": 140,
                "verdict": "ACCEPT",
            },
            {
                "ts_func_id": f"{full_path}:11:13:hash_mul",
                "name": "multiply",
                "context_hash": "ctx_mul",
                "start_line": 11,
                "end_line": 13,
                "start_byte": 150,
                "end_byte": 200,
                "verdict": "ACCEPT",
            },
            {
                "ts_func_id": f"{full_path}:16:19:hash_main",
                "name": "main",
                "context_hash": "ctx_main",
                "start_line": 16,
                "end_line": 19,
                "start_byte": 210,
                "end_byte": 300,
                "verdict": "ACCEPT",
            },
        ]
        ts_report_full = dict(ts_report)
        ts_report_full["tu_reports"] = [
            {"tu_path": full_path, "tu_hash": "sha256:aaa111", "function_count": 3}
        ]

        profile = JoinProfile.v0()
        # i_contents uses bare "simple.c.i" key (as load_i_files does)
        pairs_out, report = run_join(
            dwarf_functions=dwarf_functions,
            dwarf_report=dwarf_report,
            ts_functions=ts_functions_full,
            ts_report=ts_report_full,
            i_contents=i_contents,  # {"simple.c.i": ...}
            profile=profile,
        )

        # Without reconciliation every pair would be NO_CANDIDATES.
        # With reconciliation at least one pair should have candidates.
        has_candidates = any(len(p.candidates) > 0 for p in pairs_out.pairs)
        assert has_candidates, (
            "No candidates found — basename key reconciliation failed"
        )
        match_count = sum(
            1 for p in pairs_out.pairs if p.verdict == JoinVerdict.MATCH.value
        )
        assert match_count > 0, "Expected at least one MATCH verdict"

    def test_multi_tu_candidate_aggregation(
        self, dwarf_report, ts_report
    ):
        """Candidates from two TUs are merged, sorted, and tie-detected."""
        import textwrap

        # Two .i files both include a header with the same function
        i_a = textwrap.dedent("""\
            # 1 "shared.h"
            int helper(int x) {
                return x + 1;
            }
            # 5 "a.c"
            int fa(void) { return helper(1); }
        """)
        i_b = textwrap.dedent("""\
            # 1 "shared.h"
            int helper(int x) {
                return x + 1;
            }
            # 5 "b.c"
            int fb(void) { return helper(2); }
        """)

        # DWARF function points at shared.h lines 1-3
        dwarf_functions = [{
            "function_id": "0x100:0x0-0x20",
            "name": "helper",
            "verdict": "ACCEPT",
            "reasons": [],
            "n_line_rows": 3,
            "line_rows": [
                {"file": "shared.h", "line": 1, "count": 1},
                {"file": "shared.h", "line": 2, "count": 1},
                {"file": "shared.h", "line": 3, "count": 1},
            ],
        }]

        # TS functions in both TUs covering the replicated header code
        ts_functions = [
            {
                "ts_func_id": "a.c.i:1:3:hash_helper",
                "name": "helper",
                "context_hash": "SAME_HASH",
                "start_line": 1, "end_line": 3,
                "start_byte": 0, "end_byte": 50,
                "verdict": "ACCEPT",
            },
            {
                "ts_func_id": "b.c.i:1:3:hash_helper",
                "name": "helper",
                "context_hash": "SAME_HASH",
                "start_line": 1, "end_line": 3,
                "start_byte": 0, "end_byte": 50,
                "verdict": "ACCEPT",
            },
        ]

        ts_report_multi = dict(ts_report)
        ts_report_multi["tu_reports"] = [
            {"tu_path": "a.c.i", "tu_hash": "sha256:aaa", "function_count": 1},
            {"tu_path": "b.c.i", "tu_hash": "sha256:bbb", "function_count": 1},
        ]

        profile = JoinProfile.v0()
        pairs_out, report = run_join(
            dwarf_functions=dwarf_functions,
            dwarf_report=dwarf_report,
            ts_functions=ts_functions,
            ts_report=ts_report_multi,
            i_contents={"a.c.i": i_a, "b.c.i": i_b},
            profile=profile,
        )

        pair = pairs_out.pairs[0]
        # Both TUs contribute candidates
        assert len(pair.candidates) == 2
        # Header replication should be detected → AMBIGUOUS
        assert pair.verdict == JoinVerdict.AMBIGUOUS.value
        assert "HEADER_REPLICATION_COLLISION" in pair.reasons

    def test_multi_file_range_propagated(
        self, dwarf_report, ts_functions, ts_report, i_contents
    ):
        """MULTI_FILE_RANGE in DWARF reasons → MULTI_FILE_RANGE_PROPAGATED."""
        dwarf_functions = [{
            "function_id": "0x1000:0x0-0x20",
            "name": "add",
            "verdict": "WARN",
            "reasons": ["MULTI_FILE_RANGE"],
            "dominant_file": "simple.c",
            "dominant_file_ratio": 1.0,
            "n_line_rows": 4,
            "line_rows": [
                {"file": "simple.c", "line": 3, "count": 1},
                {"file": "simple.c", "line": 4, "count": 2},
                {"file": "simple.c", "line": 5, "count": 1},
            ],
        }]

        profile = JoinProfile.v0()
        pairs_out, report = run_join(
            dwarf_functions=dwarf_functions,
            dwarf_report=dwarf_report,
            ts_functions=ts_functions,
            ts_report=ts_report,
            i_contents=i_contents,
            profile=profile,
        )

        pair = pairs_out.pairs[0]
        assert "MULTI_FILE_RANGE_PROPAGATED" in pair.reasons
