"""
Sovereignty Policy — pre-execution access control for the collective.

Manages who can contribute, what types are allowed, trust thresholds,
and human approval workflows. Shard: `sovereignty_policies`.

Design:
- set is append-only (latest supersedes, full history preserved)
- get uses a lazy in-memory index, O(1) after first call
- allows is a pure function: receives everything, returns result, never raises
- Deny by default — no policy = no access
- Complementary to audit.py (post-hoc) — sovereignty is pre-execution
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .core.models import Entry
from .core.storage import Storage
from .exceptions import InvalidPolicyStructure
from .identity.identity_registry import IdentityRegistry

logger = logging.getLogger(__name__)

SOVEREIGNTY_SHARD = "sovereignty_policies"

# Required keys in a policy dict
_REQUIRED_POLICY_KEYS = {"agents", "min_trust_score", "allowed_types"}

# Known entry types (extensible — used for validation warnings, not hard block)
_KNOWN_ENTRY_TYPES = {
    "observation", "decision", "action", "snapshot", "system",
    "start_session", "end_session", "execute_action",
}


def _validate_policy(policy: dict) -> List[str]:
    """Validate policy structure and types. Returns list of errors (empty = valid).

    Checks:
    - Required keys present
    - agents: must be a list/tuple of non-empty strings
    - min_trust_score: must be a number in [0.0, 1.0]
    - allowed_types: must be a list/tuple of non-empty strings
    - trust_baseline: if present, must be a number in [0.0, 1.0]
    - approval_required: if present, must be a list/tuple of strings
    - cross_ai: if present, must be a boolean
    """
    errors = []

    # Required keys
    missing = _REQUIRED_POLICY_KEYS - set(policy.keys())
    if missing:
        errors.append(f"Missing required keys: {sorted(missing)}")
        return errors  # can't validate further

    # agents
    agents = policy["agents"]
    if not isinstance(agents, (list, tuple)):
        errors.append(f"'agents' must be a list, got {type(agents).__name__}")
    elif len(agents) == 0:
        errors.append("'agents' must not be empty")
    elif not all(isinstance(a, str) and a.strip() for a in agents):
        errors.append("'agents' must contain non-empty strings")

    # min_trust_score
    mts = policy["min_trust_score"]
    if not isinstance(mts, (int, float)):
        errors.append(f"'min_trust_score' must be a number, got {type(mts).__name__}")
    elif not (0.0 <= float(mts) <= 1.0):
        errors.append(f"'min_trust_score' must be in [0.0, 1.0], got {mts}")

    # allowed_types
    at = policy["allowed_types"]
    if not isinstance(at, (list, tuple)):
        errors.append(f"'allowed_types' must be a list, got {type(at).__name__}")
    elif len(at) == 0:
        errors.append("'allowed_types' must not be empty")
    elif not all(isinstance(t, str) and t.strip() for t in at):
        errors.append("'allowed_types' must contain non-empty strings")

    # trust_baseline (optional)
    if "trust_baseline" in policy:
        tb = policy["trust_baseline"]
        if not isinstance(tb, (int, float)):
            errors.append(f"'trust_baseline' must be a number, got {type(tb).__name__}")
        elif not (0.0 <= float(tb) <= 1.0):
            errors.append(f"'trust_baseline' must be in [0.0, 1.0], got {tb}")

    # approval_required (optional)
    if "approval_required" in policy:
        ar = policy["approval_required"]
        if not isinstance(ar, (list, tuple)):
            errors.append(f"'approval_required' must be a list, got {type(ar).__name__}")

    # cross_ai (optional)
    if "cross_ai" in policy:
        ca = policy["cross_ai"]
        if not isinstance(ca, bool):
            errors.append(f"'cross_ai' must be a boolean, got {type(ca).__name__}")

    return errors


@dataclass(frozen=True)
class PolicySnapshot:
    """Immutable snapshot of a sovereignty policy."""
    owner_id: str
    agents: tuple                  # whitelist of agent_ids (tuple for frozen)
    min_trust_score: float         # threshold from A
    trust_baseline: float          # initial trust for newly registered agents
    allowed_types: tuple           # which entry types can enter collective
    approval_required: tuple       # types needing human approval
    cross_ai: bool                 # allow multi-model contributions
    set_at: datetime
    entry_hash: str                # link to shard truth


@dataclass(frozen=True)
class EnforcementResult:
    """Result of a sovereignty enforcement check. Never raises."""
    verdict: str       # "allow" | "deny" | "pending"
    reason: Optional[str] = None
    detail: Any = field(default=None, hash=False, compare=False)

    @property
    def allowed(self) -> bool:
        return self.verdict == "allow"

    @classmethod
    def allow(cls) -> "EnforcementResult":
        return cls(verdict="allow")

    @classmethod
    def deny(cls, reason: str, detail: Any = None) -> "EnforcementResult":
        return cls(verdict="deny", reason=reason, detail=detail)

    @classmethod
    def pending(cls, reason: str) -> "EnforcementResult":
        return cls(verdict="pending", reason=reason)


class SovereigntyPolicy:
    """Pre-execution sovereignty policy backed by DSM shard.

    All mutations are append-only entries. Read operations use a lazy
    in-memory index rebuilt on first access and invalidated on new entry.
    """

    def __init__(self, storage: Storage):
        self._storage = storage
        # Lazy index: owner_id -> policy dict
        self._index: Optional[Dict[str, dict]] = None

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    def _invalidate_index(self) -> None:
        self._index = None

    def _ensure_index(self) -> Dict[str, dict]:
        """Build or return cached index. Called once, then O(1) via cache.

        Reads full shard on first call. This is acceptable because:
        - Sovereignty shard is small (one entry per policy set/revoke)
        - A system with 10K policy changes is extreme — typically < 100
        - Index is cached and invalidated only on write (set/revoke)
        """
        if self._index is not None:
            return self._index

        entries = self._storage.read(SOVEREIGNTY_SHARD, limit=10**6)
        index: Dict[str, dict] = {}

        # oldest-first so latest-wins
        for entry in reversed(entries):
            try:
                data = json.loads(entry.content)
            except (json.JSONDecodeError, TypeError):
                continue

            event_type = data.get("event_type")
            owner_id = data.get("owner_id")
            if not owner_id:
                continue

            if event_type == "set_policy":
                policy = data.get("policy", {})
                index[owner_id] = {
                    "owner_id": owner_id,
                    "agents": tuple(policy.get("agents", [])),
                    "min_trust_score": float(policy.get("min_trust_score", 0.5)),
                    "trust_baseline": float(policy.get("trust_baseline", 0.5)),
                    "allowed_types": tuple(policy.get("allowed_types", [])),
                    "approval_required": tuple(policy.get("approval_required", [])),
                    "cross_ai": bool(policy.get("cross_ai", False)),
                    "set_at": entry.timestamp,
                    "entry_hash": entry.hash or "",
                    "revoked": False,
                }
            elif event_type == "revoke_policy":
                if owner_id in index:
                    index[owner_id]["revoked"] = True

        self._index = index
        return index

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def set(
        self,
        owner_id: str,
        owner_signature: str,
        policy: dict,
    ) -> Entry:
        """Set a sovereignty policy. Append-only — supersedes any previous.

        Args:
            owner_id: Human sovereign identifier
            owner_signature: Proof of ownership
            policy: Dict with keys: agents, min_trust_score, allowed_types,
                    and optionally: trust_baseline, approval_required, cross_ai

        Raises:
            InvalidPolicyStructure: If required keys are missing
        """
        errors = _validate_policy(policy)
        if errors:
            raise InvalidPolicyStructure(
                f"Invalid policy: {'; '.join(errors)}"
            )

        content = json.dumps({
            "event_type": "set_policy",
            "owner_id": owner_id,
            "owner_signature": owner_signature,
            "policy": {
                "agents": list(policy["agents"]),
                "min_trust_score": float(policy["min_trust_score"]),
                "trust_baseline": float(policy.get("trust_baseline", 0.5)),
                "allowed_types": list(policy["allowed_types"]),
                "approval_required": list(policy.get("approval_required", [])),
                "cross_ai": bool(policy.get("cross_ai", False)),
            },
        }, sort_keys=True, separators=(",", ":"))

        entry = Entry(
            id=str(uuid4()),
            timestamp=datetime.now(timezone.utc),
            session_id="sovereignty",
            source="sovereignty",
            content=content,
            shard=SOVEREIGNTY_SHARD,
            hash="",
            prev_hash=None,
            metadata={"event_type": "set_policy", "owner_id": owner_id},
            version="v2.0",
        )
        result = self._storage.append(entry)
        self._invalidate_index()
        logger.info("Policy set for owner %s", owner_id)
        return result

    def revoke(
        self,
        owner_id: str,
        owner_signature: str,
        reason: Optional[str] = None,
    ) -> Entry:
        """Revoke a sovereignty policy. Append-only tombstone."""
        content = json.dumps({
            "event_type": "revoke_policy",
            "owner_id": owner_id,
            "owner_signature": owner_signature,
            "reason": reason,
        }, sort_keys=True, separators=(",", ":"))

        entry = Entry(
            id=str(uuid4()),
            timestamp=datetime.now(timezone.utc),
            session_id="sovereignty",
            source="sovereignty",
            content=content,
            shard=SOVEREIGNTY_SHARD,
            hash="",
            prev_hash=None,
            metadata={"event_type": "revoke_policy", "owner_id": owner_id},
            version="v2.0",
        )
        result = self._storage.append(entry)
        self._invalidate_index()
        logger.info("Policy revoked for owner %s (reason: %s)", owner_id, reason)
        return result

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, owner_id: str) -> Optional[PolicySnapshot]:
        """Get the active policy for an owner. O(1) via lazy index.

        Returns None if no policy or policy is revoked.
        """
        index = self._ensure_index()
        rec = index.get(owner_id)
        if rec is None or rec["revoked"]:
            return None

        return PolicySnapshot(
            owner_id=rec["owner_id"],
            agents=rec["agents"],
            min_trust_score=rec["min_trust_score"],
            trust_baseline=rec["trust_baseline"],
            allowed_types=rec["allowed_types"],
            approval_required=rec["approval_required"],
            cross_ai=rec["cross_ai"],
            set_at=rec["set_at"],
            entry_hash=rec["entry_hash"],
        )

    def history(self, owner_id: str, limit: int = 1000) -> List[Entry]:
        """Return all policy entries for an owner (chronological).

        Args:
            owner_id: Owner to filter by
            limit: Max entries to scan (default 1000, avoids loading entire shard)
        """
        entries = self._storage.read(SOVEREIGNTY_SHARD, limit=limit)
        result = []
        for e in reversed(entries):
            try:
                data = json.loads(e.content)
            except (json.JSONDecodeError, TypeError):
                continue
            if data.get("owner_id") == owner_id:
                result.append(e)
        return result

    # ------------------------------------------------------------------
    # Enforcement — pure function, never raises
    # ------------------------------------------------------------------

    def allows(
        self,
        owner_id: str,
        agent_id: str,
        entry_type: str,
        identity: IdentityRegistry,
        agent_model: Optional[str] = None,
    ) -> EnforcementResult:
        """Check if an agent is allowed to contribute an entry type.

        Pure function: receives everything it needs, returns explicit result.
        Short-circuits on first denial. Never raises.

        Check order:
        1. Policy exists for owner
        2. Agent in whitelist
        3. Trust score >= min_trust_score
        4. Entry type in allowed_types
        5. Cross-AI check (if agent is a different model)
        6. Approval required check
        """
        # 1. Policy exists
        policy = self.get(owner_id)
        if policy is None:
            return EnforcementResult.deny("no_policy", f"No active policy for {owner_id}")

        # 2. Agent in whitelist
        if agent_id not in policy.agents:
            return EnforcementResult.deny(
                "not_whitelisted",
                f"Agent {agent_id} not in whitelist",
            )

        # 3. Trust score check
        score = identity.trust_score(agent_id)
        if score < policy.min_trust_score:
            return EnforcementResult.deny(
                "low_trust",
                f"Trust {score:.2f} < threshold {policy.min_trust_score:.2f}",
            )

        # 4. Entry type allowed
        if entry_type not in policy.allowed_types:
            return EnforcementResult.deny(
                "type_forbidden",
                f"Entry type '{entry_type}' not in allowed_types",
            )

        # 5. Cross-AI check
        if agent_model and not policy.cross_ai:
            agent_identity = identity.resolve(agent_id)
            if agent_identity and agent_identity.model and agent_identity.model != agent_model:
                return EnforcementResult.deny(
                    "cross_ai_denied",
                    "Cross-AI contributions disabled",
                )

        # 6. Approval required
        if entry_type in policy.approval_required:
            return EnforcementResult.pending(
                f"Entry type '{entry_type}' requires human approval",
            )

        return EnforcementResult.allow()
