"""DSM Consumption Layer — Provenance (daryl port).

Phase 4 port of ``dsm_v0.provenance``. Same public API, same output
shapes, same enums. Backend swapped from raw JSONL shards to daryl's
native Storage + ``verify.verify_shard``.

Key semantic note
-----------------
In ``dsm_v0``, one session == one physical shard file. In daryl,
multiple sessions live inside a single physical shard. Consequently
``source_shards`` returned by this module is a list of **daryl shard
ids** (physical storage containers), not session_ids. The meaning is
preserved: "which storage containers must be walked to audit this
pack". Callers that need session-level provenance can still filter
items by ``session_id`` in the returned block.

Verification maps to :func:`dsm.verify.verify_shard`, which walks the
entire shard (not a single session) — this is a deliberate daryl
semantic choice because the hash chain in daryl spans all sessions
within a shard.
"""

from .builder import (
    build_provenance,
    promote_to_verified_claims,
    INTEGRITY_BROKEN,
    INTEGRITY_NOT_VERIFIED,
    INTEGRITY_OK,
    TRUST_PARTIAL,
    TRUST_UNVERIFIED,
    TRUST_VERIFIED,
)

__all__ = [
    "build_provenance",
    "promote_to_verified_claims",
    "INTEGRITY_BROKEN",
    "INTEGRITY_NOT_VERIFIED",
    "INTEGRITY_OK",
    "TRUST_PARTIAL",
    "TRUST_UNVERIFIED",
    "TRUST_VERIFIED",
]
