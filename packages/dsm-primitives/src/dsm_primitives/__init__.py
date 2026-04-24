"""dsm-primitives: canonical serialization, hashing, signing.

See docs/architecture/ADR_0002_DSM_PRIMITIVES.md for the protocol spec.
"""

from .canonical import canonical_json
from .hashing import hash_canonical, verify_hash
from .signing import sign, verify_signature

__version__ = "0.1.0"

__all__ = [
    "canonical_json",
    "hash_canonical",
    "verify_hash",
    "sign",
    "verify_signature",
]
