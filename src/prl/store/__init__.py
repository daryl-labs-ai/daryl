"""PRL store subpackage (P3) — persist a ProjectMap into DSM.

Write side only. Encodes each PRL node/edge as a kernel ``Entry`` and appends it
via ``Storage.append`` (per-shard tamper-evident hash chain). Per ADR §8:
``Storage.append`` — NOT ``SessionGraph.execute_action`` (which hardcodes the
``sessions`` shard, wraps content in an intent envelope, and is rate-limited).
Per ADR-0001, PRL never reads via ``Storage.read``; reads go through RR (P5).
"""

from __future__ import annotations

from .dsm_commit import (
    CONSULTATION_SHARD,
    ActResult,
    CommitResult,
    PRLStore,
    new_run_id,
    open_storage,
    open_store,
    prl_shard_name,
)

__all__ = [
    "PRLStore",
    "CommitResult",
    "ActResult",
    "CONSULTATION_SHARD",
    "prl_shard_name",
    "new_run_id",
    "open_store",
    "open_storage",
]
