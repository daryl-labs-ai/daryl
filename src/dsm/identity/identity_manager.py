"""Identity event writer — genesis and evolution events on shard `identity`."""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from ..core.models import Entry
from ..core.storage import Storage


class IdentityManager:
    SHARD = "identity"
    VALID_EVENT_TYPES = {
        "genesis",
        "skill_added",
        "skill_removed",
        "model_change",
        "config_change",
        "behavior_change",
        "capability_declared",
    }

    def __init__(
        self,
        storage: Storage,
        agent_id: str,
        session_id: str = "identity",
    ):
        self._storage = storage
        self._agent_id = agent_id
        self._session_id = session_id
        self._identity_version = 0

    @property
    def identity_version(self) -> int:
        return self._identity_version

    def create_genesis(
        self,
        purpose: str,
        capabilities: List[str],
        constraints: List[str],
        created_by: str,
        **extra: Any,
    ) -> Entry:
        entries = self._storage.read(self.SHARD, offset=0, limit=10000)
        for entry in entries:
            try:
                data = json.loads(entry.content)
            except (json.JSONDecodeError, TypeError):
                continue
            if (
                data.get("event_type") == "genesis"
                and data.get("agent_id") == self._agent_id
            ):
                raise ValueError(
                    f"Genesis already exists for agent {self._agent_id}"
                )

        content: Dict[str, Any] = {
            "agent_id": self._agent_id,
            "event_type": "genesis",
            "event_version": "1.0",
            "origin_component": "identity_manager",
            "identity_version": 1,
            "payload": {
                "created_by": created_by,
                "purpose": purpose,
                "initial_capabilities": list(capabilities),
                "constraints": list(constraints),
                **extra,
            },
        }
        entry = Entry(
            id=str(uuid4()),
            timestamp=datetime.now(timezone.utc),
            session_id=self._session_id,
            source="identity_manager",
            content=json.dumps(content, sort_keys=True, separators=(",", ":")),
            shard=self.SHARD,
            hash="",
            prev_hash=None,
            metadata={"event_type": "genesis", "agent_id": self._agent_id},
            version="v2.0",
        )
        self._storage.append(entry)
        self._identity_version = 1
        return entry

    def append_event(
        self,
        event_type: str,
        payload: Dict[str, Any],
        reason: Optional[str] = None,
    ) -> Entry:
        if event_type not in self.VALID_EVENT_TYPES:
            raise ValueError(f"Invalid event_type: {event_type}")
        if event_type == "genesis":
            raise ValueError("genesis must be created via create_genesis()")

        self._identity_version += 1
        pl = dict(payload)
        if reason is not None:
            pl["reason"] = reason

        content: Dict[str, Any] = {
            "agent_id": self._agent_id,
            "event_type": event_type,
            "event_version": "1.0",
            "origin_component": "identity_manager",
            "identity_version": self._identity_version,
            "payload": pl,
        }
        entry = Entry(
            id=str(uuid4()),
            timestamp=datetime.now(timezone.utc),
            session_id=self._session_id,
            source="identity_manager",
            content=json.dumps(content, sort_keys=True, separators=(",", ":")),
            shard=self.SHARD,
            hash="",
            prev_hash=None,
            metadata={"event_type": event_type, "agent_id": self._agent_id},
            version="v2.0",
        )
        self._storage.append(entry)
        return entry
