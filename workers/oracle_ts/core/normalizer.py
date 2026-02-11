"""
Normalizer — deterministic text normalization and hashing.

v0 normalization:
  - Strip C comments (block and line).
  - Collapse all whitespace to a single space.
  - Strip leading/trailing whitespace.
  - Do NOT rewrite tokens (no hex→decimal, no identifier renaming).
  - Hash with SHA-256.
"""
from __future__ import annotations

import hashlib
import re

# ── Comment stripping ────────────────────────────────────────────────────────

# Matches C block comments (/* ... */) and line comments (// ...\n).
# Uses re.DOTALL so '.' matches newlines inside block comments.
_COMMENT_RE = re.compile(
    r"/\*.*?\*/|//[^\n]*",
    re.DOTALL,
)

# ── Whitespace collapsing ────────────────────────────────────────────────────

_WHITESPACE_RE = re.compile(r"\s+")


# ── Public API ───────────────────────────────────────────────────────────────

def normalize_text(raw: bytes) -> bytes:
    """
    Normalize C source text for deterministic hashing.

    1. Decode as UTF-8 (lossy — replace errors).
    2. Strip all C comments.
    3. Collapse all whitespace runs to a single space.
    4. Strip leading/trailing whitespace.
    5. Re-encode as UTF-8.
    """
    text = raw.decode("utf-8", errors="replace")
    text = _COMMENT_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text)
    text = text.strip()
    return text.encode("utf-8")


def normalize_and_hash(raw: bytes) -> str:
    """Normalize, then return SHA-256 hex digest."""
    return hashlib.sha256(normalize_text(raw)).hexdigest()


def raw_hash(raw: bytes) -> str:
    """SHA-256 hex digest of raw bytes (no normalization)."""
    return hashlib.sha256(raw).hexdigest()
