"""Canonical hashing with versioned output.

Per ADR-0002:
  - hash_canonical always produces v1 ("v1:<hex>")
  - verify_hash supports v0 (legacy, no prefix) and v1
  - Unknown formats fail closed (return False)
"""

import hashlib

from .canonical import canonical_json

_V1_PREFIX = "v1:"


def _hash_v0(data: dict) -> str:
    """Compute legacy v0 hash: bare sha256 hex of canonical_json output.

    Used only by verify_hash for backward compatibility with DSM entries
    created before ADR-0002. Never produced by dsm-primitives for writing.
    """
    return hashlib.sha256(canonical_json(data)).hexdigest()


def _hash_v1(data: dict) -> str:
    """Compute v1 hash: 'v1:' + sha256 hex of canonical_json output."""
    digest = hashlib.sha256(canonical_json(data)).hexdigest()
    return f"{_V1_PREFIX}{digest}"


def hash_canonical(data: dict) -> str:
    """Compute the canonical hash of a dict (current version: v1).

    Returns a string of the form 'v1:<64 hex chars>'.

    Per ADR-0002, this function always produces the latest version's
    format. Backward compatibility is handled exclusively by verify_hash.
    """
    return _hash_v1(data)


def verify_hash(data: dict, stored: str) -> bool:
    """Verify that data hashes to the stored value.

    Supports:
      - v1: 'v1:<hex>' format (current)
      - v0: bare '<hex>' format (legacy, no prefix)

    Any other format (including unknown prefixes like 'v2:' not yet
    implemented, or 'sha256:') fails closed (returns False) to prevent
    silent acceptance of malformed or future-format hashes.

    Args:
        data: The dict to hash.
        stored: The stored hash string to verify against.

    Returns:
        True if the computed hash matches the stored value, else False.
    """
    if not isinstance(stored, str):
        return False
    if stored.startswith(_V1_PREFIX):
        return _hash_v1(data) == stored
    if ":" not in stored:
        # v0 legacy: bare hex
        return _hash_v0(data) == stored
    # Unknown format (future version, foreign prefix, etc.) — fail closed
    return False
