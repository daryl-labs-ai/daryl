"""DSM context reader — read-only queries against the event index."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..index.db import IndexDB


class DSMContextReader:
    def __init__(self, index_db: IndexDB) -> None:
        self._index_db = index_db

    async def fetch_events(self, scope: str, limit: int) -> list[dict]:
        db = self._index_db._db
        assert db is not None

        if scope.startswith("mission:"):
            mission_id = scope.split(":", 1)[1]
            scope_id = f"mission_{mission_id}"
            sql = (
                "SELECT event_id, event_type, scope_type, scope_id, source_id, "
                "timestamp, payload_json, entry_hash "
                "FROM events WHERE scope_id = ? "
                "ORDER BY timestamp DESC LIMIT ?"
            )
            params = (scope_id, limit)
        elif scope.startswith("agent:"):
            agent_id = scope.split(":", 1)[1]
            sql = (
                "SELECT event_id, event_type, scope_type, scope_id, source_id, "
                "timestamp, payload_json, entry_hash "
                "FROM events WHERE source_id = ? "
                "ORDER BY timestamp DESC LIMIT ?"
            )
            params = (agent_id, limit)
        else:
            sql = (
                "SELECT event_id, event_type, scope_type, scope_id, source_id, "
                "timestamp, payload_json, entry_hash "
                "FROM events ORDER BY timestamp DESC LIMIT ?"
            )
            params = (limit,)

        rows: list[dict] = []
        async with db.execute(sql, params) as cur:
            async for row in cur:
                rows.append({
                    "event_id": row[0],
                    "event_type": row[1],
                    "scope_type": row[2],
                    "scope_id": row[3],
                    "source_id": row[4],
                    "timestamp": row[5],
                    "payload": json.loads(row[6]) if row[6] else {},
                    "entry_hash": row[7],
                })
        return rows
