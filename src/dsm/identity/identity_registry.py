"""
Identity Registry — multi-agent identity governance.

Manages registration, resolution, revocation and trust scoring across agents.
Shard: `identity_registry` (separate from `identity` used by IdentityManager).

Design:
- register is idempotent (append-only, latest-wins on resolve)
- revoke appends a tombstone (original stays in log forever)
- resolve uses a lazy in-memory index, O(1) after first call
- trust_score has two levels: fast (O(1) metadata-only) and deep (O(N) cached)
"""

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from ..core.models import Entry
from ..core.storage import Storage
from ..exceptions import IdentityNotFound, UnauthorizedRevocation

logger = logging.getLogger(__name__)

IDENTITY_REGISTRY_SHARD = "identity_registry"

# Default trust baseline for newly registered agents
_DEFAULT_TRUST_BASELINE = 0.5

# Deep trust cache TTL in seconds (invalidated on new entry anyway)
_DEEP_TRUST_CACHE_TTL = 300


@dataclass(frozen=True)
class AgentIdentity:
    """Resolved identity snapshot for an agent."""
    agent_id: str
    public_key: str
    owner_id: str
    model: Optional[str]       # "claude", "gpt", "gemini", ...
    registered_at: datetime
    trust_score: float


class IdentityRegistry:
    """Multi-agent identity registry backed by DSM shard `identity:registry`.

    All mutations are append-only entries in the shard.
    Read operations use a lazy in-memory index rebuilt on first access
    and invalidated whenever a new entry is appended.
    """

    def __init__(self, storage: Storage, trust_baseline: float = _DEFAULT_TRUST_BASELINE):
        self._storage = storage
        self._trust_baseline = trust_baseline

        # Lazy index: agent_id -> latest registration dict
        self._index: Optional[Dict[str, dict]] = None
        # Track entry count to detect external writes
        self._index_entry_count: int = 0

        # Deep trust cache: agent_id -> (score, timestamp)
        self._deep_trust_cache: Dict[str, tuple] = {}

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    def _invalidate_index(self) -> None:
        """Mark the index as stale — will be rebuilt on next read."""
        self._index = None

    def _ensure_index(self) -> Dict[str, dict]:
        """Build or return the lazy index from shard entries."""
        if self._index is not None:
            return self._index

        entries = self._storage.read(IDENTITY_REGISTRY_SHARD, limit=10**6)
        index: Dict[str, dict] = {}

        # entries come newest-first from Storage.read(); we process
        # oldest-first so latest-wins naturally overwrites.
        for entry in reversed(entries):
            try:
                data = json.loads(entry.content)
            except (json.JSONDecodeError, TypeError):
                continue

            event_type = data.get("event_type")
            agent_id = data.get("agent_id")
            if not agent_id:
                continue

            if event_type == "register":
                index[agent_id] = {
                    "agent_id": agent_id,
                    "public_key": data.get("public_key", ""),
                    "owner_id": data.get("owner_id", ""),
                    "model": data.get("model"),
                    "registered_at": entry.timestamp,
                    "revoked": False,
                    "entry_hash": entry.hash,
                }
            elif event_type == "revoke":
                if agent_id in index:
                    index[agent_id]["revoked"] = True

        self._index = index
        self._index_entry_count = len(entries)
        return index

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        agent_id: str,
        public_key: str,
        owner_id: str,
        owner_signature: str,
        model: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Entry:
        """Register an agent identity. Idempotent — always appends.

        If the same agent_id is registered twice, resolve() returns
        the latest registration (latest-wins).
        """
        content = json.dumps({
            "event_type": "register",
            "agent_id": agent_id,
            "public_key": public_key,
            "owner_id": owner_id,
            "owner_signature": owner_signature,
            "model": model,
            "extra": metadata or {},
        }, sort_keys=True, separators=(",", ":"))

        entry = Entry(
            id=str(uuid4()),
            timestamp=datetime.now(timezone.utc),
            session_id="identity_registry",
            source="identity_registry",
            content=content,
            shard=IDENTITY_REGISTRY_SHARD,
            hash="",
            prev_hash=None,
            metadata={"event_type": "register", "agent_id": agent_id},
            version="v2.0",
        )
        result = self._storage.append(entry)
        self._invalidate_index()
        logger.info("Registered agent %s (owner: %s)", agent_id, owner_id)
        return result

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def resolve(self, agent_id: str) -> Optional[AgentIdentity]:
        """Resolve an agent identity. Returns None if not found or revoked.

        O(1) via lazy index after first call.
        """
        index = self._ensure_index()
        rec = index.get(agent_id)
        if rec is None or rec["revoked"]:
            return None

        return AgentIdentity(
            agent_id=rec["agent_id"],
            public_key=rec["public_key"],
            owner_id=rec["owner_id"],
            model=rec["model"],
            registered_at=rec["registered_at"],
            trust_score=self.trust_score(agent_id),
        )

    # ------------------------------------------------------------------
    # Revocation
    # ------------------------------------------------------------------

    def revoke(
        self,
        agent_id: str,
        owner_id: str,
        owner_signature: str,
        reason: Optional[str] = None,
    ) -> Entry:
        """Revoke an agent. Only the registered owner can revoke.

        Appends a tombstone — the original registration stays forever.
        Raises UnauthorizedRevocation if caller is not the owner.
        """
        index = self._ensure_index()
        rec = index.get(agent_id)

        if rec is not None and rec["owner_id"] != owner_id:
            raise UnauthorizedRevocation(agent_id, owner_id, rec["owner_id"])

        content = json.dumps({
            "event_type": "revoke",
            "agent_id": agent_id,
            "owner_id": owner_id,
            "owner_signature": owner_signature,
            "reason": reason,
        }, sort_keys=True, separators=(",", ":"))

        entry = Entry(
            id=str(uuid4()),
            timestamp=datetime.now(timezone.utc),
            session_id="identity_registry",
            source="identity_registry",
            content=content,
            shard=IDENTITY_REGISTRY_SHARD,
            hash="",
            prev_hash=None,
            metadata={"event_type": "revoke", "agent_id": agent_id},
            version="v2.0",
        )
        result = self._storage.append(entry)
        self._invalidate_index()
        self._deep_trust_cache.pop(agent_id, None)
        logger.info("Revoked agent %s (by: %s, reason: %s)", agent_id, owner_id, reason)
        return result

    # ------------------------------------------------------------------
    # Trust scoring
    # ------------------------------------------------------------------

    def trust_score(self, agent_id: str) -> float:
        """Fast trust score — O(1), based on registry metadata only.

        Returns trust_baseline for known agents, 0.0 for revoked/unknown.
        """
        index = self._ensure_index()
        rec = index.get(agent_id)
        if rec is None:
            return 0.0
        if rec["revoked"]:
            return 0.0

        # Fast trust: baseline adjusted by registration age
        age_seconds = (datetime.now(timezone.utc) - rec["registered_at"]).total_seconds()
        # Slight bonus for older registrations (max +0.1 after 30 days)
        age_bonus = min(age_seconds / (30 * 86400) * 0.1, 0.1)
        return min(self._trust_baseline + age_bonus, 1.0)

    def deep_trust_score(self, agent_id: str) -> float:
        """Deep trust score — O(N) first call, cached after.

        Includes chain integrity rate and entry count analysis.
        Falls back to fast trust if agent not found.
        """
        # Check cache
        cached = self._deep_trust_cache.get(agent_id)
        if cached is not None:
            score, ts = cached
            if time.time() - ts < _DEEP_TRUST_CACHE_TTL:
                return score

        index = self._ensure_index()
        rec = index.get(agent_id)
        if rec is None or rec["revoked"]:
            return 0.0

        # Compute deep trust: scan all entries for this agent
        entries = self._storage.read(IDENTITY_REGISTRY_SHARD, limit=10**6)
        agent_entries = []
        for e in entries:
            try:
                data = json.loads(e.content)
            except (json.JSONDecodeError, TypeError):
                continue
            if data.get("agent_id") == agent_id:
                agent_entries.append(e)

        # Chain integrity check
        chain_ok = 0
        for e in agent_entries:
            if e.hash and e.prev_hash is not None:
                chain_ok += 1

        chain_rate = chain_ok / max(len(agent_entries), 1)

        # Base score + chain integrity contribution
        fast = self.trust_score(agent_id)
        deep = fast * 0.7 + chain_rate * 0.3
        deep = min(max(deep, 0.0), 1.0)

        self._deep_trust_cache[agent_id] = (deep, time.time())
        return deep

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def list_agents(self, owner_id: Optional[str] = None) -> List[AgentIdentity]:
        """List all active (non-revoked) agents, optionally filtered by owner."""
        index = self._ensure_index()
        results = []
        for rec in index.values():
            if rec["revoked"]:
                continue
            if owner_id is not None and rec["owner_id"] != owner_id:
                continue
            results.append(AgentIdentity(
                agent_id=rec["agent_id"],
                public_key=rec["public_key"],
                owner_id=rec["owner_id"],
                model=rec["model"],
                registered_at=rec["registered_at"],
                trust_score=self.trust_score(rec["agent_id"]),
            ))
        return results

    def history(self, agent_id: str) -> List[Entry]:
        """Return all registry entries for a given agent (chronological)."""
        entries = self._storage.read(IDENTITY_REGISTRY_SHARD, limit=10**6)
        result = []
        for e in reversed(entries):  # oldest first
            try:
                data = json.loads(e.content)
            except (json.JSONDecodeError, TypeError):
                continue
            if data.get("agent_id") == agent_id:
                result.append(e)
        return result
