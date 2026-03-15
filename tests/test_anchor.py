"""Tests for dsm.anchor — Pre-commitment & Environment Anchoring (P4)."""

import json
import time

from dsm.anchor import (
    AnchorLog,
    pre_commit,
    post_commit,
    capture_environment,
    verify_commitment,
    verify_all_commitments,
    verify_environment,
    _sha256,
)


# --- Pre-commitment tests ---


def test_pre_commit_creates_record(tmp_path):
    """Pre-commit writes a record to anchor_log."""
    log = AnchorLog(str(tmp_path / "anchors"))
    result = pre_commit(log, "intent-1", "call_api", {"url": "https://example.com"})

    assert result["intent_id"] == "intent-1"
    assert result["params_hash"]
    assert result["commitment_hash"]

    records = log.read_log()
    assert len(records) == 1
    assert records[0]["type"] == "pre_commit"
    assert records[0]["intent_id"] == "intent-1"


def test_pre_commit_params_hash_deterministic(tmp_path):
    """Same action + params = same params_hash."""
    log = AnchorLog(str(tmp_path / "anchors"))
    r1 = pre_commit(log, "i-1", "call_api", {"url": "https://a.com"})
    r2 = pre_commit(log, "i-1", "call_api", {"url": "https://a.com"})
    assert r1["params_hash"] == r2["params_hash"]


def test_post_commit_links_to_pre(tmp_path):
    """Post-commit carries the commitment_hash from pre-commit."""
    log = AnchorLog(str(tmp_path / "anchors"))
    pre = pre_commit(log, "i-2", "fetch", {"id": 42})
    post = post_commit(log, "i-2", {"status": "ok"}, commitment_hash=pre["commitment_hash"])

    assert post["commitment_hash"] == pre["commitment_hash"]
    assert post["result_hash"]
    assert post["intent_id"] == "i-2"


def test_post_commit_with_raw_input(tmp_path):
    """Post-commit hashes raw_input when provided."""
    log = AnchorLog(str(tmp_path / "anchors"))
    pre = pre_commit(log, "i-3", "search", {"q": "test"})
    post = post_commit(log, "i-3", "result", raw_input=b"raw response bytes", commitment_hash=pre["commitment_hash"])

    assert post["input_hash"] is not None
    assert post["input_hash"] == _sha256(b"raw response bytes")


# --- Verification tests ---


def test_verify_commitment_valid(tmp_path):
    """Valid pre→post pair = VERIFIED."""
    log = AnchorLog(str(tmp_path / "anchors"))
    pre = pre_commit(log, "i-4", "action", {"x": 1})
    post_commit(log, "i-4", "done", commitment_hash=pre["commitment_hash"])

    result = verify_commitment(log, "i-4")
    assert result["status"] == "VERIFIED"
    assert result["pre_commit_at"] is not None
    assert result["post_commit_at"] is not None
    assert result["time_delta_ms"] is not None
    assert result["time_delta_ms"] >= 0


def test_verify_commitment_hash_mismatch(tmp_path):
    """Tampered commitment_hash = HASH_MISMATCH."""
    log = AnchorLog(str(tmp_path / "anchors"))
    pre = pre_commit(log, "i-5", "action", {"x": 1})
    post_commit(log, "i-5", "done", commitment_hash="tampered_hash_value")

    result = verify_commitment(log, "i-5")
    assert result["status"] == "HASH_MISMATCH"


def test_verify_commitment_incomplete_no_post(tmp_path):
    """Pre without post = INCOMPLETE."""
    log = AnchorLog(str(tmp_path / "anchors"))
    pre_commit(log, "i-6", "action", {"x": 1})

    result = verify_commitment(log, "i-6")
    assert result["status"] == "INCOMPLETE"


def test_verify_commitment_incomplete_no_records(tmp_path):
    """Unknown intent_id = INCOMPLETE."""
    log = AnchorLog(str(tmp_path / "anchors"))
    result = verify_commitment(log, "nonexistent")
    assert result["status"] == "INCOMPLETE"


def test_verify_all_commitments_clean(tmp_path):
    """All valid pairs = ALL_VERIFIED."""
    log = AnchorLog(str(tmp_path / "anchors"))
    for i in range(3):
        pre = pre_commit(log, f"i-{i}", "action", {"n": i})
        post_commit(log, f"i-{i}", f"result-{i}", commitment_hash=pre["commitment_hash"])

    result = verify_all_commitments(log)
    assert result["status"] == "ALL_VERIFIED"
    assert result["total_commits"] == 3
    assert result["verified"] == 3
    assert result["violations"] == 0


def test_verify_all_commitments_mixed(tmp_path):
    """Mix of valid and incomplete = INCOMPLETE_COMMITS."""
    log = AnchorLog(str(tmp_path / "anchors"))
    # One complete pair
    pre = pre_commit(log, "i-ok", "action", {"n": 1})
    post_commit(log, "i-ok", "done", commitment_hash=pre["commitment_hash"])
    # One incomplete (no post)
    pre_commit(log, "i-orphan", "action", {"n": 2})

    result = verify_all_commitments(log)
    assert result["total_commits"] == 2
    assert result["verified"] == 1
    assert result["incomplete"] == 1
    assert result["status"] == "INCOMPLETE_COMMITS"


def test_verify_all_with_violation(tmp_path):
    """Tampered pair = VIOLATIONS_FOUND."""
    log = AnchorLog(str(tmp_path / "anchors"))
    pre = pre_commit(log, "i-bad", "action", {"n": 1})
    post_commit(log, "i-bad", "done", commitment_hash="wrong")

    result = verify_all_commitments(log)
    assert result["status"] == "VIOLATIONS_FOUND"
    assert result["violations"] == 1


# --- Environment capture tests ---


def test_capture_environment_string(tmp_path):
    """String data produces correct env_hash."""
    log = AnchorLog(str(tmp_path / "anchors"))
    result = capture_environment(log, "api:weather", "temp=20C")

    assert result["env_hash"] == _sha256("temp=20C")
    assert result["source"] == "api:weather"
    assert result["size_bytes"] == len("temp=20C".encode("utf-8"))


def test_capture_environment_dict(tmp_path):
    """Dict data is sorted-JSON hashed."""
    log = AnchorLog(str(tmp_path / "anchors"))
    data = {"temp": 20, "city": "Paris"}
    result = capture_environment(log, "api:weather", data)

    assert result["env_hash"] == _sha256(data)
    assert result["size_bytes"] > 0


def test_capture_environment_with_headers(tmp_path):
    """Headers produce a header_hash."""
    log = AnchorLog(str(tmp_path / "anchors"))
    headers = {"Content-Type": "application/json", "X-Request-Id": "abc"}
    result = capture_environment(log, "api:test", "body", headers=headers)

    assert result["header_hash"] is not None
    assert result["header_hash"] == _sha256(headers)


def test_capture_environment_bytes(tmp_path):
    """Bytes data hashed correctly."""
    log = AnchorLog(str(tmp_path / "anchors"))
    data = b'\x00\x01\x02binary data'
    result = capture_environment(log, "file:binary", data)

    assert result["env_hash"] == _sha256(data)
    assert result["size_bytes"] == len(data)


def test_verify_environment_found(tmp_path):
    """Known env_hash is found."""
    log = AnchorLog(str(tmp_path / "anchors"))
    cap = capture_environment(log, "api:test", "hello world")

    result = verify_environment(log, cap["env_hash"])
    assert result["found"] is True
    assert result["source"] == "api:test"
    assert result["captured_at"] is not None


def test_verify_environment_not_found(tmp_path):
    """Unknown env_hash returns found=False."""
    log = AnchorLog(str(tmp_path / "anchors"))
    result = verify_environment(log, "0000000000000000")
    assert result["found"] is False
    assert result["source"] is None


# --- AnchorLog edge cases ---


def test_empty_anchor_log(tmp_path):
    """Empty log returns empty list."""
    log = AnchorLog(str(tmp_path / "anchors"))
    assert log.read_log() == []


def test_find_by_intent_returns_pair(tmp_path):
    """find_by_intent returns both pre and post."""
    log = AnchorLog(str(tmp_path / "anchors"))
    pre_commit(log, "i-find", "action", {"x": 1})
    post_commit(log, "i-find", "result")

    pair = log.find_by_intent("i-find")
    assert pair["pre_commit"] is not None
    assert pair["post_commit"] is not None
    assert pair["pre_commit"]["type"] == "pre_commit"
    assert pair["post_commit"]["type"] == "post_commit"
