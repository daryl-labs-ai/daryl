"""
External Witness for DSM.

Periodically captures a signed snapshot of each shard's state
(tip hash, entry count, timestamp) and stores it in a witness log.

This provides third-party verifiable proof that a shard was in a
specific state at a specific time. If the shard is later tampered
with, the witness record proves the original state.

The witness log is a separate JSONL file, independent from DSM shards.
It should be stored outside the agent's write perimeter for maximum
security (e.g., different directory, remote storage, or signed by
an external key).
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .status import WitnessStatus

logger = logging.getLogger(__name__)


class ShardWitness:
    """
    Captures and verifies witness records for DSM shards.

    A witness record contains:
    - shard_id: which shard was witnessed
    - timestamp: when the snapshot was taken (UTC ISO format)
    - entry_count: number of entries in the shard at snapshot time
    - tip_hash: last hash in the shard's chain
    - witness_hash: SHA-256 of (shard_id + timestamp + entry_count + tip_hash + secret)
    - witness_id: unique identifier for this witness record

    The witness_hash includes an optional secret (witness key) so that
    only the holder of the key can produce valid witness records.
    """

    def __init__(self, witness_dir: str, witness_key: str = ""):
        """
        Args:
            witness_dir: directory to store witness logs (should be
                         outside the agent's DSM data_dir)
            witness_key: optional secret key for signing witness records.
                         If empty, records are unsigned (still useful for
                         detecting tampering, but not provable to third parties
                         without trust in the witness process).
        """
        self.witness_dir = Path(witness_dir)
        self.witness_dir.mkdir(parents=True, exist_ok=True)
        self.witness_key = witness_key
        self.log_file = self.witness_dir / "witness_log.jsonl"

    def _compute_witness_hash(
        self, shard_id: str, timestamp: str, entry_count: int, tip_hash: str
    ) -> str:
        """Compute SHA-256 witness hash including the witness key."""
        payload = f"{shard_id}:{timestamp}:{entry_count}:{tip_hash}:{self.witness_key}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def capture(self, storage, shard_id: str) -> dict:
        """
        Capture a witness record for a single shard.

        Args:
            storage: DSM Storage instance
            shard_id: shard to witness

        Returns:
            dict with witness record, or None if shard is empty/missing
        """
        entries = storage.read(shard_id, limit=1)

        if not entries:
            logger.info("Shard '%s' is empty, skipping witness", shard_id)
            return None

        all_entries = storage.read(shard_id, limit=100000)
        entry_count = len(all_entries)

        tip_hash = all_entries[0].hash if all_entries[0].hash else "no_hash"

        timestamp = datetime.now(timezone.utc).isoformat() + "Z"
        witness_id = str(uuid4())

        witness_hash = self._compute_witness_hash(
            shard_id, timestamp, entry_count, tip_hash
        )

        record = {
            "witness_id": witness_id,
            "shard_id": shard_id,
            "timestamp": timestamp,
            "entry_count": entry_count,
            "tip_hash": tip_hash,
            "witness_hash": witness_hash,
            "signed": bool(self.witness_key),
        }

        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

        logger.info(
            "Witness captured: shard=%s entries=%d tip=%s",
            shard_id,
            entry_count,
            tip_hash[:12],
        )

        return record

    def capture_all(self, storage) -> list:
        """
        Capture witness records for all shards in the storage.

        Returns list of witness records.
        """
        records = []
        for meta in storage.list_shards():
            record = self.capture(storage, meta.shard_id)
            if record:
                records.append(record)
        return records

    def read_log(self) -> list:
        """Read all witness records from the log file."""
        if not self.log_file.exists():
            return []

        records = []
        with open(self.log_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return records

    def verify_record(self, record: dict) -> bool:
        """
        Verify that a witness record's hash is valid.

        Returns True if the witness_hash matches the recomputed hash.
        This proves the record hasn't been tampered with (assuming
        the witness_key is secret).
        """
        expected = self._compute_witness_hash(
            record["shard_id"],
            record["timestamp"],
            record["entry_count"],
            record["tip_hash"],
        )
        return expected == record.get("witness_hash")

    def verify_shard_against_witness(self, storage, shard_id: str) -> dict:
        """
        Compare current shard state against the most recent witness record.

        Returns:
            {
                "shard_id": str,
                "witness_valid": bool,     # witness record hash is correct
                "state_matches": bool,     # current tip matches witnessed tip
                "current_tip": str,
                "witnessed_tip": str,
                "current_count": int,
                "witnessed_count": int,
                "witness_timestamp": str,
                "status": "OK" | "DIVERGED" | "NO_WITNESS"
            }
        """
        records = self.read_log()
        shard_records = [r for r in records if r["shard_id"] == shard_id]

        if not shard_records:
            return {
                "shard_id": shard_id,
                "status": WitnessStatus.NO_WITNESS,
            }

        latest = shard_records[-1]

        witness_valid = self.verify_record(latest)

        all_entries = storage.read(shard_id, limit=100000)
        current_count = len(all_entries)
        current_tip = all_entries[0].hash if all_entries else "empty"

        state_matches = current_count >= latest["entry_count"]
        if current_count == latest["entry_count"]:
            state_matches = current_tip == latest["tip_hash"]

        status = WitnessStatus.OK if (witness_valid and state_matches) else WitnessStatus.DIVERGED

        return {
            "shard_id": shard_id,
            "witness_valid": witness_valid,
            "state_matches": state_matches,
            "current_tip": current_tip,
            "witnessed_tip": latest["tip_hash"],
            "current_count": current_count,
            "witnessed_count": latest["entry_count"],
            "witness_timestamp": latest["timestamp"],
            "status": status,
        }
