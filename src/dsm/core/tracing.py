#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSM v3.0a - Trace Recording (PR-A)
Enregistrement de traces avec chaînage de hash (prev_step_hash -> step_hash)
"""

import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any, List


class ActionType(Enum):
    """Types d'actions de trace"""
    SESSION_START = "SESSION_START"
    SESSION_END = "SESSION_END"
    TOOL_CALL = "TOOL_CALL"
    INGEST = "INGEST"
    ERROR = "ERROR"
    MARKER = "MARKER"
    CHECKPOINT = "CHECKPOINT"


def canonical_json(record: Dict[str, Any], exclude_step_hash: bool = False) -> str:
    """
    Génère le JSON canonique pour le hashage.

    Canonical JSON rules:
    - sort keys
    - separators=(",", ":")
    - ensure_ascii=False
    """
    if exclude_step_hash and "step_hash" in record:
        record_copy = record.copy()
        del record_copy["step_hash"]
    else:
        record_copy = record

    return json.dumps(
        record_copy,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def compute_step_hash(record: Dict[str, Any]) -> str:
    """
    Calcule le step_hash d'un enregistrement.

    Règle: sha256 of canonical_json(record_without_step_hash)
    """
    canonical = canonical_json(record, exclude_step_hash=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class TraceRecord:
    """Enregistrement de trace"""
    trace_id: str
    ts: str
    session_id: str
    action_type: str
    intent: str
    scope: str
    input: Optional[Dict[str, Any]]
    output: Optional[Dict[str, Any]]
    ok: bool
    error: Optional[str]
    state_before: Optional[str]
    state_after: Optional[str]
    prev_step_hash: Optional[str]
    step_hash: str


class TraceWriter:
    """Writer pour les traces DSM v3.0a"""

    def __init__(self, trace_file: Path = None):
        """
        Initialise le writer de traces.

        Args:
            trace_file: Chemin vers le fichier de trace (default: data/traces/trace_log.jsonl)
        """
        self.trace_file = trace_file or Path("data/traces/trace_log.jsonl")
        self.trace_file.parent.mkdir(parents=True, exist_ok=True)

        # État pour le chaînage de hash
        self.last_step_hash: Optional[str] = None

    def _create_record_dict(
        self,
        action_type: str,
        intent: str,
        scope: str,
        input: Optional[Dict[str, Any]] = None,
        output: Optional[Dict[str, Any]] = None,
        ok: bool = True,
        error: Optional[str] = None,
        state_before: Optional[str] = None,
        state_after: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Crée le dictionnaire pour un enregistrement de trace.
        """
        # Timestamp UTC
        ts = datetime.now(timezone.utc).isoformat()

        # Générer trace_id
        trace_id = str(uuid.uuid4())

        # Données de base
        data = {
            "trace_id": trace_id,
            "ts": ts,
            "session_id": session_id or "default",
            "action_type": action_type,
            "intent": intent,
            "scope": scope,
            "input": input,
            "output": output,
            "ok": ok,
            "error": error,
            "state_before": state_before,
            "state_after": state_after,
            "prev_step_hash": self.last_step_hash,
            "step_hash": "",  # Sera calculé après
        }

        # Calculer step_hash APRES avoir défini prev_step_hash
        step_hash = compute_step_hash(data)
        data["step_hash"] = step_hash

        # Mettre à jour last_step_hash
        self.last_step_hash = step_hash

        return data

    def write(
        self,
        action_type: str,
        intent: str,
        scope: str,
        input: Optional[Dict[str, Any]] = None,
        output: Optional[Dict[str, Any]] = None,
        ok: bool = True,
        error: Optional[str] = None,
        state_before: Optional[str] = None,
        state_after: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> TraceRecord:
        """
        Écrit un enregistrement de trace.

        Args:
            action_type: Type d'action (ActionType enum)
            intent: Intention de l'action
            scope: Portée (global, session, etc.)
            input: Données d'entrée (optionnel)
            output: Données de sortie (optionnel)
            ok: Si l'action a réussi
            error: Message d'erreur (si applicable)
            state_before: État avant l'action (optionnel)
            state_after: État après l'action (optionnel)
            session_id: ID de session (optionnel)

        Returns:
            TraceRecord créé
        """
        # Créer le dictionnaire
        data = self._create_record_dict(
            action_type=action_type,
            intent=intent,
            scope=scope,
            input=input,
            output=output,
            ok=ok,
            error=error,
            state_before=state_before,
            state_after=state_after,
            session_id=session_id,
        )

        # Sérialiser en JSON
        json_line = json.dumps(data, ensure_ascii=False)

        # Écrire dans le fichier (append-only)
        with open(self.trace_file, "a", encoding="utf-8") as f:
            f.write(json_line + "\n")

        return TraceRecord(**data)


# Writer global par défaut
_default_writer: Optional[TraceWriter] = None


def get_default_writer() -> TraceWriter:
    """Retourne le writer par défaut (singleton)"""
    global _default_writer
    if _default_writer is None:
        _default_writer = TraceWriter()
    return _default_writer


def trace_action(
    action_type: str,
    intent: str,
    scope: str,
    input: Optional[Dict[str, Any]] = None,
    output: Optional[Dict[str, Any]] = None,
    ok: bool = True,
    error: Optional[str] = None,
    state_before: Optional[str] = None,
    state_after: Optional[str] = None,
    session_id: Optional[str] = None,
    writer: Optional[TraceWriter] = None,
) -> TraceRecord:
    """
    Fonction de commodité pour tracer une action.

    Args:
        action_type: Type d'action
        intent: Intention de l'action
        scope: Portée de l'action
        input: Données d'entrée (optionnel)
        output: Données de sortie (optionnel)
        ok: Si l'action a réussi
        error: Message d'erreur (si applicable)
        state_before: État avant l'action (optionnel)
        state_after: État après l'action (optionnel)
        session_id: ID de session (optionnel)
        writer: Writer personnalisé (optionnel)

    Returns:
        TraceRecord créé
    """
    if writer is None:
        writer = get_default_writer()

    return writer.write(
        action_type=action_type,
        intent=intent,
        scope=scope,
        input=input,
        output=output,
        ok=ok,
        error=error,
        state_before=state_before,
        state_after=state_after,
        session_id=session_id,
    )
