"""
Profile — support-profile descriptor and tunable parameters.

The profile encapsulates all policy knobs so that core extraction
logic contains no opinions.  Changing thresholds or adding future
support is a profile change, not a code change.
"""
from dataclasses import dataclass, field
from typing import FrozenSet


@dataclass(frozen=True)
class Profile:
    """Describes what the analyzer supports and how it classifies quality."""

    # Identity
    profile_id: str

    # Supported binary variants
    supported_variants: FrozenSet[str] = frozenset({"stripped"})

    # Ghidra invocation
    ghidra_container: str = "reforge-ghidra-worker"
    ghidra_script_path: str = "/files/ghidra/scripts"
    ghidra_project_dir: str = "/ghidra/projects"
    decompile_timeout: int = 30  # seconds per function (passed to Java script)
    analysis_timeout: int = 600  # seconds total for analyzeHeadless

    # Binary-level warn thresholds
    high_decompile_fail_rate: float = 0.20

    # Fat function thresholds (§9.2)
    fat_function_size_percentile: float = 0.90
    fat_function_bb_threshold: int = 50
    fat_function_temp_threshold: int = 20
    fat_function_ratio_threshold: float = 5.0

    # Inline-likely additional condition (§9.3)
    inline_likely_bb_threshold: int = 30
    inline_likely_temp_threshold: int = 15

    @classmethod
    def v1(cls) -> "Profile":
        """The locked v1 profile: linux-x86_64-elf-ghidra-headless."""
        return cls(
            profile_id="linux-x86_64-elf-ghidra-headless",
        )

    @classmethod
    def v1_all_variants(cls) -> "Profile":
        """v1 profile covering debug + release + stripped variants."""
        return cls(
            profile_id="linux-x86_64-elf-ghidra-headless",
            supported_variants=frozenset({"debug", "release", "stripped"}),
        )
