"""Attestation stub — local reimplementation, no daryl imports."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from ulid import ULID


def _hash_data(data) -> str:
    if isinstance(data, (bytes, bytearray)):
        b = bytes(data)
    elif isinstance(data, str):
        b = data.encode("utf-8")
    else:
        b = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(b).hexdigest()


def create_attestation(agent_id: str, input_data, output_data, model_id: str) -> dict:
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    input_hash = _hash_data(input_data)
    output_hash = _hash_data(output_data)
    attestation_hash = hashlib.sha256(
        (input_hash + output_hash + model_id + agent_id + timestamp).encode("utf-8")
    ).hexdigest()
    return {
        "attestation_id": str(ULID()),
        "agent_id": agent_id,
        "input_hash": input_hash,
        "output_hash": output_hash,
        "model_id": model_id,
        "timestamp": timestamp,
        "attestation_hash": attestation_hash,
    }
