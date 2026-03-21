#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSM v2 - Session Graph.

Orchestration layer for DSM sessions with lifecycle management and safeguards.
Writes session_start, snapshot, tool_call, and session_end events to the
`sessions` shard. Rate limits and action limits are enforced via
SessionLimitsManager.

API principale:
  - start_session(source) -> Entry | None
  - record_snapshot(snapshot_data) -> Entry | None
  - execute_action(action_name, payload) -> Entry | None  (writes intent; WAL pattern)
  - confirm_action(intent_id, result_data, success) -> Entry | None  (writes result receipt)
  - end_session() -> Entry | None

Contraintes:
  - At most one active session at a time; start_session() creates a new one.
  - All session events go to the `sessions` shard.
  - Snapshot and action writes may be skipped if limits/cooldowns are exceeded.
  - Do not modify DSM core; this module uses only Storage.append() and core models.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
from pathlib import Path

from .session_limits_manager import SessionLimitsManager
from ..core.storage import Storage
from ..core.models import Entry

logger = logging.getLogger(__name__)


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
        if self.current_session_id is not None:
            logger.warning(
                "Session %s still active — auto-closing before new start",
                self.current_session_id,
            )
            self.end_session()

        # Générer un nouveau session_id
        self.current_session_id = f"session_{int(datetime.now(timezone.utc).timestamp())}_{uuid.uuid4().hex[:8]}"
        self.session_start_time = datetime.now(timezone.utc)
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
        try:
            written_entry = self.storage.append(entry)
        except OSError as e:
            logger.error("Failed to append entry to storage: %s", e)
            return None
        logger.info("Session started: %s (source: %s)", self.current_session_id, source)
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
            logger.warning("Cannot record snapshot: no active session")
            return None

        # Vérifier le cooldown de polling home
        can_poll, reason = self.limits_manager.can_poll_home()

        if not can_poll:
            logger.info("Snapshot skipped: %s", reason)
            # Marquer le skip dans les limites
            self.limits_manager.mark_home_poll_skipped()
            return None
        
        # Créer l'événement snapshot
        timestamp = datetime.now(timezone.utc)
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
        try:
            written_entry = self.storage.append(entry)
        except OSError as e:
            logger.error("Failed to append entry to storage: %s", e)
            return None
        # Marquer le polling comme effectué
        self.limits_manager.mark_home_polled()
        logger.info("Snapshot recorded (session: %s...)", self.current_session_id[:12])
        return written_entry

    def execute_action(self, action_name: str, payload: Dict[str, Any] = None) -> Optional[Entry]:
        """
        Write an action intent to the log. Returns the intent entry.
        Call confirm_action() after the action completes to record the result.
        If the process crashes between execute_action and confirm_action,
        the intent entry exists without a matching result — detectable on replay.
        """
        if self.current_session_id is None:
            logger.warning("Cannot execute action: no active session")
            return None

        can_execute, reason = self.limits_manager.can_execute_action()
        if not can_execute:
            logger.info("Action blocked: %s", reason)
            self.limits_manager.mark_action_skipped_cooldown(reason=reason)
            return None

        intent_id = str(uuid.uuid4())
        entry = Entry(
            id=intent_id,
            timestamp=datetime.now(timezone.utc),
            session_id=self.current_session_id,
            source="session_graph",
            content=json.dumps({
                "action_name": action_name,
                "payload": payload or {},
            }),
            shard="sessions",
            hash="",
            prev_hash=None,
            metadata={
                "event_type": "action_intent",
                "action_name": action_name,
                "intent_id": intent_id,
            },
            version="v2.0",
        )
        try:
            result = self.storage.append(entry)
            logger.info(
                "Action intent: %s (session: %s, intent: %s)",
                action_name,
                self.current_session_id[:12],
                intent_id[:8],
            )
            return result
        except OSError as e:
            logger.error("Failed to append action intent: %s", e)
            return None

    def confirm_action(
        self,
        intent_id: str,
        result_data: Dict[str, Any] = None,
        success: bool = True,
        input_hash: str = None,
        input_preview: str = None,
    ) -> Optional[Entry]:
        """
        Write the result of a previously declared intent.
        Links to the intent via intent_id in metadata.
        Optionally store input_hash/input_preview (input receipt) to prove what the agent saw.
        If this is never called (crash), the orphaned intent is detectable.
        """
        if self.current_session_id is None:
            logger.warning("Cannot confirm action: no active session")
            return None

        content_data = {
            "result": result_data or {},
            "success": success,
        }
        if input_hash:
            content_data["input_hash"] = input_hash
        if input_preview:
            content_data["input_preview"] = input_preview[:200]

        metadata = {
            "event_type": "action_result",
            "intent_id": intent_id,
            "success": success,
        }
        if input_hash:
            metadata["input_hash"] = input_hash

        entry = Entry(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            session_id=self.current_session_id,
            source="session_graph",
            content=json.dumps(content_data),
            shard="sessions",
            hash="",
            prev_hash=None,
            metadata=metadata,
            version="v2.0",
        )
        try:
            result = self.storage.append(entry)
            self.limits_manager.mark_action_executed()
            logger.info(
                "Action result: intent %s, success=%s (session: %s)",
                intent_id[:8],
                success,
                self.current_session_id[:12],
            )
            return result
        except OSError as e:
            logger.error("Failed to append action result: %s", e)
            return None

    def find_orphaned_intents(self, storage=None, limit: int = 1000) -> list:
        """
        Find action intents that have no matching action result.
        These indicate crashes between intent and completion.
        Returns list of orphaned intent entries.
        """
        s = storage or self.storage
        entries = s.read("sessions", limit=limit)

        intents = {}
        results = set()

        for e in entries:
            event_type = e.metadata.get("event_type")
            intent_id = e.metadata.get("intent_id")

            if event_type == "action_intent" and intent_id:
                intents[intent_id] = e
            elif event_type == "action_result" and intent_id:
                results.add(intent_id)

        orphaned = [e for iid, e in intents.items() if iid not in results]
        return orphaned

    def end_session(
        self,
        sync_engine=None,
        lifecycle=None,
    ) -> Optional[Entry]:
        """
        Termine la session active.

        Optional A→E hooks (backward compatible — both default to None):
            sync_engine: ShardSyncEngine — if provided, triggers reconcile on session end
            lifecycle: ShardLifecycle — if provided, checks automatic triggers on session end

        Returns:
            Entry: L'événement session_end écrit, ou None si aucune session active
        """
        if self.current_session_id is None:
            logger.warning("end_session called with no active session")
            return None

        # Calculer la durée de session
        session_end_time = datetime.now(timezone.utc)
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
        try:
            written_entry = self.storage.append(entry)
        except OSError as e:
            logger.error("Failed to append entry to storage: %s", e)
            return None

        # A→E hook: auto-sync on session end (non-blocking)
        if sync_engine is not None:
            try:
                sync_engine.reconcile(
                    agent_id=self.session_source or "unknown",
                    owner_id=self.session_source or "unknown",
                    entries=[],  # reconcile pulls only, no auto-push
                )
                logger.debug("Session end sync completed for %s", self.current_session_id)
            except Exception as e:
                logger.debug("Session end sync skipped: %s", e)

        # A→E hook: lifecycle trigger check (lightweight)
        if lifecycle is not None:
            try:
                lifecycle.check_triggers(
                    "sessions",
                    owner_id=self.session_source or "unknown",
                    owner_sig="session_end",
                )
                logger.debug("Session end lifecycle check completed")
            except Exception as e:
                logger.debug("Session end lifecycle check skipped: %s", e)

        # Réinitialiser l'état de session
        session_id = self.current_session_id
        self.current_session_id = None
        self.session_start_time = None
        self.session_source = None
        logger.info("Session ended: %s (duration: %.1fs)", session_id, session_duration)
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
