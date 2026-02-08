"""
Profile — support-profile descriptor and tunable parameters.

The profile encapsulates all policy knobs so that core extraction
logic contains no opinions.  Changing thresholds or adding future
compiler support is a profile change, not a code change.
"""
from dataclasses import dataclass, field
from typing import FrozenSet, List


@dataclass(frozen=True)
class Profile:
    """Describes what the oracle supports and how it classifies quality."""

    # Identity
    profile_id: str

    # Supported scope
    supported_compilers: FrozenSet[str]
    supported_opts: FrozenSet[str]

    # File-path exclusions (dominant-file paths starting with these are flagged)
    exclude_paths: List[str] = field(default_factory=list)

    # Thresholds
    min_dominant_file_ratio: float = 0.7
    max_fragments_warn: int = 2       # warn if function has more range segments

    @classmethod
    def v0(cls) -> "Profile":
        """The locked v0 profile: linux-x86_64-gcc-O0O1."""
        return cls(
            profile_id="linux-x86_64-gcc-O0O1",
            supported_compilers=frozenset({"gcc"}),
            supported_opts=frozenset({"O0", "O1"}),
            exclude_paths=["/usr/include", "/usr/lib/gcc"],
            min_dominant_file_ratio=0.7,
            max_fragments_warn=2,
        )
