"""Heuristic identity continuity checks (v1 stub)."""

import json
from typing import TYPE_CHECKING, Any, Dict, Optional

from ..core.storage import Storage
from .identity_replay import replay_identity

if TYPE_CHECKING:
    from ..signing import AgentSigning


class IdentityGuard:
    """
    Heuristic detection of unverified behavioral discontinuities.
    Best-effort and non-authoritative in v1.
    """

    def __init__(self, storage: Storage, agent_id: str):
        self._storage = storage
        self._agent_id = agent_id

    def check_genesis_exists(self) -> bool:
        entries = self._storage.read("identity", offset=0, limit=100000)
        for entry in entries:
            try:
                data = json.loads(entry.content)
            except (json.JSONDecodeError, TypeError):
                continue
            if (
                data.get("event_type") == "genesis"
                and data.get("agent_id") == self._agent_id
            ):
                return True
        return False

    def check_continuity(self, window: int = 100) -> Dict[str, Any]:
        self._storage.read("sessions", offset=0, limit=window)
        if not self.check_genesis_exists():
            return {
                "status": "no_genesis",
                "agent_id": self._agent_id,
                "identity_version": 0,
                "event_count": 0,
                "message": "No genesis event for this agent",
            }
        state = replay_identity(self._storage, self._agent_id)
        return {
            "status": "consistent",
            "agent_id": self._agent_id,
            "identity_version": state.identity_version,
            "event_count": state.event_count,
            "message": "Identity guard check passed (heuristic, non-authoritative)",
        }

    def check_key_identity_binding(
        self, signing: Optional["AgentSigning"] = None
    ) -> Dict[str, Any]:
        if signing is None or not signing.has_keypair():
            return {"status": "skipped", "reason": "no signing configured"}
        return {"status": "skipped", "reason": "not implemented in v1"}
