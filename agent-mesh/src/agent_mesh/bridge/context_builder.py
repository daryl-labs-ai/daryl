"""Context builder — assembles a ContextPack from DSM events and live state."""
from __future__ import annotations

from datetime import datetime, timezone

from ..dsm.ulid import new_event_id
from .dsm_reader import DSMContextReader
from .mesh_reader import MeshStateReader
from .models import ContextFact, ContextPack, ContextQuery, LiveState, ProvenMemory


class ContextBuilder:
    def __init__(self, dsm_reader: DSMContextReader, mesh_reader: MeshStateReader) -> None:
        self._dsm_reader = dsm_reader
        self._mesh_reader = mesh_reader

    async def build(self, query: ContextQuery) -> ContextPack:
        events = await self._dsm_reader.fetch_events(query.scope, query.limit)

        facts = self._extract_facts(events)
        summary = self._build_summary(facts)
        state_dict = await self._mesh_reader.get_state(query.scope)
        live_state = LiveState(
            mission_id=state_dict.get("mission_id"),
            open_tasks=state_dict.get("open_tasks", 0),
            assigned_agents=state_dict.get("assigned_agents", []),
            status=state_dict.get("status", "unknown"),
        )
        source_event_ids = [e["event_id"] for e in events]

        return ContextPack(
            context_id=f"ctx_{new_event_id()}",
            consumer_agent_id=query.consumer_agent_id,
            scope=query.scope,
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            proven_memory=ProvenMemory(summary=summary, facts=facts),
            live_state=live_state,
            source_event_ids=source_event_ids,
            raw_event_count=len(events),
            dsm_event_id=None,
        )

    def _extract_facts(self, events: list[dict]) -> list[ContextFact]:
        facts: list[ContextFact] = []
        for ev in events:
            if ev.get("event_type") != "task_result_submitted":
                continue
            payload = ev.get("payload", {})
            content = payload.get("content", {})
            text = content.get("text", "") if isinstance(content, dict) else str(content)
            if len(text) > 2000:
                text = text[:2000]
            agent_id = payload.get("agent_id", ev.get("source_id", "unknown"))
            facts.append(ContextFact(
                type="submission",
                agent_id=agent_id,
                text=text,
                source_event_ids=[ev["event_id"]],
            ))
        return facts

    def _build_summary(self, facts: list[ContextFact]) -> str:
        if not facts:
            return "No recent activity."
        unique_agents = len({f.agent_id for f in facts})
        return f"{len(facts)} submissions from {unique_agents} agents."
