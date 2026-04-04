"""
Tests for core/security_listener.py — targeting uncovered lines.

Covers:
  - get_security_layer (singleton init + self-check)
  - audit_api_call / audit_file_operation
  - run_periodic_security_check
  - generate_security_report
  - update_security_baseline
  - secure_api_call (rate limit, success, exception)
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from dsm.core import security_listener


@pytest.fixture(autouse=True)
def reset_global():
    """Reset the global security layer singleton between tests."""
    security_listener._security_layer = None
    yield
    security_listener._security_layer = None


@pytest.fixture
def mock_security_layer():
    """Provide a mocked SecurityLayer."""
    mock = MagicMock()
    mock.self_check.return_value = {
        "security_status": "OK",
        "anomalies": [],
    }
    mock.cycle_stats = {"api_requests": 0}
    mock.generate_report.return_value = {"status": "OK"}
    return mock


class TestGetSecurityLayer:
    def test_creates_singleton(self, mock_security_layer):
        with patch("dsm.core.security_listener.SecurityLayer", return_value=mock_security_layer):
            layer = security_listener.get_security_layer()
            assert layer is mock_security_layer
            mock_security_layer.self_check.assert_called_once()

    def test_returns_same_instance(self, mock_security_layer):
        with patch("dsm.core.security_listener.SecurityLayer", return_value=mock_security_layer):
            l1 = security_listener.get_security_layer()
            l2 = security_listener.get_security_layer()
            assert l1 is l2

    def test_logs_anomalies(self, mock_security_layer):
        mock_security_layer.self_check.return_value = {
            "security_status": "WARNING",
            "anomalies": ["file_changed"],
        }
        with patch("dsm.core.security_listener.SecurityLayer", return_value=mock_security_layer):
            layer = security_listener.get_security_layer()
            assert layer is mock_security_layer


class TestAuditFunctions:
    def test_audit_api_call(self, mock_security_layer):
        security_listener._security_layer = mock_security_layer
        security_listener.audit_api_call("get_price", {"symbol": "BTC"})
        mock_security_layer.audit_external_action.assert_called_once()
        call_args = mock_security_layer.audit_external_action.call_args
        assert call_args[0][0] == "api_request"
        assert "action" in call_args[0][1]

    def test_audit_file_operation(self, mock_security_layer):
        security_listener._security_layer = mock_security_layer
        security_listener.audit_file_operation("write", "/tmp/test.txt", {"size": 42})
        mock_security_layer.audit_external_action.assert_called_once()
        call_args = mock_security_layer.audit_external_action.call_args
        assert call_args[0][0] == "file_operation"

    def test_audit_file_operation_no_details(self, mock_security_layer):
        security_listener._security_layer = mock_security_layer
        security_listener.audit_file_operation("read", "/tmp/test.txt")
        mock_security_layer.audit_external_action.assert_called_once()


class TestPeriodicCheck:
    def test_run_periodic_no_anomalies(self, mock_security_layer):
        security_listener._security_layer = mock_security_layer
        report = security_listener.run_periodic_security_check()
        assert report["security_status"] == "OK"

    def test_run_periodic_with_anomalies(self, mock_security_layer):
        mock_security_layer.self_check.return_value = {
            "security_status": "WARNING",
            "anomalies": ["tampered_file"],
        }
        security_listener._security_layer = mock_security_layer
        report = security_listener.run_periodic_security_check()
        assert len(report["anomalies"]) > 0


class TestGenerateReport:
    def test_generate_report(self, mock_security_layer):
        security_listener._security_layer = mock_security_layer
        report = security_listener.generate_security_report()
        assert report == {"status": "OK"}


class TestUpdateBaseline:
    def test_update_baseline(self, mock_security_layer):
        security_listener._security_layer = mock_security_layer
        security_listener.update_security_baseline()
        mock_security_layer.update_baseline.assert_called_once()


class TestSecureApiCall:
    def test_successful_call(self, mock_security_layer):
        security_listener._security_layer = mock_security_layer
        func = MagicMock(return_value="result")
        func.__name__ = "test_func"
        result = security_listener.secure_api_call(func, "arg1", key="val")
        assert result == "result"
        func.assert_called_once_with("arg1", key="val")

    def test_rate_limit_reached(self, mock_security_layer):
        from dsm.core.security import MAX_API_REQUESTS_PER_CYCLE
        mock_security_layer.cycle_stats = {"api_requests": MAX_API_REQUESTS_PER_CYCLE}
        security_listener._security_layer = mock_security_layer
        func = MagicMock(return_value="result")
        func.__name__ = "test_func"
        result = security_listener.secure_api_call(func)
        assert result is None
        func.assert_not_called()

    def test_exception_handling(self, mock_security_layer):
        security_listener._security_layer = mock_security_layer
        func = MagicMock(side_effect=RuntimeError("boom"))
        func.__name__ = "failing_func"
        result = security_listener.secure_api_call(func)
        assert result is None
