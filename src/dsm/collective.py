"""
Collective Memory — shared verifiable memory across agents.

Single writer guarantee: ShardSyncEngine is the only writer to collective shards.
Agents push projections (not full entries), pull deltas, reconcile on session end.

Components:
- CollectiveShard: read-side index with sliding window
- ShardSyncEngine: push/pull/reconcile with orchestrator admission
- CollectiveMemoryDistiller: progressive distillation on threshold
- RollingDigester: temporal structural digests + budget-aware context loading

Depends on A (identity), B (sovereignty), C (orchestrator).
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from .core.models import Entry
from .core.storage import Storage
from .identity.identity_registry import IdentityRegistry
from .orchestrator import NeutralOrchestrator
from .sovereignty import SovereigntyPolicy

logger = logging.getLogger(__name__)

COLLECTIVE_PREFIX = "collective_"
SYNC_LOG_SHARD = "sync_log"


# ------------------------------------------------------------------
# Dataclasses
# ------------------------------------------------------------------


@dataclass(frozen=True)
class CollectiveEntry:
    """Projection of a private entry into the collective."""
    hash: str
    agent_id: str
    source_hash: str           # reference to original private entry
    content_hash: str          # verifiable without private shard access
    summary: str               # Tier 1 — short context (~100 chars)
    detail: str                # Tier 2 — extended (~1000 chars)
    key_findings: tuple        # Tier 2 — structured findings
    action_type: str
    agent_prev_hash: str       # per-agent chain in collective
    contributed_at: datetime


@dataclass(frozen=True)
class DigestEntry:
    """Temporal digest — structural aggregation of entries."""
    digest_id: str
    level: int                 # 1=hourly, 2=daily, 3=weekly, 4=monthly
    start_time: datetime
    end_time: datetime
    source_count: int
    source_hash: str           # SHA-256(concat(entry_hashes))
    key_events: tuple          # aggregated from key_findings
    agents_involved: tuple
    metrics: dict


@dataclass(frozen=True)
class ContextStack:
    """Budget-aware context result from read_with_digests()."""
    recent: tuple                    # CollectiveEntry list
    hourly_digests: tuple            # Level 1 DigestEntry list
    daily_digests: tuple             # Level 2 DigestEntry list
    weekly_digests: tuple            # Level 3 DigestEntry list
    total_tokens: int
    coverage: str                    # "last_3_hours", "last_2_days", etc.


@dataclass(frozen=True)
class PushResult:
    """Result of a sync push operation."""
    admitted: tuple            # hashes admitted
    rejected: tuple            # (hash, reason) pairs


@dataclass(frozen=True)
class PullResult:
    """Result of a sync pull operation."""
    synced: int
    last_hash: Optional[str]


@dataclass(frozen=True)
class ReconcileResult:
    """Result of a full reconcile (push + pull)."""
    push: PushResult
    pull: PullResult


# ------------------------------------------------------------------
# CollectiveShard — read-side
# ------------------------------------------------------------------


class CollectiveShard:
    """Read-side interface for a collective shard with sliding window index."""

    def __init__(self, storage: Storage, shard_name: str, window_size: int = 500):
        self._storage = storage
        self.shard_name = shard_name if shard_name.startswith(COLLECTIVE_PREFIX) else COLLECTIVE_PREFIX + shard_name
        self._window_size = window_size
        # Lazy index
        self._index: Optional[List[CollectiveEntry]] = None
        self._last_contribution_by_agent: Dict[str, str] = {}

    def _invalidate(self) -> None:
        self._index = None

    def _ensure_index(self) -> List[CollectiveEntry]:
        if self._index is not None:
            return self._index

        entries = self._storage.read(self.shard_name, limit=self._window_size)
        result = []
        agent_last: Dict[str, str] = {}

        for entry in reversed(entries):  # oldest first
            try:
                data = json.loads(entry.content)
            except (json.JSONDecodeError, TypeError):
                continue

            agent_id = data.get("agent_id", "")
            ce = CollectiveEntry(
                hash=entry.hash or "",
                agent_id=agent_id,
                source_hash=data.get("source_hash", ""),
                content_hash=data.get("content_hash", ""),
                summary=data.get("summary", ""),
                detail=data.get("detail", ""),
                key_findings=tuple(data.get("key_findings", [])),
                action_type=data.get("action_type", ""),
                agent_prev_hash=data.get("agent_prev_hash", ""),
                contributed_at=entry.timestamp,
            )
            result.append(ce)
            agent_last[agent_id] = entry.hash or ""

        self._index = result
        self._last_contribution_by_agent = agent_last
        return result

    def recent(self, limit: int = 50, agent_id: Optional[str] = None,
               entry_type: Optional[str] = None) -> List[CollectiveEntry]:
        """Get recent collective entries with optional filters. O(1) via index."""
        index = self._ensure_index()
        # newest first
        entries = list(reversed(index))
        if agent_id:
            entries = [e for e in entries if e.agent_id == agent_id]
        if entry_type:
            entries = [e for e in entries if e.action_type == entry_type]
        return entries[:limit]

    def since(self, entry_hash: str) -> List[CollectiveEntry]:
        """Get entries after a given hash (for incremental sync)."""
        index = self._ensure_index()
        found = False
        result = []
        for e in index:
            if found:
                result.append(e)
            if e.hash == entry_hash:
                found = True
        return result

    def summary(self) -> dict:
        """Collective summary: entry count, agents involved, latest hash."""
        index = self._ensure_index()
        agents = set(e.agent_id for e in index)
        return {
            "shard": self.shard_name,
            "entry_count": len(index),
            "agents": sorted(agents),
            "latest_hash": index[-1].hash if index else None,
        }

    def last_hash_for_agent(self, agent_id: str) -> str:
        """O(1) lookup of last contribution hash for an agent."""
        self._ensure_index()
        return self._last_contribution_by_agent.get(agent_id, "")


# ------------------------------------------------------------------
# ShardSyncEngine — single writer to collective
# ------------------------------------------------------------------


class ShardSyncEngine:
    """Sync engine — the only writer to collective shards.

    Pushes projections (not full entries) after orchestrator admission.
    Pulls deltas and writes sync summaries to sync_log.
    """

    def __init__(
        self,
        storage: Storage,
        collective: CollectiveShard,
        identity: IdentityRegistry,
        policy: SovereigntyPolicy,
        orchestrator: NeutralOrchestrator,
    ):
        self._storage = storage
        self._collective = collective
        self._identity = identity
        self._policy = policy
        self._orchestrator = orchestrator

    def push(
        self,
        agent_id: str,
        owner_id: str,
        entries: List[Entry],
        summary_fn=None,
        detail_fn=None,
    ) -> PushResult:
        """Push private entries as projections to the collective.

        Each entry goes through orchestrator admission.
        Only projections are written (hash, summary, content_hash — not full content).

        Args:
            summary_fn: Optional callable(entry) -> str for Tier 1 summary
            detail_fn: Optional callable(entry) -> (detail_str, key_findings_list) for Tier 2
        """
        admitted = []
        rejected = []

        for entry in entries:
            # Orchestrator admission
            result = self._orchestrator.admit(entry, agent_id, owner_id)
            if not result.allowed:
                rejected.append((entry.hash or "", result.reason))
                continue

            # Build projection
            summary = summary_fn(entry) if summary_fn else entry.content[:100]
            detail = ""
            key_findings = []
            if detail_fn:
                detail, key_findings = detail_fn(entry)

            content_hash = hashlib.sha256(
                entry.content.encode("utf-8")
            ).hexdigest()

            agent_prev = self._collective.last_hash_for_agent(agent_id)

            projection_content = json.dumps({
                "agent_id": agent_id,
                "source_hash": entry.hash or "",
                "content_hash": content_hash,
                "summary": summary,
                "detail": detail,
                "key_findings": key_findings,
                "action_type": (entry.metadata or {}).get("event_type", "unknown"),
                "agent_prev_hash": agent_prev,
            }, sort_keys=True, separators=(",", ":"))

            projection = Entry(
                id=str(uuid4()),
                timestamp=datetime.now(timezone.utc),
                session_id="sync_engine",
                source="sync_engine",
                content=projection_content,
                shard=self._collective.shard_name,
                hash="",
                prev_hash=None,
                metadata={
                    "event_type": "collective_contribution",
                    "agent_id": agent_id,
                    "source_hash": entry.hash or "",
                },
                version="v2.0",
            )

            try:
                written = self._storage.append(projection)
                admitted.append(written.hash or "")
                self._collective._invalidate()
            except OSError as e:
                logger.error("Failed to write projection: %s", e)
                rejected.append((entry.hash or "", str(e)))

        return PushResult(admitted=tuple(admitted), rejected=tuple(rejected))

    def pull(self, agent_id: str, since_hash: Optional[str] = None) -> PullResult:
        """Pull new collective entries since a hash. Writes summary to sync_log."""
        if since_hash:
            new_entries = self._collective.since(since_hash)
        else:
            new_entries = self._collective.recent(limit=100)

        if not new_entries:
            return PullResult(synced=0, last_hash=since_hash)

        last_hash = new_entries[-1].hash if new_entries else since_hash

        # Write sync summary to sync_log (not agent shard)
        sync_content = json.dumps({
            "event_type": "sync_pull",
            "agent_id": agent_id,
            "entries_synced": len(new_entries),
            "since_hash": since_hash,
            "last_hash": last_hash,
        }, sort_keys=True, separators=(",", ":"))

        sync_entry = Entry(
            id=str(uuid4()),
            timestamp=datetime.now(timezone.utc),
            session_id="sync_engine",
            source="sync_engine",
            content=sync_content,
            shard=SYNC_LOG_SHARD,
            hash="",
            prev_hash=None,
            metadata={"event_type": "sync_pull", "agent_id": agent_id},
            version="v2.0",
        )

        try:
            self._storage.append(sync_entry)
        except OSError as e:
            logger.error("Failed to write sync log: %s", e)

        return PullResult(synced=len(new_entries), last_hash=last_hash)

    def reconcile(self, agent_id: str, owner_id: str,
                  entries: List[Entry], since_hash: Optional[str] = None,
                  summary_fn=None, detail_fn=None) -> ReconcileResult:
        """Push + Pull in one call. Triggered on session end."""
        push_result = self.push(agent_id, owner_id, entries,
                                summary_fn=summary_fn, detail_fn=detail_fn)
        pull_result = self.pull(agent_id, since_hash=since_hash)
        return ReconcileResult(push=push_result, pull=pull_result)


# ------------------------------------------------------------------
# CollectiveMemoryDistiller
# ------------------------------------------------------------------


class CollectiveMemoryDistiller:
    """Progressive distillation: compress older entries when threshold exceeded."""

    DISTILLED_SHARD_SUFFIX = "distilled"

    def __init__(self, threshold: int = 1000):
        self._threshold = threshold

    def distill(self, collective: CollectiveShard, storage: Storage,
                max_entries: int = None) -> dict:
        """Distill older entries into a summary entry.

        Keeps the most recent entries, summarizes the rest into
        collective_{name}_distilled shard.

        Returns: {"distilled": int, "kept": int, "digest_hash": str}
        """
        max_entries = max_entries or self._threshold
        index = collective._ensure_index()

        if len(index) <= max_entries:
            return {"distilled": 0, "kept": len(index), "digest_hash": ""}

        # Split: older entries get distilled, newer ones stay
        to_distill = index[:len(index) - max_entries]
        kept = index[len(index) - max_entries:]

        # Build digest
        hashes = [e.hash for e in to_distill]
        digest_hash = hashlib.sha256(
            "".join(hashes).encode("utf-8")
        ).hexdigest()

        agents = sorted(set(e.agent_id for e in to_distill))
        key_events = []
        for e in to_distill:
            key_events.extend(e.key_findings)

        distill_shard = collective.shard_name + "_" + self.DISTILLED_SHARD_SUFFIX

        distill_content = json.dumps({
            "event_type": "distillation",
            "source_count": len(to_distill),
            "digest_hash": digest_hash,
            "agents_involved": agents,
            "key_events": list(key_events[:50]),  # cap to avoid huge entries
            "first_timestamp": to_distill[0].contributed_at.isoformat(),
            "last_timestamp": to_distill[-1].contributed_at.isoformat(),
        }, sort_keys=True, separators=(",", ":"))

        entry = Entry(
            id=str(uuid4()),
            timestamp=datetime.now(timezone.utc),
            session_id="distiller",
            source="distiller",
            content=distill_content,
            shard=distill_shard,
            hash="",
            prev_hash=None,
            metadata={"event_type": "distillation"},
            version="v2.0",
        )

        try:
            storage.append(entry)
        except OSError as e:
            logger.error("Failed to write distillation: %s", e)

        return {
            "distilled": len(to_distill),
            "kept": len(kept),
            "digest_hash": digest_hash,
        }


# ------------------------------------------------------------------
# RollingDigester
# ------------------------------------------------------------------


class RollingDigester:
    """Produces temporal digests at multiple granularities.

    Digests are structural aggregations of pre-computed content
    (detail + key_findings from Tier 2 projections), not LLM-generated.
    Stored in collective_{name}_digests shard.
    """

    DIGESTS_SHARD_SUFFIX = "digests"

    # Estimated token costs per item type
    _TOKENS_PER_ENTRY = 300       # Tier 2 full detail
    _TOKENS_PER_DIGEST = 80       # compressed digest

    def __init__(self, collective: CollectiveShard, storage: Storage):
        self._collective = collective
        self._storage = storage
        self._digests_shard = collective.shard_name + "_" + self.DIGESTS_SHARD_SUFFIX

    def digest_window(self, start: datetime, end: datetime, level: int) -> DigestEntry:
        """Produce a structural digest for a time window.

        Aggregates key_findings, counts, metrics from entries in the window.
        Fully deterministic — no LLM, no external deps.
        """
        index = self._collective._ensure_index()
        window_entries = [
            e for e in index
            if start <= e.contributed_at <= end
        ]

        # Aggregate
        all_findings = []
        agents = set()
        success_count = 0
        for e in window_entries:
            all_findings.extend(e.key_findings)
            agents.add(e.agent_id)
            if e.action_type not in ("error", "failure"):
                success_count += 1

        # Source hash = SHA-256(concat(entry hashes))
        source_hash = hashlib.sha256(
            "".join(e.hash for e in window_entries).encode("utf-8")
        ).hexdigest()

        digest_id = f"digest_L{level}_{start.strftime('%Y%m%d%H%M')}"

        digest = DigestEntry(
            digest_id=digest_id,
            level=level,
            start_time=start,
            end_time=end,
            source_count=len(window_entries),
            source_hash=source_hash,
            key_events=tuple(all_findings[:30]),
            agents_involved=tuple(sorted(agents)),
            metrics={
                "success_rate": success_count / max(len(window_entries), 1),
                "entry_count": len(window_entries),
            },
        )

        # Write to digests shard
        digest_content = json.dumps({
            "event_type": "digest",
            "digest_id": digest.digest_id,
            "level": digest.level,
            "start_time": digest.start_time.isoformat(),
            "end_time": digest.end_time.isoformat(),
            "source_count": digest.source_count,
            "source_hash": digest.source_hash,
            "key_events": list(digest.key_events),
            "agents_involved": list(digest.agents_involved),
            "metrics": digest.metrics,
        }, sort_keys=True, separators=(",", ":"))

        entry = Entry(
            id=str(uuid4()),
            timestamp=datetime.now(timezone.utc),
            session_id="digester",
            source="digester",
            content=digest_content,
            shard=self._digests_shard,
            hash="",
            prev_hash=None,
            metadata={"event_type": "digest", "level": level},
            version="v2.0",
        )

        try:
            self._storage.append(entry)
        except OSError as e:
            logger.error("Failed to write digest: %s", e)

        return digest

    def read_with_digests(self, since: datetime, max_tokens: int = 8000) -> ContextStack:
        """Budget-aware context loading.

        Automatically selects the best combination of recent entries (full detail)
        and temporal digests (compressed) to fit within max_tokens.
        """
        now = datetime.now(timezone.utc)
        index = self._collective._ensure_index()

        # Split entries: recent (since) vs older
        recent_entries = [e for e in index if e.contributed_at >= since]

        # Budget: fill with recent entries first (Tier 2 = ~300 tokens each)
        budget = max_tokens
        selected_recent = []
        for e in reversed(recent_entries):  # newest first
            cost = self._TOKENS_PER_ENTRY
            if budget - cost < 0:
                break
            selected_recent.append(e)
            budget -= cost

        # Fill remaining budget with digests (hourly, daily, weekly)
        hourly = []
        daily = []
        weekly = []

        # Read existing digests from shard
        digest_entries = self._storage.read(self._digests_shard, limit=1000)
        stored_digests = []
        for de in reversed(digest_entries):
            try:
                data = json.loads(de.content)
                if data.get("event_type") != "digest":
                    continue
                stored_digests.append(DigestEntry(
                    digest_id=data["digest_id"],
                    level=data["level"],
                    start_time=datetime.fromisoformat(data["start_time"]),
                    end_time=datetime.fromisoformat(data["end_time"]),
                    source_count=data["source_count"],
                    source_hash=data["source_hash"],
                    key_events=tuple(data.get("key_events", [])),
                    agents_involved=tuple(data.get("agents_involved", [])),
                    metrics=data.get("metrics", {}),
                ))
            except (json.JSONDecodeError, KeyError, TypeError):
                continue

        for d in stored_digests:
            if budget <= 0:
                break
            cost = self._TOKENS_PER_DIGEST
            if d.level == 1:
                hourly.append(d)
            elif d.level == 2:
                daily.append(d)
            elif d.level == 3:
                weekly.append(d)
            budget -= cost

        # Compute coverage description
        total_used = max_tokens - budget
        if selected_recent:
            span = now - selected_recent[-1].contributed_at
            hours = span.total_seconds() / 3600
            if hours < 24:
                coverage = f"last_{int(hours)}_hours"
            else:
                coverage = f"last_{int(hours / 24)}_days"
        else:
            coverage = "no_recent"

        return ContextStack(
            recent=tuple(selected_recent),
            hourly_digests=tuple(hourly),
            daily_digests=tuple(daily),
            weekly_digests=tuple(weekly),
            total_tokens=total_used,
            coverage=coverage,
        )
