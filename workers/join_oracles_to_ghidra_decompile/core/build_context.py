"""
Build context — resolve target binary metadata from the build receipt.

Stage 0 of the join pipeline.  Pure function, no IO.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BuildContext:
    """Immutable provenance extracted from the build receipt.

    In a cross-variant join (e.g. oracle=debug, ghidra=stripped) the
    oracle and ghidra binaries are different artifacts.  ``binary_sha256``
    and ``variant`` always refer to the **oracle** side (ground truth).
    ``ghidra_binary_sha256`` and ``ghidra_variant`` capture the Ghidra
    side when they differ.
    """

    binary_sha256: str          # oracle binary
    job_id: str
    test_case: str              # = job.name
    opt: str                    # optimization level (O0, O1, O2, O3)
    variant: str                # oracle variant (debug, release, stripped)
    builder_profile_id: str
    ghidra_binary_sha256: str | None = None   # None ⇒ same as binary_sha256
    ghidra_variant: str | None = None         # None ⇒ same as variant


def resolve_build_context(
    receipt: dict,
    build_entry: dict,
    binary_sha256: str,
    ghidra_binary_sha256: str | None = None,
    ghidra_variant: str | None = None,
) -> BuildContext:
    """Extract provenance from a resolved receipt + build entry.

    Parameters
    ----------
    receipt:
        The full ``build_receipt.json`` dict.
    build_entry:
        The specific ``BuildCell`` dict whose artifact matches the
        *oracle* binary.
    binary_sha256:
        The canonical SHA-256 of the **oracle** binary artifact.
    ghidra_binary_sha256:
        SHA-256 of the Ghidra binary when it differs from the oracle
        binary (cross-variant join).  *None* means same binary.
    ghidra_variant:
        Build variant of the Ghidra binary (e.g. ``"stripped"``).

    Returns
    -------
    BuildContext
        Frozen dataclass with all provenance fields.
    """
    job = receipt.get("job", {})
    builder = receipt.get("builder", {})

    return BuildContext(
        binary_sha256=binary_sha256,
        job_id=str(job.get("job_id", "")),
        test_case=str(job.get("name", "")),
        opt=str(build_entry.get("optimization", "")),
        variant=str(build_entry.get("variant", "")),
        builder_profile_id=str(builder.get("profile_id", "")),
        ghidra_binary_sha256=ghidra_binary_sha256,
        ghidra_variant=ghidra_variant,
    )
