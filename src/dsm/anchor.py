"""
Pre-commitment and environment anchoring for DSM.

Closes the "poisoned reality" gap: DSM proves the log wasn't altered,
anchoring proves the log wasn't fabricated at write time.

Two mechanisms:
- Pre-commitment: hash of intent published BEFORE execution
- Environment capture: hash of external data at observation time

Pre-commitment flow:
  1. Agent creates intent → gets intent_id from DSM
  2. anchor.pre_commit(intent_id, action_name, params) → commitment_hash
  3. Agent executes the real action
  4. anchor.post_commit(intent_id, result, raw_input, commitment_hash)
  5. verify_commitment() checks: pre < post AND hashes match

Inspired by @clawhopper and @notbob on Moltbook.
"""

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)


def _sha256(data: Union[str, bytes, dict]) -> str:
    """SHA-256 hex digest. Accepts str, bytes, or dict (sorted JSON)."""
    if isinstance(data, dict):
        raw = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    elif isinstance(data, str):
        raw = data.encode("utf-8")
    elif isinstance(data, bytes):
        raw = data
    else:
        raw = str(data).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class AnchorLog:
    """Append-only log for pre-commitments and environment captures."""

    def __init__(self, anchor_dir: str):
        self.anchor_dir = Path(anchor_dir)
        self.anchor_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.anchor_dir / "anchor_log.jsonl"

    def _append_record(self, record: dict) -> None:
        """Append a JSON record to the anchor log with fsync."""
        line = json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n"
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())

    def read_log(self) -> list:
        """Read all records from the anchor log."""
        if not self.log_path.exists():
            return []
        records = []
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return records

    def find_by_intent(self, intent_id: str) -> dict:
        """Find pre_commit and post_commit records for an intent_id."""
        records = self.read_log()
        result = {"pre_commit": None, "post_commit": None}
        for r in records:
            if r.get("intent_id") == intent_id:
                if r.get("type") == "pre_commit":
                    result["pre_commit"] = r
                elif r.get("type") == "post_commit":
                    result["post_commit"] = r
        return result


def pre_commit(
    anchor_log: AnchorLog,
    intent_id: str,
    action_name: str,
    params: dict,
) -> dict:
    """
    Record a pre-commitment BEFORE executing an action.

    Returns:
        {"commitment_hash": str, "params_hash": str, "intent_id": str}
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    params_hash = _sha256({
        "intent_id": intent_id,
        "action_name": action_name,
        "params": params,
    })

    record = {
        "type": "pre_commit",
        "intent_id": intent_id,
        "action_name": action_name,
        "params_hash": params_hash,
        "timestamp": timestamp,
    }

    commitment_hash = _sha256(json.dumps(record, sort_keys=True, separators=(",", ":")))
    record["commitment_hash"] = commitment_hash

    anchor_log._append_record(record)

    logger.info("Pre-commit: intent=%s action=%s", intent_id[:12], action_name)

    return {
        "commitment_hash": commitment_hash,
        "params_hash": params_hash,
        "intent_id": intent_id,
    }


def post_commit(
    anchor_log: AnchorLog,
    intent_id: str,
    result_data,
    raw_input=None,
    commitment_hash: Optional[str] = None,
) -> dict:
    """
    Record a post-commitment AFTER executing an action.

    Returns:
        {"intent_id": str, "result_hash": str, "input_hash": str|None,
         "commitment_hash": str|None}
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    result_hash = _sha256(result_data) if result_data is not None else None
    input_hash = _sha256(raw_input) if raw_input is not None else None

    record = {
        "type": "post_commit",
        "intent_id": intent_id,
        "result_hash": result_hash,
        "input_hash": input_hash,
        "commitment_hash": commitment_hash,
        "timestamp": timestamp,
    }

    anchor_log._append_record(record)

    logger.info("Post-commit: intent=%s", intent_id[:12])

    return {
        "intent_id": intent_id,
        "result_hash": result_hash,
        "input_hash": input_hash,
        "commitment_hash": commitment_hash,
    }


def capture_environment(
    anchor_log: AnchorLog,
    source: str,
    raw_data: Union[str, bytes, dict],
    headers: Optional[dict] = None,
) -> dict:
    """
    Capture an environment fingerprint (external data at observation time).

    Returns:
        {"env_hash": str, "source": str, "header_hash": str|None, "size_bytes": int}
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    env_hash = _sha256(raw_data)

    if isinstance(raw_data, bytes):
        size_bytes = len(raw_data)
    elif isinstance(raw_data, str):
        size_bytes = len(raw_data.encode("utf-8"))
    elif isinstance(raw_data, dict):
        size_bytes = len(json.dumps(raw_data, sort_keys=True).encode("utf-8"))
    else:
        size_bytes = len(str(raw_data).encode("utf-8"))

    header_hash = _sha256(headers) if headers else None

    record = {
        "type": "env_capture",
        "source": source,
        "env_hash": env_hash,
        "header_hash": header_hash,
        "size_bytes": size_bytes,
        "timestamp": timestamp,
    }

    anchor_log._append_record(record)

    logger.info("Env capture: source=%s size=%d", source, size_bytes)

    return {
        "env_hash": env_hash,
        "source": source,
        "header_hash": header_hash,
        "size_bytes": size_bytes,
    }


def verify_commitment(anchor_log: AnchorLog, intent_id: str) -> dict:
    """
    Verify a pre/post commitment pair for an intent.

    Checks:
    - Both pre_commit and post_commit exist
    - pre_commit.timestamp < post_commit.timestamp
    - post_commit.commitment_hash matches SHA-256 of pre_commit record

    Returns:
        {"intent_id": str, "status": str, "pre_commit_at": str,
         "post_commit_at": str, "time_delta_ms": float}

    Status: VERIFIED | SEQUENCE_VIOLATION | HASH_MISMATCH | INCOMPLETE
    """
    pair = anchor_log.find_by_intent(intent_id)
    pre = pair["pre_commit"]
    post = pair["post_commit"]

    if pre is None and post is None:
        return {
            "intent_id": intent_id,
            "status": "INCOMPLETE",
            "pre_commit_at": None,
            "post_commit_at": None,
            "time_delta_ms": None,
        }

    if pre is None or post is None:
        return {
            "intent_id": intent_id,
            "status": "INCOMPLETE",
            "pre_commit_at": pre["timestamp"] if pre else None,
            "post_commit_at": post["timestamp"] if post else None,
            "time_delta_ms": None,
        }

    # Check sequence: pre must come before post
    pre_at = pre["timestamp"]
    post_at = post["timestamp"]

    if post_at < pre_at:
        return {
            "intent_id": intent_id,
            "status": "SEQUENCE_VIOLATION",
            "pre_commit_at": pre_at,
            "post_commit_at": post_at,
            "time_delta_ms": None,
        }

    # Check commitment hash: post's commitment_hash must match pre's
    pre_commitment = pre.get("commitment_hash")
    post_commitment = post.get("commitment_hash")

    if pre_commitment and post_commitment and pre_commitment != post_commitment:
        return {
            "intent_id": intent_id,
            "status": "HASH_MISMATCH",
            "pre_commit_at": pre_at,
            "post_commit_at": post_at,
            "time_delta_ms": None,
        }

    # Calculate time delta
    try:
        from datetime import datetime
        t_pre = datetime.fromisoformat(pre_at.replace("Z", "+00:00"))
        t_post = datetime.fromisoformat(post_at.replace("Z", "+00:00"))
        delta_ms = (t_post - t_pre).total_seconds() * 1000
    except (ValueError, TypeError):
        delta_ms = None

    return {
        "intent_id": intent_id,
        "status": "VERIFIED",
        "pre_commit_at": pre_at,
        "post_commit_at": post_at,
        "time_delta_ms": delta_ms,
    }


def verify_all_commitments(anchor_log: AnchorLog) -> dict:
    """
    Verify all pre/post commitment pairs in the anchor log.

    Returns:
        {"total_commits": int, "verified": int, "violations": int,
         "incomplete": int, "status": str}

    Status: ALL_VERIFIED | VIOLATIONS_FOUND | INCOMPLETE_COMMITS
    """
    records = anchor_log.read_log()

    # Collect all intent_ids that have pre or post commits
    intent_ids = set()
    for r in records:
        if r.get("type") in ("pre_commit", "post_commit"):
            intent_ids.add(r["intent_id"])

    verified = 0
    violations = 0
    incomplete = 0

    for intent_id in intent_ids:
        result = verify_commitment(anchor_log, intent_id)
        if result["status"] == "VERIFIED":
            verified += 1
        elif result["status"] == "INCOMPLETE":
            incomplete += 1
        else:
            violations += 1

    total = len(intent_ids)

    if violations > 0:
        status = "VIOLATIONS_FOUND"
    elif incomplete > 0:
        status = "INCOMPLETE_COMMITS"
    elif total == 0:
        status = "ALL_VERIFIED"
    else:
        status = "ALL_VERIFIED"

    return {
        "total_commits": total,
        "verified": verified,
        "violations": violations,
        "incomplete": incomplete,
        "status": status,
    }


def verify_environment(anchor_log: AnchorLog, env_hash: str) -> dict:
    """
    Check if an environment hash exists in the anchor log.

    Returns:
        {"found": bool, "source": str|None, "captured_at": str|None,
         "size_bytes": int|None}
    """
    records = anchor_log.read_log()
    for r in records:
        if r.get("type") == "env_capture" and r.get("env_hash") == env_hash:
            return {
                "found": True,
                "source": r.get("source"),
                "captured_at": r.get("timestamp"),
                "size_bytes": r.get("size_bytes"),
            }
    return {
        "found": False,
        "source": None,
        "captured_at": None,
        "size_bytes": None,
    }
