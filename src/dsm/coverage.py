"""
Memory Coverage Check for DSM.

Compares an agent's semantic index (set of entry IDs or hashes)
against the full DSM log to find gaps — entries that exist in DSM
but are missing from the agent's memory index.

An agent with FULL coverage has indexed every DSM entry.
An agent with CRITICAL_GAPS has unindexed entries that may lead
to forgotten context, repeated actions, or hallucinated history.

Use case: agent startup sanity check, periodic drift detection,
post-crash recovery validation.

Inspired by feedback from @openclawbrian on Moltbook.
"""

import logging
from typing import Optional, Set, List

logger = logging.getLogger(__name__)


class CoverageGap:
    """A single entry present in DSM but missing from the agent's index."""

    def __init__(
        self,
        entry_id: str,
        shard_id: str,
        timestamp: str,
        content_preview: str,
        entry_hash: str,
        event_type: str = "unknown",
        session_id: str = "",
    ):
        self.entry_id = entry_id
        self.shard_id = shard_id
        self.timestamp = timestamp
        self.content_preview = content_preview
        self.entry_hash = entry_hash
        self.event_type = event_type
        self.session_id = session_id

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "shard_id": self.shard_id,
            "timestamp": self.timestamp,
            "content_preview": self.content_preview,
            "entry_hash": self.entry_hash,
            "event_type": self.event_type,
            "session_id": self.session_id,
        }


def check_coverage(
    storage,
    indexed_ids: Optional[Set[str]] = None,
    indexed_hashes: Optional[Set[str]] = None,
    shard_ids: Optional[List[str]] = None,
    max_gaps: int = 500,
) -> dict:
    """
    Check how well an agent's index covers the DSM log.

    The agent provides the set of entry IDs and/or entry hashes it has
    indexed. This function scans the DSM shards and finds entries that
    are NOT in the agent's index.

    Args:
        storage: DSM Storage instance
        indexed_ids: Set of entry.id values the agent has indexed
        indexed_hashes: Set of entry.hash values the agent has indexed
        shard_ids: Optional list of specific shards to check (None = all)
        max_gaps: Maximum number of gap details to collect (prevents OOM)

    Returns:
        {
            "total_entries": int,
            "indexed_entries": int,
            "missing_entries": int,
            "coverage_percent": float,
            "gaps": [CoverageGap.to_dict(), ...],
            "gaps_truncated": bool,
            "shards_checked": int,
            "per_shard": {shard_id: {"total": N, "indexed": N, "missing": N}},
            "status": "FULLY_COVERED" | "PARTIAL_COVERAGE" | "CRITICAL_GAPS" | "NO_INDEX"
        }
    """
    if indexed_ids is None and indexed_hashes is None:
        return {
            "total_entries": 0,
            "indexed_entries": 0,
            "missing_entries": 0,
            "coverage_percent": 0.0,
            "gaps": [],
            "gaps_truncated": False,
            "shards_checked": 0,
            "per_shard": {},
            "status": "NO_INDEX",
        }

    indexed_ids = indexed_ids or set()
    indexed_hashes = indexed_hashes or set()

    # Determine which shards to check
    if shard_ids is None:
        all_shards = storage.list_shards()
        shard_ids = [meta.shard_id for meta in all_shards]

    total_entries = 0
    indexed_entries = 0
    gaps = []
    gaps_truncated = False
    per_shard = {}

    for shard_id in shard_ids:
        entries = storage.read(shard_id, limit=100000)
        entries = list(reversed(entries))  # chronological order

        shard_total = len(entries)
        shard_indexed = 0

        for entry in entries:
            total_entries += 1

            # Check if entry is in the agent's index (by ID or hash)
            is_indexed = (entry.id in indexed_ids) or (entry.hash in indexed_hashes)

            if is_indexed:
                indexed_entries += 1
                shard_indexed += 1
            else:
                # Record the gap
                if len(gaps) < max_gaps:
                    timestamp = (
                        entry.timestamp.isoformat()
                        if hasattr(entry.timestamp, "isoformat")
                        else str(entry.timestamp)
                    )
                    content_preview = (entry.content or "")[:120]
                    event_type = entry.metadata.get("event_type", "unknown")

                    gaps.append(
                        CoverageGap(
                            entry_id=entry.id,
                            shard_id=shard_id,
                            timestamp=timestamp,
                            content_preview=content_preview,
                            entry_hash=entry.hash,
                            event_type=event_type,
                            session_id=entry.session_id,
                        )
                    )
                else:
                    gaps_truncated = True

        per_shard[shard_id] = {
            "total": shard_total,
            "indexed": shard_indexed,
            "missing": shard_total - shard_indexed,
        }

    missing_entries = total_entries - indexed_entries
    coverage_percent = (
        round(indexed_entries / total_entries * 100, 2) if total_entries > 0 else 0.0
    )

    # Determine status
    if total_entries == 0:
        status = "FULLY_COVERED"
    elif coverage_percent == 100.0:
        status = "FULLY_COVERED"
    elif coverage_percent >= 95.0:
        status = "PARTIAL_COVERAGE"
    else:
        status = "CRITICAL_GAPS"

    logger.info(
        "Coverage check: %d/%d entries indexed (%.1f%%) — %s",
        indexed_entries,
        total_entries,
        coverage_percent,
        status,
    )

    return {
        "total_entries": total_entries,
        "indexed_entries": indexed_entries,
        "missing_entries": missing_entries,
        "coverage_percent": coverage_percent,
        "gaps": [g.to_dict() for g in gaps],
        "gaps_truncated": gaps_truncated,
        "shards_checked": len(shard_ids),
        "per_shard": per_shard,
        "status": status,
    }


def check_all(storage, indexed_ids: Optional[Set[str]] = None, indexed_hashes: Optional[Set[str]] = None, max_gaps: int = 500) -> dict:
    """Check coverage across all shards. Convenience wrapper."""
    return check_coverage(storage, indexed_ids=indexed_ids, indexed_hashes=indexed_hashes, max_gaps=max_gaps)
