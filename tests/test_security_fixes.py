"""P0 — Tests for 3 critical DSM security layer fixes."""

import pytest
from pathlib import Path

from dsm.core.security import SecurityLayer
from dsm.core import security_listener
from dsm.exchange import TaskReceipt, verify_receipt, _compute_receipt_hash, _receipt_payload


def test_forced_baseline_update_with_ack_returns_true(tmp_path):
    """Fix 1: check_baseline_gate(force=True, manual_ack='I UNDERSTAND') returns (True, ...)."""
    (tmp_path / "data" / "security").mkdir(parents=True, exist_ok=True)
    security = SecurityLayer(workspace_dir=tmp_path)
    allowed, message = security.check_baseline_gate(
        force=True, manual_ack="I UNDERSTAND", reason="test"
    )
    assert allowed is True
    assert "approved" in message.lower() or "passed" in message.lower()


def test_audit_api_call_and_generate_security_report_do_not_crash(tmp_path):
    """Fix 2: audit_api_call and generate_security_report from security_listener don't crash."""
    (tmp_path / "data" / "security").mkdir(parents=True, exist_ok=True)
    security = SecurityLayer(workspace_dir=tmp_path)
    # Patch global so listener uses our temp workspace
    security_listener._security_layer = security
    try:
        security_listener.audit_api_call("test_action", {"key": "value"})
        report = security_listener.generate_security_report()
        assert isinstance(report, str)
        assert "SECURITY" in report.upper() or "DSM" in report
    finally:
        security_listener._security_layer = None


def test_verify_receipt_signature_invalid_when_tampered(tmp_path):
    """Fix 3: verify_receipt returns SIGNATURE_INVALID and signature_verified False when signature tampered."""
    try:
        from dsm.signing import AgentSigning
    except ImportError:
        pytest.skip("PyNaCl not available")
    keys_dir = str(tmp_path / "keys")
    sign = AgentSigning(keys_dir, "alice")
    sign.generate_keypair()
    receipt_hash = "a" * 64
    sig = sign.sign_receipt(receipt_hash)
    pub = sign.get_public_key()
    # Tamper signature (flip one hex char)
    tampered_sig = sig[:-1] + ("0" if sig[-1] != "0" else "1")
    payload = {
        "receipt_id": "r1",
        "issuer_agent_id": "alice",
        "task_description": "task",
        "entry_id": "e1",
        "entry_hash": "h1",
        "shard_id": "s1",
        "shard_tip_hash": "t1",
        "shard_entry_count": 1,
        "timestamp": "2026-01-01T00:00:00Z",
    }
    receipt = TaskReceipt(
        receipt_id="r1",
        issuer_agent_id="alice",
        task_description="task",
        entry_id="e1",
        entry_hash="h1",
        shard_id="s1",
        shard_tip_hash="t1",
        shard_entry_count=1,
        timestamp="2026-01-01T00:00:00Z",
        receipt_hash=_compute_receipt_hash(payload),
        signature=tampered_sig,
        public_key=pub,
    )
    result = verify_receipt(receipt)
    assert result["signature_verified"] is False
    assert result["status"] == "SIGNATURE_INVALID"


def test_verify_receipt_signature_verified_true_when_valid(tmp_path):
    """Fix 3: verify_receipt returns signature_verified True when signature is valid."""
    try:
        from dsm.signing import AgentSigning
    except ImportError:
        pytest.skip("PyNaCl not available")
    keys_dir = str(tmp_path / "keys")
    sign = AgentSigning(keys_dir, "bob")
    sign.generate_keypair()
    payload = {
        "receipt_id": "r2",
        "issuer_agent_id": "bob",
        "task_description": "task2",
        "entry_id": "e2",
        "entry_hash": "h2",
        "shard_id": "s2",
        "shard_tip_hash": "t2",
        "shard_entry_count": 2,
        "timestamp": "2026-01-01T00:00:00Z",
    }
    receipt_hash = _compute_receipt_hash(payload)
    sig = sign.sign_receipt(receipt_hash)
    pub = sign.get_public_key()
    receipt = TaskReceipt(
        receipt_id="r2",
        issuer_agent_id="bob",
        task_description="task2",
        entry_id="e2",
        entry_hash="h2",
        shard_id="s2",
        shard_tip_hash="t2",
        shard_entry_count=2,
        timestamp="2026-01-01T00:00:00Z",
        receipt_hash=receipt_hash,
        signature=sig,
        public_key=pub,
    )
    result = verify_receipt(receipt)
    assert result["signature_verified"] is True
    assert result["status"] == "INTACT"


# --- P1 tests (Fix 4: file-based write token) ---


def _enable_protected_files(tmp_path):
    """Enable protected files in policy so check_protected_write can deny/allow."""
    import json
    security_dir = tmp_path / "data" / "security"
    security_dir.mkdir(parents=True, exist_ok=True)
    policy = {
        "protected_files": {
            "enabled": True,
            "allow_rewrite": False,
            "token_file": ".dsm_write_token",
            "protected_paths": ["src/dsm/core/security.py"],
        }
    }
    (security_dir / "policy.json").write_text(json.dumps(policy))


def test_env_var_bypass_no_longer_works(tmp_path):
    """DSM_SECURITY_REWRITE_OK=1 should NOT bypass file protection anymore."""
    import os
    _enable_protected_files(tmp_path)
    os.environ["DSM_SECURITY_REWRITE_OK"] = "1"
    try:
        sl = SecurityLayer(workspace_dir=tmp_path)
        allowed, msg = sl.check_protected_write("src/dsm/core/security.py")
        assert not allowed, "Env var bypass should no longer work"
    finally:
        os.environ.pop("DSM_SECURITY_REWRITE_OK", None)


def test_write_token_grants_access(tmp_path):
    """A fresh .dsm_write_token file should grant one-time write access."""
    import uuid
    _enable_protected_files(tmp_path)
    sl = SecurityLayer(workspace_dir=tmp_path)
    token_path = tmp_path / ".dsm_write_token"
    token_path.write_text(str(uuid.uuid4()))
    allowed, msg = sl.check_protected_write("src/dsm/core/security.py")
    assert allowed, f"Write token should grant access: {msg}"
    assert not token_path.exists(), "Token should be deleted after use (single-use)"


def test_expired_write_token_denied(tmp_path):
    """A write token older than 60s should be rejected."""
    import uuid
    import os
    import time
    _enable_protected_files(tmp_path)
    sl = SecurityLayer(workspace_dir=tmp_path)
    token_path = tmp_path / ".dsm_write_token"
    token_path.write_text(str(uuid.uuid4()))
    # Backdate the file
    old_time = time.time() - 120
    os.utime(token_path, (old_time, old_time))
    allowed, msg = sl.check_protected_write("src/dsm/core/security.py")
    assert not allowed, "Expired token should be denied"
