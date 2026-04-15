"""Read-only data access for the dashboard.

Primary source: `events.jsonl` — has full payloads, always authoritative.
Secondary source: `index.sqlite3` — fast lookups (used lightly here).

Never writes.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Optional


def _read_events_file(events_path: Path) -> list[dict]:
    if not events_path.exists():
        return []
    out: list[dict] = []
    with events_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


class DashboardReader:
    """All read logic in one place. Zero writes."""

    def __init__(self, data_dir: Path | str):
        self.data_dir = Path(data_dir)
        self.events_path = self.data_dir / "events.jsonl"
        self.db_path = self.data_dir / "index.sqlite3"

    # ── Raw event access ─────────────────────────────────────────────────

    def _all_events(self) -> list[dict]:
        return _read_events_file(self.events_path)

    def recent_events(self, limit: int = 50) -> list[dict]:
        events = self._all_events()
        sliced = events[-limit:] if limit > 0 else events
        return list(reversed(sliced))  # newest first

    # ── Missions ─────────────────────────────────────────────────────────

    def list_missions(self) -> list[dict]:
        """Return a list of mission summaries.

        Built from events.jsonl: each `mission_created` event seeds a row,
        task/result events bump counters, `mission_closed` flips status.
        Enriched with `agents_count` (distinct agents who submitted) and
        `last_event_at` (timestamp of the most recent mission-scoped event).
        """
        events = self._all_events()
        missions: dict[str, dict] = {}
        mission_agents: dict[str, set[str]] = {}

        for ev in events:
            et = ev.get("event_type")
            payload = ev.get("payload") or {}
            ts = ev.get("timestamp") or ""
            scope = ev.get("scope_id") or ""

            if et == "mission_created":
                mid = payload.get("mission_id")
                if mid:
                    missions[mid] = {
                        "mission_id": mid,
                        "title": payload.get("title", ""),
                        "description": payload.get("description", ""),
                        "status": "open",
                        "created_at": ts,
                        "closed_at": None,
                        "task_count": 0,
                        "result_count": 0,
                        "agents_count": 0,
                        "last_event_at": ts,
                    }
                    mission_agents.setdefault(mid, set())
            elif et == "mission_closed":
                mid = payload.get("mission_id")
                if mid and mid in missions:
                    missions[mid]["status"] = "closed"
                    missions[mid]["closed_at"] = ts
            elif et == "task_created":
                mid = payload.get("mission_id")
                if mid and mid in missions:
                    missions[mid]["task_count"] += 1
            elif et == "task_result_submitted":
                mid = payload.get("mission_id")
                if mid and mid in missions:
                    missions[mid]["result_count"] += 1
                    aid = payload.get("agent_id")
                    if aid:
                        mission_agents.setdefault(mid, set()).add(aid)

            # Track the most recent mission-scoped event timestamp.
            if scope.startswith("mission_"):
                raw_mid = scope[len("mission_"):]
                if raw_mid in missions:
                    cur = missions[raw_mid].get("last_event_at") or ""
                    if ts > cur:
                        missions[raw_mid]["last_event_at"] = ts

        for mid, m in missions.items():
            m["agents_count"] = len(mission_agents.get(mid, set()))

        return sorted(
            missions.values(),
            key=lambda m: m.get("created_at") or "",
            reverse=True,
        )

    def get_mission_detail(self, mission_id: str) -> Optional[dict]:
        """Return a single mission with tasks, results, and events.

        Returns None if the mission is not found.
        """
        events = self._all_events()
        scope_id = f"mission_{mission_id}"
        mission_events = [e for e in events if e.get("scope_id") == scope_id]
        if not mission_events:
            return None

        mission_info: Optional[dict] = None
        tasks: dict[str, dict] = {}

        for ev in mission_events:
            et = ev.get("event_type")
            payload = ev.get("payload") or {}

            if et == "mission_created":
                mission_info = {
                    "mission_id": mission_id,
                    "title": payload.get("title", ""),
                    "description": payload.get("description", ""),
                    "status": "open",
                    "created_at": ev.get("timestamp"),
                    "closed_at": None,
                }
            elif et == "mission_closed":
                if mission_info is not None:
                    mission_info["status"] = "closed"
                    mission_info["closed_at"] = ev.get("timestamp")
            elif et == "task_created":
                tid = payload.get("task_id")
                if tid:
                    task_payload = payload.get("payload") or {}
                    tasks[tid] = {
                        "task_id": tid,
                        "task_type": payload.get("task_type", ""),
                        "objective": task_payload.get("objective", ""),
                        "required_capabilities": task_payload.get(
                            "required_capabilities", []
                        ),
                        "created_at": ev.get("timestamp"),
                        "assigned_to": None,
                        "assigned_at": None,
                        "results": [],
                    }
            elif et == "task_assigned":
                tid = payload.get("task_id")
                if tid and tid in tasks:
                    tasks[tid]["assigned_to"] = payload.get("assigned_to")
                    tasks[tid]["assigned_at"] = ev.get("timestamp")
            elif et == "task_result_submitted":
                tid = payload.get("task_id")
                if tid and tid in tasks:
                    tasks[tid]["results"].append(
                        {
                            "agent_id": payload.get("agent_id"),
                            "contribution_id": payload.get("contribution_id"),
                            "content": payload.get("content"),
                            "content_hash": payload.get("content_hash"),
                            "signature": payload.get("signature"),
                            "self_reported_confidence": payload.get(
                                "self_reported_confidence"
                            ),
                            "created_at": payload.get("created_at"),
                            "submitted_at": ev.get("timestamp"),
                            "signature_valid": self._verify_result_signature(payload),
                        }
                    )

        if mission_info is None:
            # We found scope events but no mission_created — treat as absent.
            return None

        mission_info["tasks"] = sorted(
            tasks.values(), key=lambda t: t.get("created_at") or ""
        )
        mission_info["events"] = [
            {
                "event_id": e.get("event_id"),
                "event_type": e.get("event_type"),
                "timestamp": e.get("timestamp"),
                "source_type": e.get("source_type"),
                "source_id": e.get("source_id"),
            }
            for e in mission_events
        ]
        return mission_info

    def _verify_result_signature(self, payload: dict) -> Optional[bool]:
        """Verify a task_result_submitted signature.

        Returns:
            True  — signature verifies
            False — signature does not verify
            None  — cannot verify (missing key, import error, etc.)
        """
        try:
            from agent_mesh.adapters.daryl_adapter.signing import (
                canonicalize_payload,
                verify_bytes,
            )
        except Exception:
            return None

        agent_id = payload.get("agent_id")
        signature = payload.get("signature")
        if not agent_id or not signature:
            return None

        agent = self.get_agent(agent_id)
        if agent is None or not agent.get("public_key"):
            return None

        signable = {
            "schema_version": "signing.v1",
            "agent_id": agent_id,
            "key_id": agent.get("key_id", ""),
            "mission_id": payload.get("mission_id"),
            "task_id": payload.get("task_id"),
            "contribution_id": payload.get("contribution_id"),
            "contribution_type": "task_result",
            "content_hash": payload.get("content_hash"),
            "created_at": payload.get("created_at"),
        }
        try:
            canonical = canonicalize_payload(signable)
            return verify_bytes(canonical, signature, agent["public_key"])
        except Exception:
            return None

    # ── Agents ───────────────────────────────────────────────────────────

    def list_agents(self) -> list[dict]:
        """Return a list of agents reconstructed from registration events."""
        events = self._all_events()
        agents: dict[str, dict] = {}
        for ev in events:
            et = ev.get("event_type")
            payload = ev.get("payload") or {}

            if et == "agent_registered":
                aid = payload.get("agent_id")
                if aid:
                    agents[aid] = {
                        "agent_id": aid,
                        "agent_type": payload.get("agent_type", ""),
                        "capabilities": payload.get("capabilities", []),
                        "public_key": payload.get("public_key", ""),
                        "key_id": payload.get("key_id", ""),
                        "status": "active",
                        "registered_at": ev.get("timestamp"),
                    }
            elif et == "agent_status_changed":
                aid = payload.get("agent_id")
                if aid and aid in agents:
                    agents[aid]["status"] = payload.get(
                        "status", agents[aid]["status"]
                    )
            elif et == "agent_key_rotated":
                aid = payload.get("agent_id")
                if aid and aid in agents:
                    agents[aid]["public_key"] = payload.get(
                        "new_public_key", agents[aid]["public_key"]
                    )
                    agents[aid]["key_id"] = payload.get(
                        "new_key_id", agents[aid]["key_id"]
                    )
        return sorted(agents.values(), key=lambda a: a["agent_id"])

    def get_agent(self, agent_id: str) -> Optional[dict]:
        for a in self.list_agents():
            if a["agent_id"] == agent_id:
                return a
        return None

    # ── Tasks ────────────────────────────────────────────────────────────

    def _build_tasks(self) -> dict[str, dict]:
        """Internal: reconstruct all tasks from events, keyed by task_id.

        Captures everything needed by both the list view and the detail view:
        full objective, submissions with signature verification, assigned agent,
        status (pending / submitted / validated), and receipt_id if present in
        any submission payload.
        """
        events = self._all_events()
        tasks: dict[str, dict] = {}
        validated_task_ids: set[str] = set()

        for ev in events:
            et = ev.get("event_type")
            payload = ev.get("payload") or {}

            if et == "task_created":
                tid = payload.get("task_id")
                if not tid:
                    continue
                task_payload = payload.get("payload") or {}
                tasks[tid] = {
                    "task_id": tid,
                    "mission_id": payload.get("mission_id"),
                    "task_type": payload.get("task_type", ""),
                    "objective": task_payload.get("objective", ""),
                    "required_capabilities": task_payload.get(
                        "required_capabilities", []
                    ),
                    "constraints": task_payload.get("constraints", {}),
                    "assigned_to": None,
                    "assigned_at": None,
                    "created_at": ev.get("timestamp"),
                    "submissions": [],
                    "status": "pending",
                    "receipt_id": None,
                }
            elif et == "task_assigned":
                tid = payload.get("task_id")
                if tid and tid in tasks:
                    tasks[tid]["assigned_to"] = payload.get("assigned_to")
                    tasks[tid]["assigned_at"] = ev.get("timestamp")
            elif et == "task_result_submitted":
                tid = payload.get("task_id")
                if tid and tid in tasks:
                    sub = {
                        "agent_id": payload.get("agent_id"),
                        "contribution_id": payload.get("contribution_id"),
                        "content": payload.get("content"),
                        "content_hash": payload.get("content_hash"),
                        "signature": payload.get("signature"),
                        "self_reported_confidence": payload.get(
                            "self_reported_confidence"
                        ),
                        "created_at": payload.get("created_at"),
                        "submitted_at": ev.get("timestamp"),
                        "event_id": ev.get("event_id"),
                        "receipt_id": payload.get("receipt_id"),
                        "signature_valid": self._verify_result_signature(payload),
                    }
                    tasks[tid]["submissions"].append(sub)
                    # If any submission payload carries a receipt_id, remember it.
                    if sub["receipt_id"] and not tasks[tid]["receipt_id"]:
                        tasks[tid]["receipt_id"] = sub["receipt_id"]
            elif et == "validation_completed":
                tid = payload.get("task_id")
                if tid:
                    validated_task_ids.add(tid)

        # Compute status from the submission set + validation events.
        for tid, t in tasks.items():
            if tid in validated_task_ids:
                t["status"] = "validated"
            elif t["submissions"]:
                t["status"] = "submitted"
            else:
                t["status"] = "pending"

        return tasks

    def list_tasks(self) -> list[dict]:
        """Return all tasks with list-view metadata, newest first."""
        raw = self._build_tasks()
        out: list[dict] = []
        for t in raw.values():
            last_at: Optional[str] = None
            for s in t["submissions"]:
                ts = s.get("submitted_at") or ""
                if ts and (last_at is None or ts > last_at):
                    last_at = ts
            out.append(
                {
                    "task_id": t["task_id"],
                    "mission_id": t["mission_id"],
                    "task_type": t["task_type"],
                    "assigned_to": t["assigned_to"],
                    "submissions_count": len(t["submissions"]),
                    "receipt_id": t["receipt_id"],
                    "last_submission_at": last_at,
                    "status": t["status"],
                    "objective": t["objective"],
                    "created_at": t["created_at"],
                }
            )
        return sorted(out, key=lambda x: x.get("created_at") or "", reverse=True)

    def get_task_detail(self, task_id: str) -> Optional[dict]:
        """Return a full task with all submissions and verification info."""
        return self._build_tasks().get(task_id)

    # ── Mission compare ──────────────────────────────────────────────────

    def compare_mission_results(self, mission_id: str) -> Optional[dict]:
        """Return mission submissions grouped by task, ready for a compare view.

        Each task carries its submissions list and a `comparable` flag that
        flips true as soon as at least two submissions exist for the task.
        Returns None if the mission does not exist.
        """
        all_missions = self.list_missions()
        mission = next(
            (m for m in all_missions if m["mission_id"] == mission_id), None
        )
        if mission is None:
            return None

        raw_tasks = self._build_tasks()
        tasks_for_mission = [
            t for t in raw_tasks.values() if t.get("mission_id") == mission_id
        ]
        tasks_for_mission.sort(key=lambda t: t.get("created_at") or "")

        compare_tasks: list[dict] = []
        for t in tasks_for_mission:
            compare_tasks.append(
                {
                    "task_id": t["task_id"],
                    "task_type": t.get("task_type"),
                    "objective": t.get("objective"),
                    "assigned_to": t.get("assigned_to"),
                    "status": t.get("status"),
                    "submissions_count": len(t["submissions"]),
                    "comparable": len(t["submissions"]) >= 2,
                    "submissions": t["submissions"],
                }
            )

        return {
            "mission_id": mission_id,
            "title": mission.get("title", ""),
            "status": mission.get("status", "open"),
            "tasks": compare_tasks,
        }

    # ── Event detail ─────────────────────────────────────────────────────

    def get_event(self, event_id: str) -> Optional[dict]:
        """Return a full raw event (including payload, auth, links) by id."""
        if not event_id:
            return None
        for ev in self._all_events():
            if ev.get("event_id") == event_id:
                return ev
        return None

    # ── SQLite probe (optional, used only if present) ────────────────────

    def sqlite_event_count(self) -> Optional[int]:
        """Quick sanity probe against the SQLite index. Returns None if missing."""
        if not self.db_path.exists():
            return None
        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
            try:
                cur = conn.execute("SELECT COUNT(*) FROM events")
                row = cur.fetchone()
                return int(row[0]) if row else 0
            finally:
                conn.close()
        except Exception:
            return None
