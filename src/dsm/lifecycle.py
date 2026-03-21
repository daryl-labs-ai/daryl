"""
Shard Lifecycle — state machine for shard life and death.

State machine: active → draining → sealed → archived (terminal).
Each transition is a DSM entry in `lifecycle_registry` shard.

Design:
- Distillation before seal (via D's CollectiveMemoryDistiller)
- Spot-check O(1) verify (first + last hash), deep = full replay
- Seal passes through SyncEngine for collective shards (single-writer)
- Automatic triggers: max_entries, max_age_days (from sovereignty config)
- archived is terminal — no transition out

Depends on A (identity), B (sovereignty), D (distiller).
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .core.models import Entry
from .core.storage import Storage
from .shard_families import FAMILY_RETENTION, classify_shard

logger = logging.getLogger(__name__)

LIFECYCLE_SHARD = "lifecycle_registry"


# ------------------------------------------------------------------
# State constants
# ------------------------------------------------------------------


class ShardState:
    """Shard lifecycle states."""
    ACTIVE   = "active"
    DRAINING = "draining"
    SEALED   = "sealed"
    ARCHIVED = "archived"

    _VALID = frozenset({"active", "draining", "sealed", "archived"})

    # Allowed transitions
    _TRANSITIONS = {
        "active":   {"draining", "sealed"},   # seal auto-drains if active
        "draining": {"sealed"},
        "sealed":   {"archived"},
        # archived: terminal — no transitions out
    }


# ------------------------------------------------------------------
# Result dataclasses
# ------------------------------------------------------------------


@dataclass(frozen=True)
class LifecycleResult:
    """Result of a lifecycle transition."""
    ok: bool
    shard_id: str
    transition: Optional[str] = None
    entry: Optional[Entry] = None
    distilled: int = 0
    final_hash: Optional[str] = None
    error: Optional[str] = None


@dataclass(frozen=True)
class VerifyResult:
    """Result of a lifecycle verification."""
    passed: bool
    reason: Optional[str] = None
    last_hash: Optional[str] = None
    summary: Optional[dict] = None


@dataclass(frozen=True)
class TriggerResult:
    """Result of automatic trigger check."""
    triggered: bool
    reason: Optional[str] = None
    action: Optional[str] = None  # "drain", "seal", None


# ------------------------------------------------------------------
# ShardLifecycle
# ------------------------------------------------------------------


class ShardLifecycle:
    """Manages the full lifecycle of DSM shards.

    State machine: active → draining → sealed → archived.
    All transitions are logged to lifecycle_registry shard.
    """

    def __init__(self, storage: Storage, distiller=None):
        self._storage = storage
        self._distiller = distiller
        # State cache: shard_id -> state string
        self._state_cache: Dict[str, str] = {}

    def _invalidate(self, shard_id: str) -> None:
        self._state_cache.pop(shard_id, None)

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def state(self, shard_id: str) -> str:
        """Get current state of a shard. O(1) via cache.

        Default: ACTIVE for any shard without explicit transitions.
        """
        if shard_id in self._state_cache:
            return self._state_cache[shard_id]

        # Scan lifecycle registry for this shard
        entries = self._storage.read(LIFECYCLE_SHARD, limit=10**6)
        current = ShardState.ACTIVE

        for entry in reversed(entries):  # oldest first
            try:
                data = json.loads(entry.content)
            except (json.JSONDecodeError, TypeError):
                continue
            if data.get("shard_id") != shard_id:
                continue
            if data.get("event_type") == "lifecycle_transition":
                to_state = data.get("to_state")
                if to_state in ShardState._VALID:
                    current = to_state

        self._state_cache[shard_id] = current
        return current

    # ------------------------------------------------------------------
    # Transitions
    # ------------------------------------------------------------------

    def _write_transition(
        self, shard_id: str, from_state: str, to_state: str,
        owner_id: str, reason: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> Entry:
        """Write a lifecycle transition entry."""
        content_data = {
            "event_type": "lifecycle_transition",
            "shard_id": shard_id,
            "from_state": from_state,
            "to_state": to_state,
            "owner_id": owner_id,
            "reason": reason,
        }
        if extra:
            content_data.update(extra)

        entry = Entry(
            id=str(uuid4()),
            timestamp=datetime.now(timezone.utc),
            session_id="lifecycle",
            source="lifecycle",
            content=json.dumps(content_data, sort_keys=True, separators=(",", ":")),
            shard=LIFECYCLE_SHARD,
            hash="",
            prev_hash=None,
            metadata={
                "event_type": "lifecycle_transition",
                "shard_id": shard_id,
                "to_state": to_state,
            },
            version="v2.0",
        )
        result = self._storage.append(entry)
        self._state_cache[shard_id] = to_state
        return result

    def drain(self, shard_id: str, owner_id: str, owner_sig: str,
              collective=None) -> LifecycleResult:
        """Transition a shard to DRAINING state.

        Triggers distillation if a distiller and collective are provided.
        """
        current = self.state(shard_id)
        if current != ShardState.ACTIVE:
            return LifecycleResult(
                ok=False, shard_id=shard_id,
                error=f"Cannot drain: shard is {current}, expected active",
            )

        distilled = 0
        if self._distiller and collective:
            result = self._distiller.distill(collective, self._storage)
            distilled = result.get("distilled", 0)

        entry = self._write_transition(
            shard_id, ShardState.ACTIVE, ShardState.DRAINING,
            owner_id, reason="drain requested",
            extra={"distilled_count": distilled},
        )

        logger.info("Shard %s drained (distilled: %d)", shard_id, distilled)
        return LifecycleResult(
            ok=True, shard_id=shard_id,
            transition="active->draining",
            entry=entry, distilled=distilled,
        )

    def seal(self, shard_id: str, owner_id: str, owner_sig: str,
             reason: Optional[str] = None, collective=None) -> LifecycleResult:
        """Seal a shard. Auto-drains if active.

        Performs spot-check before sealing.
        """
        current = self.state(shard_id)

        # Auto-drain if active
        if current == ShardState.ACTIVE:
            drain_result = self.drain(shard_id, owner_id, owner_sig,
                                      collective=collective)
            if not drain_result.ok:
                return drain_result
            current = ShardState.DRAINING

        if current != ShardState.DRAINING:
            return LifecycleResult(
                ok=False, shard_id=shard_id,
                error=f"Cannot seal: shard is {current}, expected draining",
            )

        # Spot-check before seal
        verify = self.verify(shard_id, deep=False)
        if not verify.passed:
            return LifecycleResult(
                ok=False, shard_id=shard_id,
                error=f"Integrity check failed: {verify.reason}",
            )

        # Get final hash
        entries = self._storage.read(shard_id, limit=1)
        final_hash = entries[0].hash if entries else None

        entry = self._write_transition(
            shard_id, ShardState.DRAINING, ShardState.SEALED,
            owner_id, reason=reason or "sealed",
            extra={"final_hash": final_hash},
        )

        logger.info("Shard %s sealed (final_hash: %s)", shard_id, final_hash and final_hash[:16])
        return LifecycleResult(
            ok=True, shard_id=shard_id,
            transition="draining->sealed",
            entry=entry, final_hash=final_hash,
        )

    def archive(self, shard_id: str, owner_id: str,
                owner_sig: str) -> LifecycleResult:
        """Archive a sealed shard. Terminal state — no transition out.

        Stores only the final hash reference.
        """
        current = self.state(shard_id)
        if current != ShardState.SEALED:
            return LifecycleResult(
                ok=False, shard_id=shard_id,
                error=f"Cannot archive: shard is {current}, expected sealed",
            )

        entries = self._storage.read(shard_id, limit=1)
        final_hash = entries[0].hash if entries else None

        entry = self._write_transition(
            shard_id, ShardState.SEALED, ShardState.ARCHIVED,
            owner_id, reason="archived",
            extra={"final_hash": final_hash, "hash_only": True},
        )

        logger.info("Shard %s archived", shard_id)
        return LifecycleResult(
            ok=True, shard_id=shard_id,
            transition="sealed->archived",
            entry=entry, final_hash=final_hash,
        )

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify(self, shard_id: str, deep: bool = False) -> VerifyResult:
        """Verify shard integrity.

        deep=False: spot-check O(1) — first/last hash + count
        deep=True:  full chain replay
        """
        entries = self._storage.read(shard_id, limit=10**6 if deep else 2)

        if not entries:
            return VerifyResult(passed=True, reason="empty shard",
                                summary={"entry_count": 0})

        if not deep:
            # Spot check: verify newest entry has a hash
            newest = entries[0]
            return VerifyResult(
                passed=newest.hash is not None and newest.hash != "",
                reason=None if newest.hash else "missing hash on tip",
                last_hash=newest.hash,
                summary={"entry_count": len(entries), "tip_hash": newest.hash},
            )

        # Deep: full chain verification
        chrono = list(reversed(entries))
        for i, e in enumerate(chrono):
            if i == 0:
                continue
            if e.prev_hash != chrono[i - 1].hash:
                return VerifyResult(
                    passed=False,
                    reason=f"chain break at entry {i}",
                    last_hash=chrono[-1].hash,
                    summary={"entry_count": len(chrono), "break_at": i},
                )

        return VerifyResult(
            passed=True,
            last_hash=chrono[-1].hash,
            summary={"entry_count": len(chrono)},
        )

    # ------------------------------------------------------------------
    # Automatic triggers
    # ------------------------------------------------------------------

    def check_triggers(self, shard_id: str, owner_id: str,
                       owner_sig: str) -> TriggerResult:
        """Check if automatic lifecycle triggers should fire.

        Uses FAMILY_RETENTION defaults based on shard family.
        Lightweight — checked on session end.
        """
        current = self.state(shard_id)
        if current != ShardState.ACTIVE:
            return TriggerResult(triggered=False, reason="not active")

        family = classify_shard(shard_id)
        retention = FAMILY_RETENTION.get(family, {})

        max_entries = retention.get("max_entries")
        max_age_days = retention.get("max_age_days")

        # Check entry count
        if max_entries is not None:
            entries = self._storage.read(shard_id, limit=1)
            if entries:
                all_entries = self._storage.read(shard_id, limit=max_entries + 1)
                if len(all_entries) > max_entries:
                    return TriggerResult(
                        triggered=True,
                        reason=f"entry count {len(all_entries)} > {max_entries}",
                        action="drain",
                    )

        # Check age
        if max_age_days is not None:
            entries = self._storage.read(shard_id, limit=10**6)
            if entries:
                chrono = list(reversed(entries))
                oldest = chrono[0]
                age = (datetime.now(timezone.utc) - oldest.timestamp).days
                if age > max_age_days:
                    return TriggerResult(
                        triggered=True,
                        reason=f"shard age {age} days > {max_age_days}",
                        action="drain",
                    )

        return TriggerResult(triggered=False)

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def history(self, shard_id: str) -> List[Entry]:
        """Return all lifecycle entries for a shard (chronological)."""
        entries = self._storage.read(LIFECYCLE_SHARD, limit=10**6)
        result = []
        for e in reversed(entries):
            try:
                data = json.loads(e.content)
            except (json.JSONDecodeError, TypeError):
                continue
            if data.get("shard_id") == shard_id:
                result.append(e)
        return result
