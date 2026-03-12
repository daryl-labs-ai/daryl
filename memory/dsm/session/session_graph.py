#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSM v2 - Session Graph
Orchestration layer for DSM sessions with lifecycle management and safeguards
"""

import json
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from pathlib import Path

from .session_limits_manager import SessionLimitsManager
from ..core.storage import Storage
from ..core.models import Entry


class SessionGraph:
    """
    Gestionnaire du graphe de session DSM v2
    
    Orchestrates the complete session lifecycle:
    - start_session(source) → session_start event
    - record_snapshot(data) → snapshot event (with cooldown check)
    - execute_action(name, payload) → tool_call event (with limits check)
    - end_session() → session_end event
    """
    
    def __init__(self, storage: Storage = None, limits_manager: SessionLimitsManager = None):
        """
        Initialise le SessionGraph
        
        Args:
            storage: Instance DSM Storage (optionnel, auto-créé si None)
            limits_manager: Instance SessionLimitsManager (optionnel, auto-créé si None)
        """
        # Initialiser Storage si non fourni
        if storage is None:
            # Utiliser le même chemin que SessionLimitsManager par défaut
            base_dir = str(Path.home() / "clawdbot_dsm_test" / "memory")
            storage = Storage(data_dir=base_dir)
        self.storage = storage
        
        # Initialiser SessionLimitsManager si non fourni
        if limits_manager is None:
            # Utiliser le même base_dir que storage
            base_dir = str(self.storage.data_dir.parent)
            limits_manager = SessionLimitsManager(base_dir=base_dir)
        self.limits_manager = limits_manager
        
        # Session ID actif
        self.current_session_id: Optional[str] = None
        
        # Timestamp de début de session
        self.session_start_time: Optional[datetime] = None
        
        # Source de la session
        self.session_source: Optional[str] = None
        
    def start_session(self, source: str) -> Entry:
        """
        Démarre une nouvelle session DSM
        
        Args:
            source: Source de la session (ex: "telegram", "manual", "moltbook")
        
        Returns:
            Entry: L'événement session_start écrit, ou None si échec
        """
        # Générer un nouveau session_id
        self.current_session_id = f"session_{int(datetime.utcnow().timestamp())}_{uuid.uuid4().hex[:8]}"
        self.session_start_time = datetime.utcnow()
        self.session_source = source
        
        # Créer l'événement session_start
        content = json.dumps({
            "start_time": self.session_start_time.isoformat(),
            "source": source
        })
        
        entry = Entry(
            id=str(uuid.uuid4()),
            timestamp=self.session_start_time,
            session_id=self.current_session_id,
            source=source,
            content=content,
            shard="sessions",
            hash="",
            prev_hash=None,
            metadata={"event_type": "session_start"},
            version="v2.0"
        )
        
        # Écrire l'événement via Storage
        written_entry = self.storage.append(entry)
        
        print(f"📌 Session started: {self.current_session_id} (source: {source})")
        return written_entry
    
    def record_snapshot(self, snapshot_data: Dict[str, Any]) -> Optional[Entry]:
        """
        Enregistre un snapshot d'état (avec vérification de cooldown)
        
        Args:
            snapshot_data: Données du snapshot (ex: Moltbook home state)
        
        Returns:
            Entry: L'événement snapshot écrit, ou None si cooldown
        """
        if not self.current_session_id:
            print("❌ Cannot record snapshot: no active session")
            return None
        
        # Vérifier le cooldown de polling home
        can_poll, reason = self.limits_manager.can_poll_home()
        
        if not can_poll:
            print(f"📦 Snapshot skipped: {reason}")
            # Marquer le skip dans les limites
            self.limits_manager.mark_home_poll_skipped()
            return None
        
        # Créer l'événement snapshot
        timestamp = datetime.utcnow()
        content = json.dumps({
            "snapshot_data": snapshot_data,
            "timestamp": timestamp.isoformat()
        })
        
        entry = Entry(
            id=str(uuid.uuid4()),
            timestamp=timestamp,
            session_id=self.current_session_id,
            source=self.session_source or "session_graph",
            content=content,
            shard="sessions",
            hash="",
            prev_hash=None,
            metadata={"event_type": "snapshot"},
            version="v2.0"
        )
        
        # Écrire l'événement via Storage
        written_entry = self.storage.append(entry)
        
        # Marquer le polling comme effectué
        self.limits_manager.mark_home_polled()
        
        print(f"📦 Snapshot recorded (session: {self.current_session_id[:12]}...)")
        return written_entry
    
    def execute_action(self, action_name: str, payload: Dict[str, Any]) -> Optional[Entry]:
        """
        Exécute une action (avec vérification des limites)
        
        Args:
            action_name: Nom de l'action (ex: "post_reply", "create_post")
            payload: Payload de l'action
        
        Returns:
            Entry: L'événement tool_call écrit, ou None si limites
        """
        if not self.current_session_id:
            print("❌ Cannot execute action: no active session")
            return None
        
        # Vérifier si l'action est autorisée
        can_execute, reason = self.limits_manager.can_execute_action()
        
        if not can_execute:
            print(f"🛑 Action blocked: {reason}")
            # Marquer l'action comme skipée
            self.limits_manager.mark_action_skipped_cooldown(reason=reason)
            return None
        
        # Créer l'événement tool_call
        timestamp = datetime.utcnow()
        content = json.dumps({
            "action": action_name,
            "payload": payload,
            "timestamp": timestamp.isoformat()
        })
        
        entry = Entry(
            id=str(uuid.uuid4()),
            timestamp=timestamp,
            session_id=self.current_session_id,
            source=self.session_source or "session_graph",
            content=content,
            shard="sessions",
            hash="",
            prev_hash=None,
            metadata={"event_type": "tool_call", "action_name": action_name},
            version="v2.0"
        )
        
        # Écrire l'événement via Storage
        written_entry = self.storage.append(entry)
        
        # Marquer l'action comme exécutée
        self.limits_manager.mark_action_executed()
        
        print(f"⚡ Action executed: {action_name} (session: {self.current_session_id[:12]}...)")
        return written_entry
    
    def end_session(self) -> Optional[Entry]:
        """
        Termine la session active
        
        Returns:
            Entry: L'événement session_end écrit, ou None si aucune session active
        """
        if not self.current_session_id:
            print("❌ Cannot end session: no active session")
            return None
        
        # Calculer la durée de session
        session_end_time = datetime.utcnow()
        session_duration = (session_end_time - self.session_start_time).total_seconds() if self.session_start_time else 0
        
        # Créer l'événement session_end
        content = json.dumps({
            "end_time": session_end_time.isoformat(),
            "start_time": self.session_start_time.isoformat(),
            "duration_seconds": session_duration,
            "source": self.session_source
        })
        
        entry = Entry(
            id=str(uuid.uuid4()),
            timestamp=session_end_time,
            session_id=self.current_session_id,
            source=self.session_source or "session_graph",
            content=content,
            shard="sessions",
            hash="",
            prev_hash=None,
            metadata={"event_type": "session_end"},
            version="v2.0"
        )
        
        # Écrire l'événement via Storage
        written_entry = self.storage.append(entry)
        
        # Réinitialiser l'état de session
        session_id = self.current_session_id
        self.current_session_id = None
        self.session_start_time = None
        self.session_source = None
        
        print(f"🏁 Session ended: {session_id} (duration: {session_duration:.1f}s)")
        return written_entry
    
    def get_session_id(self) -> Optional[str]:
        """
        Retourne l'ID de la session active
        
        Returns:
            str: Session ID, ou None si aucune session active
        """
        return self.current_session_id
    
    def is_session_active(self) -> bool:
        """
        Vérifie si une session est active
        
        Returns:
            bool: True si une session est active
        """
        return self.current_session_id is not None
