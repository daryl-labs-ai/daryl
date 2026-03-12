#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSM v3.0a - Unit Tests for Trace Replay
Tests: test_replay_ok, test_replay_corrupt_json_line, test_replay_broken_chain
"""

import json
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

# Add parent to path for imports
import sys
parent_dir = Path(__file__).parent
sys.path.insert(0, str(parent_dir))

from dsm_v2.core.replay import (
    TraceRecord,
    parse_trace_line,
    verify_record,
    verify_chain,
    replay_session,
    canonical_json,
    compute_step_hash,
)


class TestReplayOK(unittest.TestCase):
    """Test: Replay d'une trace valide"""

    def test_replay_ok(self):
        """
        Crée une trace valide avec 3 records et vérifie que le replay retourne OK.
        """
        session_id = str(uuid4())
        trace_id = str(uuid4())

        with tempfile.TemporaryDirectory() as tmpdir:
            trace_file = Path(tmpdir) / "trace_log.jsonl"

            # Créer 3 records avec chaînage de hash correct
            records = []
            prev_hash = None

            for i in range(3):
                record = {
                    "trace_id": trace_id,
                    "ts": "2026-03-04T15:00:00.000Z",
                    "session_id": session_id,
                    "action_type": f"ACTION_{i}",
                    "intent": f"intent_{i}",
                    "scope": "test",
                    "input": {},
                    "output": {},
                    "ok": True,
                    "error": None,
                    "state_before": None,
                    "state_after": None,
                    "prev_step_hash": prev_hash,
                    "step_hash": "",  # Sera calculé
                }

                # Calculer step_hash
                step_hash = compute_step_hash(record)
                record["step_hash"] = step_hash

                records.append(record)
                prev_hash = step_hash

            # Écrire les records
            with open(trace_file, "w") as f:
                for record in records:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")

            # Rejouer la session
            report = replay_session(
                trace_file=trace_file,
                session_id=session_id,
                strict=False,
                limit=None,
            )

            # Vérifier le résultat
            self.assertEqual(report.session_id, session_id)
            self.assertEqual(report.total_records, 3)
            self.assertEqual(report.verified_records, 3)
            self.assertEqual(report.corrupt_records, 0)
            self.assertEqual(report.broken_chain_records, 0)
            self.assertEqual(report.status, "OK")


class TestReplayCorruptJSONLine(unittest.TestCase):
    """Test: Replay d'une trace avec JSON corrompu"""

    def test_replay_corrupt_json_line(self):
        """
        Crée une trace avec une ligne JSON invalide et vérifie que le replay détecte la corruption.
        """
        session_id = str(uuid4())
        trace_id = str(uuid4())

        with tempfile.TemporaryDirectory() as tmpdir:
            trace_file = Path(tmpdir) / "trace_log.jsonl"

            # Créer des records valides
            record = {
                "trace_id": trace_id,
                "ts": "2026-03-04T15:00:00.000Z",
                "session_id": session_id,
                "action_type": "ACTION",
                "intent": "intent",
                "scope": "test",
                "input": {},
                "output": {},
                "ok": True,
                "error": None,
                "state_before": None,
                "state_after": None,
                "prev_step_hash": None,
                "step_hash": compute_step_hash({
                    "trace_id": trace_id,
                    "ts": "2026-03-04T15:00:00.000Z",
                    "session_id": session_id,
                    "action_type": "ACTION",
                    "intent": "intent",
                    "scope": "test",
                    "input": {},
                    "output": {},
                    "ok": True,
                    "error": None,
                    "state_before": None,
                    "state_after": None,
                    "prev_step_hash": None,
                }),
            }

            lines = [
                json.dumps(record, ensure_ascii=False),
                "{invalid json line}",
                json.dumps(record, ensure_ascii=False),
            ]

            # Écrire les records
            with open(trace_file, "w") as f:
                f.write("\n".join(lines) + "\n")

            # Rejouer la session
            report = replay_session(
                trace_file=trace_file,
                session_id=session_id,
                strict=False,
                limit=None,
            )

            # Vérifier le résultat
            self.assertEqual(report.total_records, 2)  # 2 records valides
            self.assertEqual(report.corrupt_records, 1)  # 1 ligne corrompue
            self.assertEqual(report.status, "CORRUPT")
            self.assertTrue(any("corrupted JSON" in e for e in report.errors))


class TestReplayBrokenChain(unittest.TestCase):
    """Test: Replay d'une trace avec chaîne brisée"""

    def test_replay_broken_chain(self):
        """
        Crée une trace avec un prev_step_hash incorrect et vérifie que le replay détecte la chaîne brisée.
        """
        session_id = str(uuid4())
        trace_id = str(uuid4())

        with tempfile.TemporaryDirectory() as tmpdir:
            trace_file = Path(tmpdir) / "trace_log.jsonl"

            # Créer 2 records seulement : 1 valide, 1 avec chaîne brisée
            records = []
            hashes = []

            # Record 0: Premier record (pas de prev_step_hash)
            record0 = {
                "trace_id": trace_id,
                "ts": "2026-03-04T15:00:00.000Z",
                "session_id": session_id,
                "action_type": "ACTION_0",
                "intent": "intent_0",
                "scope": "test",
                "input": {},
                "output": {},
                "ok": True,
                "error": None,
                "state_before": None,
                "state_after": None,
                "prev_step_hash": None,
                "step_hash": "",
            }
            step_hash0 = compute_step_hash(record0)
            record0["step_hash"] = step_hash0
            hashes.append(step_hash0)
            records.append(record0)

            # Record 1: Avec prev_step_hash incorrect (cassé)
            record1 = {
                "trace_id": trace_id,
                "ts": "2026-03-04T15:00:01.000Z",
                "session_id": session_id,
                "action_type": "ACTION_1",
                "intent": "intent_1",
                "scope": "test",
                "input": {},
                "output": {},
                "ok": True,
                "error": None,
                "state_before": None,
                "state_after": None,
                "prev_step_hash": "WRONG_HASH",  # Cassé: doit être step_hash0
                "step_hash": "",
            }
            step_hash1 = compute_step_hash(record1)
            record1["step_hash"] = step_hash1
            hashes.append(step_hash1)
            records.append(record1)

            # Écrire les records
            with open(trace_file, "w") as f:
                for record in records:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")

            # Rejouer la session
            report = replay_session(
                trace_file=trace_file,
                session_id=session_id,
                strict=False,
                limit=None,
            )

            # Vérifier le résultat
            self.assertEqual(report.total_records, 2)
            self.assertEqual(report.broken_chain_records, 1)  # 1 chaîne brisée (record 1)
            self.assertEqual(report.status, "DIVERGENCE")
            self.assertTrue(any("broken chain" in e for e in report.errors))


if __name__ == "__main__":
    unittest.main()
