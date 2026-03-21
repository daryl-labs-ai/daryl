"""
Parallel Shard Lanes — scalable multi-agent collective writes.

Instead of N agents contending on a single collective shard (FileLock bottleneck),
each agent writes to its own lane shard: ``collective_lane_{agent_id}``.

A LaneGroup coordinates:
- Per-agent lane isolation (zero write contention)
- Unified cross-lane reads (merge view)
- Periodic merge entries referencing lane tips
- Budget-aware tiered reads across all lanes

Architecture decision: **Lane-as-Separate-Shard** (Option A).
Zero kernel modifications. Each lane is a normal DSM shard with its own
hash chain, segments, and FileLock. The merge is a read-side view, not
a physical copy.

Depends on: A (identity), B (sovereignty), C (orchestrator), D (collective).
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from .core.models import Entry
from .core.storage import Storage
from .collective import (
    CollectiveEntry,
    CollectiveShard,
    ShardSyncEngine,
    COLLECTIVE_PREFIX,
)
from .identity.identity_registry import IdentityRegistry
from .orchestrator import NeutralOrchestrator
from .sovereignty import SovereigntyPolicy

logger = logging.getLogger(__name__)

LANE_PREFIX = "collective_lane_"


# ------------------------------------------------------------------
# Dataclasses
# ------------------------------------------------------------------


@dataclass(frozen=True)
class LaneTip:
    """Snapshot of a lane's latest state."""
    agent_id: str
    shard_name: str
    entry_count: int
    latest_hash: str
    latest_timestamp: Optional[datetime]


@dataclass(frozen=True)
class MergeEntry:
    """A merge point referencing all lane tips at a moment in time."""
    merge_id: str
    timestamp: datetime
    tips: tuple           # tuple of LaneTip
    merge_hash: str       # SHA-256(concat(tip hashes))


@dataclass(frozen=True)
class LaneWriteResult:
    """Result of a lane write (push to agent's own lane)."""
    lane_shard: str
    admitted: tuple       # hashes admitted
    rejected: tuple       # (hash, reason) pairs


# ------------------------------------------------------------------
# LaneGroup — coordinated parallel lanes
# ------------------------------------------------------------------


class LaneGroup:
    """Manages parallel shard lanes for a collective.

    Each registered agent gets its own lane shard. Writes go to the
    agent's lane (zero contention with other agents). Reads merge
    across all lanes for a unified view.

    Usage::

        lanes = LaneGroup(storage, identity, policy, orchestrator)
        lanes.register_lane("claude_1")
        lanes.register_lane("gpt_1")

        # Each agent writes to its own lane — no contention
        lanes.push("claude_1", "owner", entries)
        lanes.push("gpt_1", "owner", entries)

        # Unified read across all lanes
        recent = lanes.recent(limit=50)
        tiered = lanes.recent_at_tier(tier=2, max_tokens=8000)

        # Merge snapshot
        merge = lanes.create_merge()
    """

    def __init__(
        self,
        storage: Storage,
        identity: IdentityRegistry,
        policy: SovereigntyPolicy,
        orchestrator: NeutralOrchestrator,
        merge_shard: str = "collective_merges",
    ):
        self._storage = storage
        self._identity = identity
        self._policy = policy
        self._orchestrator = orchestrator
        self._merge_shard = merge_shard

        # Lane registry: agent_id -> (CollectiveShard, ShardSyncEngine)
        self._lanes: Dict[str, Tuple[CollectiveShard, ShardSyncEngine]] = {}

    # ------------------------------------------------------------------
    # Lane registration
    # ------------------------------------------------------------------

    def lane_shard_name(self, agent_id: str) -> str:
        """Return the shard name for an agent's lane."""
        return f"{LANE_PREFIX}{agent_id}"

    def register_lane(self, agent_id: str) -> str:
        """Register a lane for an agent. Idempotent.

        Returns the lane shard name.
        """
        if agent_id in self._lanes:
            return self.lane_shard_name(agent_id)

        shard_name = self.lane_shard_name(agent_id)
        collective = CollectiveShard(self._storage, shard_name)
        sync_engine = ShardSyncEngine(
            self._storage,
            collective=collective,
            identity=self._identity,
            policy=self._policy,
            orchestrator=self._orchestrator,
        )
        self._lanes[agent_id] = (collective, sync_engine)
        logger.info("Lane registered: %s -> %s", agent_id, shard_name)
        return shard_name

    def has_lane(self, agent_id: str) -> bool:
        """Check if an agent has a registered lane."""
        return agent_id in self._lanes

    def registered_agents(self) -> List[str]:
        """List all agents with registered lanes."""
        return list(self._lanes.keys())

    def _get_lane(self, agent_id: str) -> Tuple[CollectiveShard, ShardSyncEngine]:
        """Get lane components. Raises KeyError if not registered."""
        if agent_id not in self._lanes:
            raise KeyError(
                f"No lane registered for agent '{agent_id}'. "
                f"Call register_lane('{agent_id}') first."
            )
        return self._lanes[agent_id]

    # ------------------------------------------------------------------
    # Per-lane writes (zero contention)
    # ------------------------------------------------------------------

    def push(
        self,
        agent_id: str,
        owner_id: str,
        entries: List[Entry],
        summary_fn=None,
        detail_fn=None,
    ) -> LaneWriteResult:
        """Push entries to an agent's own lane shard.

        Each agent writes to its own shard — no FileLock contention
        with other agents. Orchestrator admission still applies.

        Args:
            agent_id: The agent pushing entries.
            owner_id: The collective owner.
            entries: Private entries to project.
            summary_fn: Optional summary extractor.
            detail_fn: Optional detail extractor.

        Returns:
            LaneWriteResult with lane shard name and admitted/rejected.
        """
        collective, sync_engine = self._get_lane(agent_id)
        result = sync_engine.push(
            agent_id=agent_id,
            owner_id=owner_id,
            entries=entries,
            summary_fn=summary_fn,
            detail_fn=detail_fn,
        )
        return LaneWriteResult(
            lane_shard=collective.shard_name,
            admitted=result.admitted,
            rejected=result.rejected,
        )

    # ------------------------------------------------------------------
    # Cross-lane reads (unified merge view)
    # ------------------------------------------------------------------

    def recent(
        self,
        limit: int = 50,
        agent_id: Optional[str] = None,
        entry_type: Optional[str] = None,
    ) -> List[CollectiveEntry]:
        """Read recent entries across all lanes, merged by timestamp.

        If agent_id is specified, reads only that agent's lane (O(1) lookup).
        Otherwise merges all lanes sorted by contributed_at (newest first).

        Args:
            limit: Max entries to return.
            agent_id: Optional filter — single lane only.
            entry_type: Optional filter by action_type.

        Returns:
            List of CollectiveEntry, newest first.
        """
        if agent_id:
            # Single-lane fast path
            collective, _ = self._get_lane(agent_id)
            return collective.recent(limit=limit, entry_type=entry_type)

        # Cross-lane merge: collect from all lanes, sort by time
        all_entries: List[CollectiveEntry] = []
        for aid, (collective, _) in self._lanes.items():
            lane_entries = collective.recent(limit=limit, entry_type=entry_type)
            all_entries.extend(lane_entries)

        # Sort by contributed_at descending (newest first)
        all_entries.sort(key=lambda e: e.contributed_at, reverse=True)
        return all_entries[:limit]

    def recent_at_tier(
        self,
        tier: int = 2,
        limit: int = 50,
        max_tokens: Optional[int] = None,
        agent_id: Optional[str] = None,
    ) -> List[dict]:
        """Read recent entries at a specific tier across all lanes.

        Merges entries from all lanes, sorted by timestamp, then applies
        tier resolution and budget-aware auto-downgrade.

        Args:
            tier: Resolution level (0-3).
            limit: Max entries.
            max_tokens: Optional token budget for auto-downgrade.
            agent_id: Optional single-lane filter.

        Returns:
            List of dicts at the requested (or downgraded) tier.
        """
        if agent_id:
            collective, _ = self._get_lane(agent_id)
            return collective.recent_at_tier(
                tier=tier, limit=limit, max_tokens=max_tokens,
            )

        # Cross-lane: get raw entries, then apply tier + budget
        entries = self.recent(limit=limit)
        if not entries:
            return []

        effective_tier = tier
        if max_tokens is not None:
            cost = len(entries) * CollectiveEntry.tier_token_estimate(tier)
            while cost > max_tokens and effective_tier > 0:
                effective_tier -= 1
                cost = len(entries) * CollectiveEntry.tier_token_estimate(effective_tier)
            if cost > max_tokens:
                per_entry = CollectiveEntry.tier_token_estimate(0)
                entries = entries[:max(1, max_tokens // per_entry)]

        return [e.at_tier(effective_tier) for e in entries]

    # ------------------------------------------------------------------
    # Lane tips & merge
    # ------------------------------------------------------------------

    def tips(self) -> List[LaneTip]:
        """Get the current tip (latest state) of each lane.

        Returns:
            List of LaneTip, one per registered lane.
        """
        result = []
        for agent_id, (collective, _) in self._lanes.items():
            summary = collective.summary()
            index = collective._ensure_index()
            latest_ts = index[-1].contributed_at if index else None
            result.append(LaneTip(
                agent_id=agent_id,
                shard_name=collective.shard_name,
                entry_count=summary["entry_count"],
                latest_hash=summary["latest_hash"] or "",
                latest_timestamp=latest_ts,
            ))
        return result

    def create_merge(self) -> MergeEntry:
        """Create a merge entry referencing all current lane tips.

        The merge entry is written to the merge shard and provides
        a single verifiable reference point across all lanes.

        Returns:
            MergeEntry with tips and merge hash.
        """
        current_tips = self.tips()

        # Merge hash = SHA-256(concat(sorted tip hashes))
        tip_hashes = sorted(t.latest_hash for t in current_tips if t.latest_hash)
        merge_hash = hashlib.sha256(
            "".join(tip_hashes).encode("utf-8")
        ).hexdigest()

        merge_id = f"merge_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}"

        merge = MergeEntry(
            merge_id=merge_id,
            timestamp=datetime.now(timezone.utc),
            tips=tuple(current_tips),
            merge_hash=merge_hash,
        )

        # Write merge entry to merge shard
        merge_content = json.dumps({
            "event_type": "lane_merge",
            "merge_id": merge.merge_id,
            "merge_hash": merge.merge_hash,
            "lane_count": len(current_tips),
            "tips": [
                {
                    "agent_id": t.agent_id,
                    "shard_name": t.shard_name,
                    "entry_count": t.entry_count,
                    "latest_hash": t.latest_hash,
                    "latest_timestamp": t.latest_timestamp.isoformat() if t.latest_timestamp else None,
                }
                for t in current_tips
            ],
        }, sort_keys=True, separators=(",", ":"))

        entry = Entry(
            id=str(uuid4()),
            timestamp=datetime.now(timezone.utc),
            session_id="lane_group",
            source="lane_group",
            content=merge_content,
            shard=self._merge_shard,
            hash="",
            prev_hash=None,
            metadata={"event_type": "lane_merge", "merge_id": merge_id},
            version="v2.0",
        )

        try:
            self._storage.append(entry)
            logger.info(
                "Lane merge created: %s (%d lanes, hash=%s)",
                merge_id, len(current_tips), merge_hash[:16],
            )
        except OSError as e:
            logger.error("Failed to write merge entry: %s", e)

        return merge

    def merge_history(self, limit: int = 20) -> List[dict]:
        """Read recent merge entries from the merge shard.

        Returns:
            List of merge dicts (newest first).
        """
        entries = self._storage.read(self._merge_shard, limit=limit)
        result = []
        for entry in entries:
            try:
                data = json.loads(entry.content)
                if data.get("event_type") == "lane_merge":
                    result.append(data)
            except (json.JSONDecodeError, TypeError):
                continue
        return result

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        """Get statistics across all lanes.

        Returns:
            Dict with lane_count, total_entries, per-lane breakdown.
        """
        lane_stats = []
        total = 0
        for agent_id, (collective, _) in self._lanes.items():
            summary = collective.summary()
            count = summary["entry_count"]
            total += count
            lane_stats.append({
                "agent_id": agent_id,
                "shard": collective.shard_name,
                "entry_count": count,
                "latest_hash": summary["latest_hash"],
            })

        return {
            "lane_count": len(self._lanes),
            "total_entries": total,
            "lanes": lane_stats,
        }

    def verify_lane(self, agent_id: str) -> dict:
        """Verify hash chain integrity of a single lane.

        Returns verification result dict.
        """
        from .verify import verify_shard
        collective, _ = self._get_lane(agent_id)
        return verify_shard(self._storage, collective.shard_name)
