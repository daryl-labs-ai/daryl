#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSM v2 - Drift Metrics (v2.1)
Simple metrics without complex verification
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

class DriftMetrics:
    """Métriques simples de drift (v2.1)"""

    def __init__(self, metrics_file="data/integrity/integrity_log.jsonl"):
        self.metrics_file = Path(metrics_file)
        self.metrics_file.parent.mkdir(parents=True, exist_ok=True)

    def record_integrity_check(self, check_type: str, shard: str,
                               entry_id: str = None, details: dict = None):
        """
        Record un check d'intégrité

        Args:
            check_type: "verify", "corruption_detected", "tampering_detected"
            shard: Shard concerné
            entry_id: Entry spécifique
            details: Détails du check
        """
        record = {
            "timestamp": datetime.utcnow().isoformat(),
            "check_type": check_type,
            "shard": shard,
            "entry_id": entry_id,
            "details": details,
            "success": check_type == "verify"
        }

        with open(self.metrics_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record) + '\n')

    def calculate_stability_score(self, session: dict, hours: int = 24) -> float:
        """
        Calcule un score de stabilité (heuristique)

        Args:
            session: Données de session
            hours: Période en heures

        Returns:
            float: Score 0-1
        """
        # Formula: (new_additions / period) + (heartbeat_regularity / 10)
        entries = session.get("entries_count", 0)
        heartbeats = session.get("heartbeat_count", 0)

        # New additions rate (per hour)
        additions_rate = entries / hours if hours > 0 else 0

        # Heartbeat regularity (how close to expected)
        expected_heartbeats = hours * 4  # ~15 min
        if heartbeats > 0:
            heartbeat_regularity = min(1.0, expected_heartbeats / heartbeats)
        else:
            heartbeat_regularity = 1.0

        # Final score
        stability_score = min(1.0, (additions_rate * 10) + (heartbeat_regularity * 10)) / 20

        return stability_score
