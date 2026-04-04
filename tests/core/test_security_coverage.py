"""
Tests for core/security.py — targeting uncovered lines (49% → 80%+).

Covers:
  - SecurityLayer init
  - compute_file_hash
  - verify_integrity (NEW files, MODIFIED files, MISSING files)
  - check_baseline_gate (all gate conditions)
  - update_baseline (normal, forced, double-ack)
  - audit_action (api_request, file_write, external_connection, rate limit exceeded)
  - check_rate_limit
  - get_cycle_stats / reset_cycle
  - self_check
  - generate_report
  - check_protected_write (disabled, enabled, token override, expired token)
  - safe_write_protected
  - _verify_chain_integrity (valid, broken, missing)
  - _check_git_status
  - _audit_event
"""

import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from dsm.core.security import (
    SecurityLayer,
    MAX_API_REQUESTS_PER_CYCLE,
    MAX_FILE_WRITES_PER_CYCLE,
)


@pytest.fixture
def sec(tmp_path):
    return SecurityLayer(workspace_dir=tmp_path)


@pytest.fixture
def sec_with_files(tmp_path):
    """SecurityLayer with some critical files present."""
    # Create a src/dsm/core directory with a fake models.py
    core_dir = tmp_path / "src" / "dsm" / "core"
    core_dir.mkdir(parents=True)
    (core_dir / "models.py").write_text("# models\n")
    (core_dir / "storage.py").write_text("# storage\n")
    (core_dir / "signing.py").write_text("# signing\n")
    (core_dir / "shard_segments.py").write_text("# segments\n")
    (core_dir / "replay.py").write_text("# replay\n")
    (core_dir / "security.py").write_text("# security\n")
    return SecurityLayer(workspace_dir=tmp_path)


# ---------------------------------------------------------------------------
# Init & file hash
# ---------------------------------------------------------------------------

class TestInit:
    def test_creates_security_dir(self, sec, tmp_path):
        assert (tmp_path / "data" / "security").exists()

    def test_cycle_stats_initialized(self, sec):
        stats = sec.get_cycle_stats()
        assert stats["api_requests"] == 0
        assert stats["file_writes"] == 0


class TestComputeFileHash:
    def test_existing_file(self, sec, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        h = sec.compute_file_hash(f)
        assert h is not None
        assert len(h) == 64  # SHA256 hex

    def test_missing_file(self, sec, tmp_path):
        h = sec.compute_file_hash(tmp_path / "nonexistent.txt")
        assert h is None


# ---------------------------------------------------------------------------
# verify_integrity
# ---------------------------------------------------------------------------

class TestVerifyIntegrity:
    def test_first_scan_returns_results(self, sec_with_files):
        result = sec_with_files.verify_integrity()
        assert "files" in result
        assert "has_anomalies" in result
        assert isinstance(result["files"], dict)

    def test_detects_modified_file(self, sec_with_files, tmp_path):
        # First scan to establish baseline
        sec_with_files.verify_integrity()
        # Modify a file
        (tmp_path / "src" / "dsm" / "core" / "models.py").write_text("# MODIFIED\n")
        # Second scan should detect change
        result = sec_with_files.verify_integrity()
        assert result["has_anomalies"] is True

    def test_missing_file_returns_none(self, sec):
        result = sec.verify_integrity()
        # All CRITICAL_FILES are missing → None status
        for status in result["files"].values():
            assert status is None


# ---------------------------------------------------------------------------
# check_baseline_gate
# ---------------------------------------------------------------------------

class TestCheckBaselineGate:
    def test_force_without_ack(self, sec):
        allowed, msg = sec.check_baseline_gate(force=True, manual_ack="wrong")
        assert allowed is False

    def test_force_with_correct_ack(self, sec):
        allowed, msg = sec.check_baseline_gate(force=True, manual_ack="I UNDERSTAND")
        assert allowed is True

    def test_missing_reason(self, sec):
        with patch.object(sec, '_check_git_status', return_value={}):
            allowed, msg = sec.check_baseline_gate(reason=None, manual_ack="I UNDERSTAND")
            assert allowed is False
            assert "reason" in msg.lower()

    def test_missing_manual_ack(self, sec):
        with patch.object(sec, '_check_git_status', return_value={}):
            allowed, msg = sec.check_baseline_gate(reason="test", manual_ack=None)
            assert allowed is False
            assert "acknowledgment" in msg.lower()

    def test_all_checks_pass(self, sec):
        # _check_git_status must return a truthy dict with "clean" values to pass
        with patch.object(sec, '_check_git_status', return_value={"file.py": "clean"}):
            allowed, msg = sec.check_baseline_gate(reason="test", manual_ack="I UNDERSTAND")
            assert allowed is True

    def test_dirty_git(self, sec):
        with patch.object(sec, '_check_git_status', return_value={"file.py": "modified"}):
            allowed, msg = sec.check_baseline_gate(reason="test", manual_ack="I UNDERSTAND")
            assert allowed is False
            assert "dirty" in msg.lower() or "Git" in msg


# ---------------------------------------------------------------------------
# update_baseline
# ---------------------------------------------------------------------------

class TestUpdateBaseline:
    def test_forced_without_double_ack(self, sec):
        success, msg = sec.update_baseline(reason="test", force=True, manual_ack="I UNDERSTAND")
        assert success is False
        assert "Refused" in msg

    def test_forced_with_double_ack(self, sec_with_files):
        success, msg = sec_with_files.update_baseline(
            reason="test", force=True, manual_ack="I UNDERSTAND I UNDERSTAND"
        )
        assert success is True
        assert "Baseline updated" in msg

    def test_normal_fails_without_gates(self, sec):
        with patch.object(sec, '_check_git_status', return_value={"f": "modified"}):
            success, msg = sec.update_baseline(reason="test")
            assert success is False


# ---------------------------------------------------------------------------
# audit_action & rate limiting
# ---------------------------------------------------------------------------

class TestAuditAction:
    def test_api_request_increments(self, sec):
        sec.audit_action("api_request", {"url": "http://test"})
        assert sec.cycle_stats["api_requests"] == 1

    def test_file_write_increments(self, sec):
        sec.audit_action("file_write", {"path": "/tmp/f"})
        assert sec.cycle_stats["file_writes"] == 1

    def test_append_shard_increments_file_writes(self, sec):
        sec.audit_action("append_shard", {"shard": "s1"})
        assert sec.cycle_stats["file_writes"] == 1

    def test_external_connection_increments(self, sec):
        sec.audit_action("external_connection", {"host": "api.example.com"})
        assert sec.cycle_stats["external_connections"] == 1

    def test_rate_limit_exceeded_api(self, sec):
        for i in range(MAX_API_REQUESTS_PER_CYCLE + 1):
            sec.audit_action("api_request", {"i": i})
        assert sec.cycle_stats["api_requests"] > MAX_API_REQUESTS_PER_CYCLE

    def test_rate_limit_exceeded_file(self, sec):
        for i in range(MAX_FILE_WRITES_PER_CYCLE + 1):
            sec.audit_action("file_write", {"i": i})
        assert sec.cycle_stats["file_writes"] > MAX_FILE_WRITES_PER_CYCLE


class TestCheckRateLimit:
    def test_api_under_limit(self, sec):
        allowed, msg = sec.check_rate_limit("api_request")
        assert allowed is True

    def test_api_over_limit(self, sec):
        sec.cycle_stats["api_requests"] = MAX_API_REQUESTS_PER_CYCLE
        allowed, msg = sec.check_rate_limit("api_request")
        assert allowed is False

    def test_file_write_under_limit(self, sec):
        allowed, msg = sec.check_rate_limit("file_write")
        assert allowed is True

    def test_file_write_over_limit(self, sec):
        sec.cycle_stats["file_writes"] = MAX_FILE_WRITES_PER_CYCLE
        allowed, msg = sec.check_rate_limit("file_write")
        assert allowed is False

    def test_unknown_type_allowed(self, sec):
        allowed, msg = sec.check_rate_limit("unknown_type")
        assert allowed is True


class TestCycleStats:
    def test_get_cycle_stats(self, sec):
        stats = sec.get_cycle_stats()
        assert "api_requests" in stats
        assert "file_writes" in stats

    def test_reset_cycle(self, sec):
        sec.cycle_stats["api_requests"] = 5
        sec.reset_cycle()
        assert sec.cycle_stats["api_requests"] == 0


# ---------------------------------------------------------------------------
# self_check
# ---------------------------------------------------------------------------

class TestSelfCheck:
    def test_self_check_returns_report(self, sec):
        report = sec.self_check()
        assert "security_status" in report
        assert "anomalies" in report
        assert "integrity" in report
        assert "chain_status" in report

    def test_self_check_ok_status(self, sec):
        report = sec.self_check()
        assert report["security_status"] in ("OK", "WARNING")

    def test_self_check_with_chain_break(self, sec, tmp_path):
        # Create a broken chain file
        chain_dir = tmp_path / "data" / "integrity"
        chain_dir.mkdir(parents=True)
        chain_data = {
            "entries": [
                {"id": "1", "hash": "aaa", "prev_hash": None},
                {"id": "2", "hash": "bbb", "prev_hash": "WRONG"},
            ]
        }
        (chain_dir / "chain.json").write_text(json.dumps(chain_data))
        report = sec.self_check()
        assert any("chain" in a.lower() or "Chain" in a for a in report["anomalies"])


# ---------------------------------------------------------------------------
# generate_report
# ---------------------------------------------------------------------------

class TestGenerateReport:
    def test_returns_string(self, sec):
        report = sec.generate_report()
        assert isinstance(report, str)
        assert "SECURITY REPORT" in report

    def test_report_contains_sections(self, sec):
        report = sec.generate_report()
        assert "Critical File" in report
        assert "Git Status" in report
        assert "Integrity Chain" in report
        assert "Cycle Stats" in report


# ---------------------------------------------------------------------------
# check_protected_write
# ---------------------------------------------------------------------------

class TestCheckProtectedWrite:
    def test_protection_disabled(self, sec):
        # Default policy has protection disabled
        allowed, msg = sec.check_protected_write("src/dsm/core/security.py")
        assert allowed is True

    def test_protection_enabled_blocked(self, sec, tmp_path):
        # Create policy with protection enabled
        policy = {
            "protected_files": {
                "enabled": True,
                "allow_rewrite": False,
                "token_file": ".dsm_write_token",
                "protected_paths": ["src/dsm/core/security.py"],
            }
        }
        policy_file = tmp_path / "data" / "security" / "policy.json"
        policy_file.write_text(json.dumps(policy))
        allowed, msg = sec.check_protected_write("src/dsm/core/security.py")
        assert allowed is False

    def test_protection_enabled_allow_rewrite(self, sec, tmp_path):
        policy = {
            "protected_files": {
                "enabled": True,
                "allow_rewrite": True,
                "protected_paths": ["src/dsm/core/security.py"],
            }
        }
        policy_file = tmp_path / "data" / "security" / "policy.json"
        policy_file.write_text(json.dumps(policy))
        allowed, msg = sec.check_protected_write("src/dsm/core/security.py")
        assert allowed is True

    def test_protection_token_override(self, sec, tmp_path):
        policy = {
            "protected_files": {
                "enabled": True,
                "allow_rewrite": False,
                "token_file": ".dsm_write_token",
                "protected_paths": ["src/dsm/core/security.py"],
            }
        }
        (tmp_path / "data" / "security" / "policy.json").write_text(json.dumps(policy))
        # Create a fresh token file
        token = tmp_path / ".dsm_write_token"
        token.write_text("nonce-123")
        allowed, msg = sec.check_protected_write("src/dsm/core/security.py")
        assert allowed is True
        # Token should be deleted (single-use)
        assert not token.exists()

    def test_protection_expired_token(self, sec, tmp_path):
        policy = {
            "protected_files": {
                "enabled": True,
                "allow_rewrite": False,
                "token_file": ".dsm_write_token",
                "protected_paths": ["src/dsm/core/security.py"],
            }
        }
        (tmp_path / "data" / "security" / "policy.json").write_text(json.dumps(policy))
        token = tmp_path / ".dsm_write_token"
        token.write_text("old-nonce")
        # Make it old
        import os
        old_time = time.time() - 120
        os.utime(str(token), (old_time, old_time))
        allowed, msg = sec.check_protected_write("src/dsm/core/security.py")
        assert allowed is False

    def test_non_protected_file(self, sec, tmp_path):
        policy = {
            "protected_files": {
                "enabled": True,
                "allow_rewrite": False,
                "protected_paths": ["src/dsm/core/security.py"],
            }
        }
        (tmp_path / "data" / "security" / "policy.json").write_text(json.dumps(policy))
        allowed, msg = sec.check_protected_write("src/dsm/some_other.py")
        assert allowed is True

    def test_deprecated_env_var_warning(self, sec, tmp_path):
        policy = {
            "protected_files": {
                "enabled": True,
                "allow_rewrite": False,
                "token_file": ".dsm_write_token",
                "protected_paths": ["src/dsm/core/security.py"],
            }
        }
        (tmp_path / "data" / "security" / "policy.json").write_text(json.dumps(policy))
        with patch.dict("os.environ", {"DSM_SECURITY_REWRITE_OK": "1"}):
            allowed, msg = sec.check_protected_write("src/dsm/core/security.py")
            # Should still be blocked (env var deprecated)
            assert allowed is False


# ---------------------------------------------------------------------------
# safe_write_protected
# ---------------------------------------------------------------------------

class TestSafeWriteProtected:
    def test_writes_non_protected_file(self, sec, tmp_path):
        target = tmp_path / "output" / "test.txt"
        result = sec.safe_write_protected(target, "content")
        assert result is True
        assert target.read_text() == "content"

    def test_blocked_on_protected(self, sec, tmp_path, capsys):
        policy = {
            "protected_files": {
                "enabled": True,
                "allow_rewrite": False,
                "protected_paths": ["blocked.py"],
            }
        }
        (tmp_path / "data" / "security" / "policy.json").write_text(json.dumps(policy))
        result = sec.safe_write_protected(tmp_path / "blocked.py", "content")
        assert result is False


# ---------------------------------------------------------------------------
# _verify_chain_integrity
# ---------------------------------------------------------------------------

class TestVerifyChainIntegrity:
    def test_no_chain_file(self, sec):
        result = sec._verify_chain_integrity()
        assert result["valid"] is True
        assert result["entries"] == 0

    def test_valid_chain(self, sec, tmp_path):
        chain_dir = tmp_path / "data" / "integrity"
        chain_dir.mkdir(parents=True)
        chain_data = {
            "entries": [
                {"id": "1", "hash": "aaa", "prev_hash": None},
                {"id": "2", "hash": "bbb", "prev_hash": "aaa"},
                {"id": "3", "hash": "ccc", "prev_hash": "bbb"},
            ]
        }
        (chain_dir / "chain.json").write_text(json.dumps(chain_data))
        result = sec._verify_chain_integrity()
        assert result["valid"] is True
        assert result["entries"] == 3

    def test_broken_chain(self, sec, tmp_path):
        chain_dir = tmp_path / "data" / "integrity"
        chain_dir.mkdir(parents=True)
        chain_data = {
            "entries": [
                {"id": "1", "hash": "aaa", "prev_hash": None},
                {"id": "2", "hash": "bbb", "prev_hash": "WRONG"},
            ]
        }
        (chain_dir / "chain.json").write_text(json.dumps(chain_data))
        result = sec._verify_chain_integrity()
        assert result["valid"] is False

    def test_missing_hash_entry(self, sec, tmp_path):
        chain_dir = tmp_path / "data" / "integrity"
        chain_dir.mkdir(parents=True)
        chain_data = {
            "entries": [
                {"id": "1", "hash": None},
            ]
        }
        (chain_dir / "chain.json").write_text(json.dumps(chain_data))
        result = sec._verify_chain_integrity()
        assert result["valid"] is False

    def test_empty_entries(self, sec, tmp_path):
        chain_dir = tmp_path / "data" / "integrity"
        chain_dir.mkdir(parents=True)
        (chain_dir / "chain.json").write_text(json.dumps({"entries": []}))
        result = sec._verify_chain_integrity()
        assert result["valid"] is True
        assert result["entries"] == 0

    def test_corrupt_json(self, sec, tmp_path):
        chain_dir = tmp_path / "data" / "integrity"
        chain_dir.mkdir(parents=True)
        (chain_dir / "chain.json").write_text("NOT_JSON")
        result = sec._verify_chain_integrity()
        assert result["valid"] is False


# ---------------------------------------------------------------------------
# _check_git_status
# ---------------------------------------------------------------------------

class TestCheckGitStatus:
    def test_returns_dict(self, sec):
        result = sec._check_git_status()
        assert isinstance(result, dict)

    def test_handles_git_not_available(self, sec):
        with patch("subprocess.run", side_effect=Exception("git not found")):
            result = sec._check_git_status()
            assert result == {}


# ---------------------------------------------------------------------------
# audit_external_action
# ---------------------------------------------------------------------------

class TestAuditExternalAction:
    def test_logs_event(self, sec, tmp_path):
        sec.audit_external_action("test_event", {"key": "value"})
        audit_log = tmp_path / "data" / "security" / "audit.jsonl"
        assert audit_log.exists()
        lines = audit_log.read_text().strip().split("\n")
        event = json.loads(lines[-1])
        assert event["type"] == "test_event"
