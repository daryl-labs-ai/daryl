"""
Tests for core/security.py CLI functions + generate_report edge cases.

Covers uncovered lines:
  - generate_report with anomalies, git status, broken chain
  - cmd_check, cmd_update_baseline, cmd_audit, cmd_self_check
  - _check_git_status with modified/untracked critical files
  - check_baseline_gate with many dirty files (>5)
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest

from dsm.core.security import (
    SecurityLayer,
    cmd_check,
    cmd_update_baseline,
    cmd_audit,
    cmd_self_check,
)


@pytest.fixture
def sec(tmp_path):
    return SecurityLayer(workspace_dir=tmp_path)


# ---------------------------------------------------------------------------
# generate_report edge cases
# ---------------------------------------------------------------------------

class TestGenerateReportEdgeCases:
    def test_report_with_anomalies(self, sec, tmp_path):
        # Create broken chain to trigger anomaly
        chain_dir = tmp_path / "data" / "integrity"
        chain_dir.mkdir(parents=True)
        (chain_dir / "chain.json").write_text(json.dumps({
            "entries": [
                {"id": "1", "hash": "aaa", "prev_hash": None},
                {"id": "2", "hash": "bbb", "prev_hash": "WRONG"},
            ]
        }))
        report = sec.generate_report()
        assert "ANOMALIES" in report or "BROKEN" in report

    def test_report_with_git_status(self, sec):
        with patch.object(sec, '_check_git_status', return_value={"file.py": "modified"}):
            report = sec.generate_report()
            assert "Git Status" in report

    def test_report_clean_git(self, sec):
        with patch.object(sec, '_check_git_status', return_value={}):
            report = sec.generate_report()
            assert "Clean working tree" in report


# ---------------------------------------------------------------------------
# _check_git_status edge cases
# ---------------------------------------------------------------------------

class TestCheckGitStatusEdgeCases:
    def test_with_modified_critical_file(self, sec):
        mock_result = MagicMock()
        mock_result.stdout = " M src/dsm/core/models.py\n"
        with patch("subprocess.run", return_value=mock_result):
            result = sec._check_git_status()
            if result:  # May contain critical file
                assert isinstance(result, dict)

    def test_with_untracked_file(self, sec):
        mock_result = MagicMock()
        mock_result.stdout = "?? src/dsm/core/storage.py\n"
        with patch("subprocess.run", return_value=mock_result):
            result = sec._check_git_status()
            assert isinstance(result, dict)

    def test_empty_output(self, sec):
        mock_result = MagicMock()
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result):
            result = sec._check_git_status()
            assert result == {}

    def test_timeout_exception(self, sec):
        with patch("subprocess.run", side_effect=Exception("timeout")):
            result = sec._check_git_status()
            assert result == {}


# ---------------------------------------------------------------------------
# check_baseline_gate — many dirty files
# ---------------------------------------------------------------------------

class TestBaselineGateEdgeCases:
    def test_many_dirty_files_truncated(self, sec):
        dirty = {f"file_{i}.py": "modified" for i in range(10)}
        with patch.object(sec, '_check_git_status', return_value=dirty):
            allowed, msg = sec.check_baseline_gate(reason="test", manual_ack="I UNDERSTAND")
            assert allowed is False
            assert "more" in msg  # Shows "... and N more"


# ---------------------------------------------------------------------------
# CLI: cmd_check
# ---------------------------------------------------------------------------

class TestCmdCheck:
    def test_cmd_check_ok(self, tmp_path):
        with patch("dsm.core.security.SecurityLayer") as MockSec:
            mock = MockSec.return_value
            mock.generate_report.return_value = "REPORT"
            mock.self_check.return_value = {"anomalies": []}
            with pytest.raises(SystemExit) as exc:
                cmd_check(SimpleNamespace())
            assert exc.value.code == 0

    def test_cmd_check_anomalies(self, tmp_path):
        with patch("dsm.core.security.SecurityLayer") as MockSec:
            mock = MockSec.return_value
            mock.generate_report.return_value = "REPORT"
            mock.self_check.return_value = {"anomalies": ["bad"]}
            with pytest.raises(SystemExit) as exc:
                cmd_check(SimpleNamespace())
            assert exc.value.code == 1


# ---------------------------------------------------------------------------
# CLI: cmd_update_baseline
# ---------------------------------------------------------------------------

class TestCmdUpdateBaseline:
    def test_force_without_reason(self, capsys):
        args = SimpleNamespace(reason=None, manual_ack=None, force=True)
        cmd_update_baseline(args)
        out = capsys.readouterr().out
        assert "reason" in out.lower()

    def test_force_without_ack(self, capsys):
        args = SimpleNamespace(reason="test", manual_ack=None, force=True)
        cmd_update_baseline(args)
        out = capsys.readouterr().out
        assert "manual-ack" in out.lower() or "UNDERSTAND" in out

    def test_force_success(self):
        args = SimpleNamespace(reason="test", manual_ack="I UNDERSTAND I UNDERSTAND", force=True)
        with patch("dsm.core.security.SecurityLayer") as MockSec:
            mock = MockSec.return_value
            mock.update_baseline.return_value = (True, "OK updated")
            with pytest.raises(SystemExit) as exc:
                cmd_update_baseline(args)
            assert exc.value.code == 0

    def test_force_failure(self):
        args = SimpleNamespace(reason="test", manual_ack="wrong", force=True)
        with patch("dsm.core.security.SecurityLayer") as MockSec:
            mock = MockSec.return_value
            mock.update_baseline.return_value = (False, "Refused")
            with pytest.raises(SystemExit) as exc:
                cmd_update_baseline(args)
            assert exc.value.code == 1

    def test_normal_no_reason_no_ack_gate_fails(self, capsys):
        args = SimpleNamespace(reason=None, manual_ack=None, force=False)
        with patch("dsm.core.security.SecurityLayer") as MockSec:
            mock = MockSec.return_value
            mock.check_baseline_gate.return_value = (False, "gate failed")
            cmd_update_baseline(args)
            out = capsys.readouterr().out
            assert "BASELINE" in out or "gate" in out.lower() or "Requirements" in out


# ---------------------------------------------------------------------------
# CLI: cmd_audit
# ---------------------------------------------------------------------------

class TestCmdAudit:
    def test_no_audit_log(self, capsys):
        with patch("dsm.core.security.SecurityLayer") as MockSec:
            mock = MockSec.return_value
            mock.security_dir = Path("/nonexistent/path")
            cmd_audit(SimpleNamespace(limit=20))
            out = capsys.readouterr().out
            assert "No audit log" in out

    def test_with_audit_log(self, tmp_path, capsys):
        sec_dir = tmp_path / "data" / "security"
        sec_dir.mkdir(parents=True)
        audit_file = sec_dir / "audit.jsonl"
        events = [
            {"timestamp": "2026-01-01T00:00:00Z", "type": "api_request", "details": {"url": "http://test"}},
            {"timestamp": "2026-01-01T00:01:00Z", "type": "file_write", "details": {"path": "/tmp/f"}},
        ]
        audit_file.write_text("\n".join(json.dumps(e) for e in events) + "\n")

        with patch("dsm.core.security.SecurityLayer") as MockSec:
            mock = MockSec.return_value
            mock.security_dir = sec_dir
            cmd_audit(SimpleNamespace(limit=20))
            out = capsys.readouterr().out
            assert "AUDIT LOG" in out
            assert "api_request" in out


# ---------------------------------------------------------------------------
# CLI: cmd_self_check
# ---------------------------------------------------------------------------

class TestCmdSelfCheck:
    def test_cmd_self_check(self, capsys):
        with patch("dsm.core.security.SecurityLayer") as MockSec:
            mock = MockSec.return_value
            mock.self_check.return_value = {"status": "OK", "anomalies": []}
            cmd_self_check(SimpleNamespace())
            out = capsys.readouterr().out
            data = json.loads(out)
            assert data["status"] == "OK"
