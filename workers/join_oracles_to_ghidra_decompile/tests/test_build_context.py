"""Tests for core.build_context — Stage 0."""
from __future__ import annotations

import pytest

from join_oracles_to_ghidra_decompile.core.build_context import (
    BuildContext,
    resolve_build_context,
)
from join_oracles_to_ghidra_decompile.io.loader import (
    resolve_target_build_entry,
)
from join_oracles_to_ghidra_decompile.tests.conftest import TEST_SHA256


class TestResolveBuildEntry:
    """Test receipt → build entry resolution."""

    def test_finds_matching_entry(self, build_receipt):
        entry = resolve_target_build_entry(build_receipt, TEST_SHA256)
        assert entry["optimization"] == "O0"
        assert entry["variant"] == "stripped"
        assert entry["artifact"]["sha256"] == TEST_SHA256

    def test_raises_on_missing_sha(self, build_receipt):
        with pytest.raises(ValueError, match="No build entry"):
            resolve_target_build_entry(build_receipt, "no_such_sha")

    def test_finds_second_entry(self, build_receipt):
        sha_o3 = "f" * 64
        entry = resolve_target_build_entry(build_receipt, sha_o3)
        assert entry["optimization"] == "O3"


class TestResolveContext:
    """Test BuildContext construction."""

    def test_context_fields(self, build_receipt):
        entry = resolve_target_build_entry(build_receipt, TEST_SHA256)
        ctx = resolve_build_context(build_receipt, entry, TEST_SHA256)

        assert isinstance(ctx, BuildContext)
        assert ctx.binary_sha256 == TEST_SHA256
        assert ctx.job_id == "job-42"
        assert ctx.test_case == "math_recurse"
        assert ctx.opt == "O0"
        assert ctx.variant == "stripped"
        assert ctx.builder_profile_id == "gcc-O0O1O2O3"
        assert ctx.ghidra_binary_sha256 is None
        assert ctx.ghidra_variant is None

    def test_cross_variant_context(self, build_receipt):
        entry = resolve_target_build_entry(build_receipt, TEST_SHA256)
        ghidra_sha = "f" * 64
        ctx = resolve_build_context(
            build_receipt, entry, TEST_SHA256,
            ghidra_binary_sha256=ghidra_sha,
            ghidra_variant="debug",
        )
        assert ctx.binary_sha256 == TEST_SHA256
        assert ctx.ghidra_binary_sha256 == ghidra_sha
        assert ctx.ghidra_variant == "debug"

    def test_context_is_frozen(self, build_receipt):
        entry = resolve_target_build_entry(build_receipt, TEST_SHA256)
        ctx = resolve_build_context(build_receipt, entry, TEST_SHA256)

        with pytest.raises(AttributeError):
            ctx.opt = "O3"  # type: ignore[misc]
