"""SQLite (aiosqlite) index DB."""
from __future__ import annotations

import json
from pathlib import Path

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT,
    scope_type TEXT,
    scope_id TEXT,
    source_id TEXT,
    timestamp TEXT,
    payload_json TEXT,
    entry_hash TEXT
);
CREATE TABLE IF NOT EXISTS agent_runtime (
    agent_id TEXT PRIMARY KEY,
    last_heartbeat TEXT,
    status TEXT,
    current_task_id TEXT
);
CREATE TABLE IF NOT EXISTS missions (
    mission_id TEXT PRIMARY KEY,
    status TEXT,
    created_at TEXT,
    closed_at TEXT
);
"""


class IndexDB:
    def __init__(self, data_dir: Path):
        self._path = Path(data_dir) / "index.sqlite3"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        self._db = await aiosqlite.connect(str(self._path))
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def index_event(self, event: dict, entry_hash: str) -> None:
        assert self._db is not None
        await self._db.execute(
            "INSERT OR REPLACE INTO events "
            "(event_id, event_type, scope_type, scope_id, source_id, timestamp, payload_json, entry_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event["event_id"],
                event["event_type"],
                event["scope_type"],
                event["scope_id"],
                event["source_id"],
                event["timestamp"],
                json.dumps(event.get("payload", {})),
                entry_hash,
            ),
        )
        await self._db.commit()

    async def get_event(self, event_id: str) -> dict | None:
        assert self._db is not None
        async with self._db.execute(
            "SELECT event_id, event_type, scope_type, scope_id, source_id, timestamp, payload_json, entry_hash "
            "FROM events WHERE event_id = ?",
            (event_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return {
            "event_id": row[0],
            "event_type": row[1],
            "scope_type": row[2],
            "scope_id": row[3],
            "source_id": row[4],
            "timestamp": row[5],
            "payload": json.loads(row[6]) if row[6] else {},
            "entry_hash": row[7],
        }

    async def update_agent_runtime(
        self,
        agent_id: str,
        last_heartbeat: str | None,
        status: str,
        current_task_id: str | None,
    ) -> None:
        assert self._db is not None
        await self._db.execute(
            "INSERT OR REPLACE INTO agent_runtime "
            "(agent_id, last_heartbeat, status, current_task_id) VALUES (?, ?, ?, ?)",
            (agent_id, last_heartbeat, status, current_task_id),
        )
        await self._db.commit()

    async def create_mission(self, mission_id: str, created_at: str | None = None) -> None:
        assert self._db is not None
        await self._db.execute(
            "INSERT OR REPLACE INTO missions (mission_id, status, created_at, closed_at) "
            "VALUES (?, 'open', ?, NULL)",
            (mission_id, created_at or ""),
        )
        await self._db.commit()

    async def close_mission(self, mission_id: str, closed_at: str | None = None) -> None:
        assert self._db is not None
        await self._db.execute(
            "UPDATE missions SET status='closed', closed_at=? WHERE mission_id=?",
            (closed_at or "", mission_id),
        )
        await self._db.commit()

    async def get_mission(self, mission_id: str) -> dict | None:
        assert self._db is not None
        async with self._db.execute(
            "SELECT mission_id, status, created_at, closed_at FROM missions WHERE mission_id=?",
            (mission_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return {
            "mission_id": row[0],
            "status": row[1],
            "created_at": row[2],
            "closed_at": row[3],
        }
