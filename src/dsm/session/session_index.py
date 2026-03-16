"""
Session Index (P7).

Persistent, queryable index over session shards.
Enables O(1) session lookup and O(log n) action queries
without replaying the full shard.

The index is DERIVED from the shard — it can be rebuilt anytime.
Trust comes from the shard; speed comes from the index.
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.storage import Storage

logger = logging.getLogger(__name__)


class SessionIndex:
    """
    Queryable index over a DSM shard.

    Index files (JSONL) stored in index_dir/:
      - sessions.jsonl:  one line per session {session_id, source, start_time, end_time, entry_count, entry_ids}
      - actions.jsonl:   one line per action  {action_name, session_id, entry_id, timestamp, success}
      - meta.json:       {shard_id, entries_indexed, sessions_found, built_at}
    """

    def __init__(self, index_dir: str, shard_id: str = "sessions"):
        self.index_dir = Path(index_dir)
        self.shard_id = shard_id
        self._sessions: Dict[str, Dict] = {}  # session_id -> metadata
        self._actions: List[Dict] = []  # flat list, sorted by timestamp
        self._meta: Dict[str, Any] = {}
        self._load_if_exists()

    # --- Build ---

    def build_from_storage(self, storage: Storage) -> Dict[str, Any]:
        """
        Scan entire shard and build index from scratch.

        Returns: {"status": "OK", "entries_indexed": N, "sessions_found": M, "duration_seconds": float}
        """
        t0 = time.monotonic()
        entries = storage.read(self.shard_id, limit=10**7)

        sessions: Dict[str, Dict] = {}
        actions: List[Dict] = []

        for entry in entries:
            sid = entry.session_id or "unknown"
            meta = entry.metadata or {}
            event_type = meta.get("event_type", "")
            ts = entry.timestamp.isoformat() if isinstance(entry.timestamp, datetime) else str(entry.timestamp)

            # Track session
            if sid not in sessions:
                sessions[sid] = {
                    "session_id": sid,
                    "source": entry.source or "",
                    "start_time": ts,
                    "end_time": ts,
                    "entry_count": 0,
                    "entry_ids": [],
                    "actions": {},
                }
            sess = sessions[sid]
            sess["entry_count"] += 1
            sess["entry_ids"].append(entry.id)
            # Update time bounds
            if ts < sess["start_time"]:
                sess["start_time"] = ts
            if ts > sess["end_time"]:
                sess["end_time"] = ts

            # Track actions (tool_call or any entry with action_name)
            action_name = meta.get("action_name")
            if action_name or event_type == "tool_call":
                aname = action_name or "unknown"
                success = meta.get("success", True)
                actions.append({
                    "action_name": aname,
                    "session_id": sid,
                    "entry_id": entry.id,
                    "timestamp": ts,
                    "success": bool(success),
                })
                sess["actions"][aname] = sess["actions"].get(aname, 0) + 1

        # Sort actions by timestamp
        actions.sort(key=lambda a: a["timestamp"])

        # Persist
        self.index_dir.mkdir(parents=True, exist_ok=True)

        with open(self.index_dir / "sessions.jsonl", "w", encoding="utf-8") as f:
            for sess in sessions.values():
                record = {**sess, "actions": [{"name": k, "count": v} for k, v in sess["actions"].items()]}
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        with open(self.index_dir / "actions.jsonl", "w", encoding="utf-8") as f:
            for act in actions:
                f.write(json.dumps(act, ensure_ascii=False) + "\n")

        duration = time.monotonic() - t0
        self._meta = {
            "shard_id": self.shard_id,
            "entries_indexed": len(entries),
            "sessions_found": len(sessions),
            "built_at": datetime.now(timezone.utc).isoformat() + "Z",
        }
        with open(self.index_dir / "meta.json", "w", encoding="utf-8") as f:
            json.dump(self._meta, f, ensure_ascii=False)

        self._sessions = sessions
        self._actions = actions

        return {
            "status": "OK",
            "entries_indexed": len(entries),
            "sessions_found": len(sessions),
            "duration_seconds": round(duration, 4),
        }

    # --- Query ---

    def find_session(self, session_id: str) -> Optional[Dict]:
        """
        Quick O(1) lookup for session metadata.

        Returns dict with session_id, source, start_time, end_time,
        entry_count, entry_ids, actions — or None if not found.
        """
        sess = self._sessions.get(session_id)
        if not sess:
            return None
        actions_list = sess.get("actions", {})
        if isinstance(actions_list, dict):
            actions_list = [{"name": k, "count": v} for k, v in actions_list.items()]
        return {
            "session_id": sess["session_id"],
            "source": sess.get("source", ""),
            "start_time": sess.get("start_time", ""),
            "end_time": sess.get("end_time", ""),
            "entry_count": sess.get("entry_count", 0),
            "entry_ids": sess.get("entry_ids", []),
            "actions": actions_list,
        }

    def get_actions(
        self,
        action_name: Optional[str] = None,
        session_id: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """
        Query actions with optional filters. All filters are AND-combined.
        Returns list of action dicts sorted by timestamp.
        """
        results = []
        for act in self._actions:
            if action_name and act["action_name"] != action_name:
                continue
            if session_id and act["session_id"] != session_id:
                continue
            if start_time and act["timestamp"] < start_time:
                continue
            if end_time and act["timestamp"] > end_time:
                continue
            results.append(act)
            if len(results) >= limit:
                break
        return results

    def list_sessions(self, limit: int = 50) -> List[Dict]:
        """List all sessions, most recent first."""
        sessions = []
        for sess in self._sessions.values():
            actions_list = sess.get("actions", {})
            if isinstance(actions_list, dict):
                actions_list = [{"name": k, "count": v} for k, v in actions_list.items()]
            sessions.append({
                "session_id": sess["session_id"],
                "source": sess.get("source", ""),
                "start_time": sess.get("start_time", ""),
                "end_time": sess.get("end_time", ""),
                "entry_count": sess.get("entry_count", 0),
            })
        sessions.sort(key=lambda s: s.get("end_time", ""), reverse=True)
        return sessions[:limit]

    def is_consistent(self, storage: Storage) -> bool:
        """
        Check if index matches shard state by comparing entry counts.
        Returns True if consistent, False if rebuild needed.
        """
        entries = storage.read(self.shard_id, limit=10**7)
        return len(entries) == self._meta.get("entries_indexed", -1)

    # --- Internal ---

    def _load_if_exists(self) -> None:
        """Load index from disk if it exists."""
        meta_path = self.index_dir / "meta.json"
        if not meta_path.exists():
            return

        try:
            with open(meta_path, encoding="utf-8") as f:
                self._meta = json.load(f)
        except (json.JSONDecodeError, OSError):
            return

        sessions_path = self.index_dir / "sessions.jsonl"
        if sessions_path.exists():
            with open(sessions_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    actions = rec.get("actions", [])
                    if isinstance(actions, list):
                        rec["actions"] = {a["name"]: a["count"] for a in actions}
                    self._sessions[rec["session_id"]] = rec

        actions_path = self.index_dir / "actions.jsonl"
        if actions_path.exists():
            with open(actions_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    self._actions.append(json.loads(line))
