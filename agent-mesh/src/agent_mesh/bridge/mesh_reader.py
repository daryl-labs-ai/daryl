"""Mesh state reader — read-only live state extraction."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..index.db import IndexDB
    from ..registry.agent_registry import AgentRegistry


class MeshStateReader:
    def __init__(self, registry: AgentRegistry, index_db: IndexDB) -> None:
        self._registry = registry
        self._index_db = index_db

    async def get_state(self, scope: str) -> dict:
        mission_id = None
        open_tasks = 0
        assigned_agents: list[str] = []
        status = "unknown"

        if scope.startswith("mission:"):
            mission_id = scope.split(":", 1)[1]
            mission = await self._index_db.get_mission(mission_id)
            if mission is not None:
                status = mission.get("status", "unknown")

            db = self._index_db._db
            assert db is not None

            async with db.execute(
                "SELECT COUNT(*) FROM events "
                "WHERE scope_id = ? AND event_type = 'task_created'",
                (f"mission_{mission_id}",),
            ) as cur:
                created_count = (await cur.fetchone())[0]

            async with db.execute(
                "SELECT COUNT(*) FROM events "
                "WHERE scope_id = ? AND event_type = 'task_result_submitted'",
                (f"mission_{mission_id}",),
            ) as cur:
                submitted_count = (await cur.fetchone())[0]

            open_tasks = max(0, created_count - submitted_count)

            async with db.execute(
                "SELECT DISTINCT json_extract(payload_json, '$.assigned_to') "
                "FROM events "
                "WHERE scope_id = ? AND event_type = 'task_assigned' "
                "AND json_extract(payload_json, '$.assigned_to') IS NOT NULL",
                (f"mission_{mission_id}",),
            ) as cur:
                async for row in cur:
                    if row[0]:
                        assigned_agents.append(row[0])

        return {
            "mission_id": mission_id,
            "open_tasks": open_tasks,
            "assigned_agents": assigned_agents,
            "status": status,
        }
