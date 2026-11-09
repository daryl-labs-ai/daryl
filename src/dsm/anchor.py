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


# Fields of a pre_commit record covered by its commitment_hash.
_PRE_COMMIT_FIELDS = ("type", "intent_id", "action_name", "params_hash", "timestamp")


def _params_hash_of(intent_id: str, action_name: str, params: dict) -> str:
    return _sha256({
        "intent_id": intent_id,
        "action_name": action_name,
        "params": params,
    })


def _commitment_hash_of(pre_record: dict) -> str:
    """Recompute the commitment hash of a pre_commit record from its own fields."""
    body = {k: pre_record.get(k) for k in _PRE_COMMIT_FIELDS}
    return _sha256(json.dumps(body, sort_keys=True, separators=(",", ":")))


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
        """Find pre_commit and post_commit records for an intent_id.

        The last record of each type wins (historical behaviour); the counts
        are returned so verifiers can reject duplicates (shadowing).
        """
        records = self.read_log()
        result = {"pre_commit": None, "post_commit": None, "pre_count": 0, "post_count": 0}
        for r in records:
            if r.get("intent_id") == intent_id:
                if r.get("type") == "pre_commit":
                    result["pre_commit"] = r
                    result["pre_count"] += 1
                elif r.get("type") == "post_commit":
                    result["post_commit"] = r
                    result["post_count"] += 1
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
    params_hash = _params_hash_of(intent_id, action_name, params)

    record = {
        "type": "pre_commit",
        "intent_id": intent_id,
        "action_name": action_name,
        "params_hash": params_hash,
        "timestamp": timestamp,
    }

    commitment_hash = _commitment_hash_of(record)
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


def verify_commitment(
    anchor_log: AnchorLog,
    intent_id: str,
    *,
    expected_commitment_hash: Optional[str] = None,
    action_name: Optional[str] = None,
    params: Optional[dict] = None,
) -> dict:
    """
    Verify a pre/post commitment pair for an intent.

    Checks (all from the log itself):
    - exactly one pre_commit and one post_commit exist
    - pre_commit.timestamp <= post_commit.timestamp
    - pre_commit.commitment_hash is present and equals the hash recomputed from
      the pre_commit fields (action_name, params_hash, timestamp, ...)
    - post_commit.commitment_hash is present and equals it

    Optional checks against material held OUTSIDE the anchor log (the only way
    to detect a coherent rewrite of the whole pair, since the log is unkeyed):
    - expected_commitment_hash: the commitment hash returned by pre_commit()
    - action_name + params: the original intent; params_hash is recomputed

    Returns:
        {"intent_id", "status", "pre_commit_at", "post_commit_at",
         "time_delta_ms", "externally_anchored", "reason"}

    Status: VERIFIED | SEQUENCE_VIOLATION | HASH_MISMATCH | COMMITMENT_MISSING |
            PARAMS_MISMATCH | DUPLICATE_RECORD | INCOMPLETE
    """
    pair = anchor_log.find_by_intent(intent_id)
    pre = pair["pre_commit"]
    post = pair["post_commit"]
    externally_anchored = expected_commitment_hash is not None or action_name is not None

    def _result(status: str, reason: Optional[str] = None, delta=None) -> dict:
        return {
            "intent_id": intent_id,
            "status": status,
            "pre_commit_at": pre.get("timestamp") if pre else None,
            "post_commit_at": post.get("timestamp") if post else None,
            "time_delta_ms": delta,
            "externally_anchored": externally_anchored,
            "reason": reason,
        }

    if pair.get("pre_count", 0) > 1 or pair.get("post_count", 0) > 1:
        return _result("DUPLICATE_RECORD", "more than one pre_commit or post_commit for this intent")

    if pre is None or post is None:
        return _result("INCOMPLETE")

    pre_at = pre.get("timestamp")
    post_at = post.get("timestamp")
    if not isinstance(pre_at, str) or not isinstance(post_at, str):
        return _result("SEQUENCE_VIOLATION", "missing timestamp")
    if post_at < pre_at:
        return _result("SEQUENCE_VIOLATION", "post_commit precedes pre_commit")

    pre_commitment = pre.get("commitment_hash")
    post_commitment = post.get("commitment_hash")
    if not pre_commitment:
        return _result("COMMITMENT_MISSING", "pre_commit has no commitment_hash")
    if not post_commitment:
        return _result("COMMITMENT_MISSING", "post_commit is not bound to a commitment_hash")

    if _commitment_hash_of(pre) != pre_commitment:
        return _result("HASH_MISMATCH", "pre_commit fields do not match its commitment_hash")
    if post_commitment != pre_commitment:
        return _result("HASH_MISMATCH", "post_commit.commitment_hash differs from pre_commit")
    if expected_commitment_hash is not None and expected_commitment_hash != pre_commitment:
        return _result("HASH_MISMATCH", "commitment_hash differs from the externally held value")

    if action_name is not None:
        if pre.get("action_name") != action_name:
            return _result("PARAMS_MISMATCH", "action_name differs from the expected intent")
        if _params_hash_of(intent_id, action_name, params or {}) != pre.get("params_hash"):
            return _result("PARAMS_MISMATCH", "params_hash differs from the expected params")

    try:
        t_pre = datetime.fromisoformat(pre_at.replace("Z", "+00:00"))
        t_post = datetime.fromisoformat(post_at.replace("Z", "+00:00"))
        delta_ms = (t_post - t_pre).total_seconds() * 1000
    except (ValueError, TypeError):
        delta_ms = None

    return _result("VERIFIED", delta=delta_ms)


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
