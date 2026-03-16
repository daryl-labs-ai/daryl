#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSM v2 - Session Tracking
session_id, provenance, heartbeat tracking
"""

import fcntl
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass, field

@dataclass
class Session:
    """Session DSM v2"""
    id: str                          # UUID de session
    started_at: datetime               # ISO 8601 UTC
    ended_at: Optional[datetime]      # Null si active
    heartbeat_count: int            # Nombre de heartbeats
    entries_count: int              # Nombre d'entrées créées
    stability_score: float          # 0-1 (heuristique)
    shard_hashes: List[str]          # Hashes des shards accédés

@dataclass
class Provenance:
    """Traçabilité d'origine"""
    source_agent: str               # Agent qui a créé l'entrée
    source_session: str             # Session de création
    source_platform: str            # "telegram", "heartbeat", "manual", etc.
    verified: bool                  # Si l'authenticité est vérifiée

class SessionTracker:
    """Gestionnaire de sessions DSM v2"""

    def __init__(self, state_file="data/sessions.json"):
        self.state_file = Path(state_file)
        self.state = self._load_state()

    def _load_state(self) -> dict:
        """Charge l'état des sessions (with shared lock)."""
        if not self.state_file.exists():
            return {"sessions": [], "current_session": None}
        with open(self.state_file, "r", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                return json.load(f)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def _save_state(self):
        """Sauvegarde l'état (with exclusive lock)."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, "w", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                json.dump(self.state, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def start_session(self) -> Session:
        """
        Démarre une nouvelle session

        Returns:
            Session: Nouvelle session
        """
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        session = Session(
            id=session_id,
            started_at=now,
            ended_at=None,
            heartbeat_count=0,
            entries_count=0,
            stability_score=1.0,
            shard_hashes=[]
        )

        self.state["sessions"].append({
            "id": session_id,
            "started_at": now,
            "ended_at": None,
            "heartbeat_count": 0,
            "entries_count": 0,
            "stability_score": 1.0,
            "shard_hashes": []
        })
        self.state["current_session"] = session_id

        self._save_state()
        return session

    def end_session(self, stability_score: float = None) -> Session:
        """
        Termine la session actuelle

        Args:
            stability_score: Score de stabilité (0-1)

        Returns:
            Session: Session terminée
        """
        current_id = self.state.get("current_session")
        if not current_id:
            return None

        # Find session
        session = None
        for s in self.state["sessions"]:
            if s["id"] == current_id:
                session = s
                break

        if not session:
            return None

        # Update session
        now = datetime.now(timezone.utc).isoformat()
        session.ended_at = now
        if stability_score is not None:
            session.stability_score = stability_score

        self.state["current_session"] = None

        self._save_state()
        return session

    def record_heartbeat(self, shard_hashes: List[str] = None) -> Optional[Session]:
        """
        Enregistre un heartbeat

        Args:
            shard_hashes: Hashes des shards accédés pendant ce heartbeat

        Returns:
            Session: Session mise à jour
        """
        current_id = self.state.get("current_session")
        if not current_id:
            return None

        # Find session
        for s in self.state["sessions"]:
            if s["id"] == current_id:
                s["heartbeat_count"] = (s.get("heartbeat_count", 0) + 1)
                s["entries_count"] = s.get("entries_count", 0) + 1
                if shard_hashes:
                    s["shard_hashes"] = list(set(s.get("shard_hashes", []) + shard_hashes))
                s["stability_score"] = min(1.0, s.get("stability_score", 1.0))
                break

        self._save_state()

        # Return updated session
        for s in self.state["sessions"]:
            if s["id"] == current_id:
                return Session(**s)

        return None

    def get_current_session(self) -> Optional[Session]:
        """Récupère la session actuelle"""
        current_id = self.state.get("current_session")
        if not current_id:
            return None

        for s in self.state["sessions"]:
            if s["id"] == current_id:
                return Session(**s)

        return None

    def get_sessions(self, limit: int = 50) -> List[Session]:
        """Récupère les sessions récentes"""
        sessions = self.state.get("sessions", [])
        return sorted(sessions, key=lambda x: x["started_at"], reverse=True)[:limit]
