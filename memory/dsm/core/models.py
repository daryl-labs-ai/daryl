#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSM v2 - Core Models
Entry, ShardMeta, IntegrityRecord dataclasses
"""

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, List
import hashlib

@dataclass
class Entry:
    """Entrée mémoire standardisée DSM v2"""
    id: str                          # UUID unique
    timestamp: datetime                 # ISO 8601 UTC
    session_id: str                  # Session qui a créé cette entrée
    source: str                      # message, heartbeat, manual, etc.
    content: str                     # Contenu principal
    shard: str                        # Nom du shard (ex: "daryl_identity")
    hash: str                         # SHA-256 du contenu
    prev_hash: Optional[str]           # Hash de l'entrée précédente (chain)
    metadata: dict                    # Tags, keywords, etc.
    version: str                      # Version du format (ex: "v2.0")

@dataclass
class ShardMeta:
    """Métadonnées d'un shard"""
    shard_id: str                   # Nom du shard (ex: "daryl_identity")
    created_at: datetime             # Date de création
    last_updated: datetime            # Date de dernière mise à jour
    entry_count: int              # Nombre d'entrées dans le shard
    size_bytes: int               # Taille du shard en bytes
    integrity_status: str          # "verified", "corrupted", "unknown"

@dataclass
class IntegrityRecord:
    """Record d'intégrité"""
    timestamp: datetime                # ISO 8601 UTC
    check_type: str                  # "verify", "corruption_detected", "tampering_detected"
    shard: str                      # Shard concerné
    entry_id: Optional[str]         # Entry spécifique
    details: dict                    # Détails du check
    success: bool                   # True = integrity OK
