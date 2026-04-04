"""
Tests for core/replay.py — targeting uncovered lines (62% → 80%+).

Covers:
  - parse_trace_line (valid, empty, invalid JSON, missing fields)
  - canonical_json / compute_step_hash
  - verify_record (strict + lenient, missing fields)
  - verify_chain (valid, broken, first record non-null prev)
  - replay_session (OK, CORRUPT, DIVERGENCE, limit, session filter, missing file)
  - print_report (normal, with errors, many errors)
  - save_json_report
"""

import json
import hashlib
from pathlib import Path

import pytest

from dsm.core.replay import (
    TraceRecord,
    ReplayReport,
    parse_trace_line,
    canonical_json,
    compute_step_hash,
    verify_record,
    verify_chain,
    replay_session,
    print_report,
    save_json_report,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_trace_data(trace_id="t1", session_id="sess1", action_type="action",
                     ok=True, prev_step_hash=None):
    """Build a trace dict and compute its step_hash."""
    data = {
        "trace_id": trace_id,
        "ts": "2026-01-01T00:00:00Z",
        "session_id": session_id,
        "action_type": action_type,
        "intent": "test",
        "ok": ok,
        "state_before": "s0",
        "state_after": "s1",
        "prev_step_hash": prev_step_hash,
    }
    step_hash = compute_step_hash(data)
    data["step_hash"] = step_hash
    return data


def _write_trace_file(tmp_path, lines):
    """Write JSONL trace file."""
    f = tmp_path / "trace.jsonl"
    f.write_text("\n".join(json.dumps(line) for line in lines) + "\n")
    return f


# ---------------------------------------------------------------------------
# parse_trace_line
# ---------------------------------------------------------------------------

class TestParseTraceLine:
    def test_valid_line(self):
        data = _make_trace_data()
        record = parse_trace_line(json.dumps(data), 1)
        assert record is not None
        assert record.trace_id == "t1"
        assert record.session_id == "sess1"

    def test_empty_line(self):
        assert parse_trace_line("", 1) is None
        assert parse_trace_line("   ", 1) is None

    def test_invalid_json(self):
        assert parse_trace_line("NOT_JSON{}", 1) is None

    def test_missing_required_field(self):
        data = {"trace_id": "t1", "ts": "t", "session_id": "s"}
        assert parse_trace_line(json.dumps(data), 1) is None

    def test_all_required_fields_present(self):
        data = {
            "trace_id": "t1", "ts": "t", "session_id": "s1",
            "action_type": "a", "ok": True, "step_hash": "h",
        }
        record = parse_trace_line(json.dumps(data), 1)
        assert record is not None

    def test_optional_fields_default(self):
        data = {
            "trace_id": "t1", "ts": "t", "session_id": "s1",
            "action_type": "a", "ok": True, "step_hash": "h",
        }
        record = parse_trace_line(json.dumps(data), 5)
        assert record.intent == ""
        assert record.error is None
        assert record.line_number == 5


# ---------------------------------------------------------------------------
# canonical_json / compute_step_hash
# ---------------------------------------------------------------------------

class TestCanonicalJson:
    def test_deterministic(self):
        a = canonical_json({"b": 2, "a": 1})
        b = canonical_json({"a": 1, "b": 2})
        assert a == b

    def test_compact(self):
        result = canonical_json({"key": "value"})
        assert " " not in result


class TestComputeStepHash:
    def test_returns_hex(self):
        h = compute_step_hash({"a": 1})
        assert len(h) == 64  # SHA256

    def test_deterministic(self):
        h1 = compute_step_hash({"a": 1, "b": 2})
        h2 = compute_step_hash({"b": 2, "a": 1})
        assert h1 == h2


# ---------------------------------------------------------------------------
# verify_record
# ---------------------------------------------------------------------------

class TestVerifyRecord:
    def test_valid_record_strict(self):
        data = _make_trace_data()
        record = parse_trace_line(json.dumps(data), 1)
        valid, err = verify_record(record, strict=True)
        assert valid is True
        assert err is None

    def test_valid_record_lenient(self):
        data = _make_trace_data()
        record = parse_trace_line(json.dumps(data), 1)
        valid, err = verify_record(record, strict=False)
        assert valid is True

    def test_tampered_hash_strict(self):
        data = _make_trace_data()
        data["step_hash"] = "tampered"
        record = parse_trace_line(json.dumps(data), 1)
        valid, err = verify_record(record, strict=True)
        assert valid is False
        assert "mismatch" in err

    def test_tampered_hash_lenient(self):
        data = _make_trace_data()
        data["step_hash"] = "tampered"
        record = parse_trace_line(json.dumps(data), 1)
        valid, err = verify_record(record, strict=False)
        # Lenient mode: still valid but with warning
        assert valid is True
        assert err is not None

    def test_empty_trace_id(self):
        data = _make_trace_data()
        data["trace_id"] = ""
        data["step_hash"] = compute_step_hash({k: v for k, v in data.items() if k != "step_hash"})
        record = parse_trace_line(json.dumps(data), 1)
        valid, err = verify_record(record, strict=True)
        assert valid is False
        assert "trace_id" in err

    def test_empty_session_id(self):
        data = _make_trace_data()
        data["session_id"] = ""
        data["step_hash"] = compute_step_hash({k: v for k, v in data.items() if k != "step_hash"})
        record = parse_trace_line(json.dumps(data), 1)
        valid, err = verify_record(record, strict=True)
        assert valid is False
        assert "session_id" in err


# ---------------------------------------------------------------------------
# verify_chain
# ---------------------------------------------------------------------------

class TestVerifyChain:
    def test_valid_chain(self):
        d1 = _make_trace_data(trace_id="t1", prev_step_hash=None)
        d2 = _make_trace_data(trace_id="t2", prev_step_hash=d1["step_hash"])
        r1 = parse_trace_line(json.dumps(d1), 1)
        r2 = parse_trace_line(json.dumps(d2), 2)
        errors = verify_chain([r1, r2])
        assert errors == []

    def test_broken_chain(self):
        d1 = _make_trace_data(trace_id="t1", prev_step_hash=None)
        d2 = _make_trace_data(trace_id="t2", prev_step_hash="WRONG_HASH")
        r1 = parse_trace_line(json.dumps(d1), 1)
        r2 = parse_trace_line(json.dumps(d2), 2)
        errors = verify_chain([r1, r2])
        assert len(errors) == 1
        assert "broken chain" in errors[0]

    def test_first_record_non_null_prev(self):
        d1 = _make_trace_data(trace_id="t1", prev_step_hash="some_hash")
        r1 = parse_trace_line(json.dumps(d1), 1)
        errors = verify_chain([r1])
        assert len(errors) == 1
        assert "first record" in errors[0]

    def test_empty_chain(self):
        assert verify_chain([]) == []

    def test_single_valid_record(self):
        d1 = _make_trace_data(trace_id="t1", prev_step_hash=None)
        r1 = parse_trace_line(json.dumps(d1), 1)
        assert verify_chain([r1]) == []


# ---------------------------------------------------------------------------
# replay_session
# ---------------------------------------------------------------------------

class TestReplaySession:
    def test_ok_session(self, tmp_path):
        d1 = _make_trace_data(trace_id="t1", session_id="s1", prev_step_hash=None)
        d2 = _make_trace_data(trace_id="t2", session_id="s1", prev_step_hash=d1["step_hash"])
        f = _write_trace_file(tmp_path, [d1, d2])
        report = replay_session(f, "s1")
        assert report.status == "OK"
        assert report.total_records == 2

    def test_corrupt_session_strict(self, tmp_path):
        f = tmp_path / "trace.jsonl"
        f.write_text("NOT_VALID_JSON\n")
        report = replay_session(f, "s1", strict=True)
        assert report.status == "CORRUPT"
        assert report.corrupt_records >= 1

    def test_divergence_broken_chain(self, tmp_path):
        d1 = _make_trace_data(trace_id="t1", session_id="s1", prev_step_hash=None)
        d2 = _make_trace_data(trace_id="t2", session_id="s1", prev_step_hash="WRONG")
        f = _write_trace_file(tmp_path, [d1, d2])
        report = replay_session(f, "s1")
        assert report.status == "DIVERGENCE"

    def test_session_filter(self, tmp_path):
        d1 = _make_trace_data(trace_id="t1", session_id="s1")
        d2 = _make_trace_data(trace_id="t2", session_id="OTHER")
        f = _write_trace_file(tmp_path, [d1, d2])
        report = replay_session(f, "s1")
        assert report.total_records == 1

    def test_limit(self, tmp_path):
        d1 = _make_trace_data(trace_id="t1", session_id="s1", prev_step_hash=None)
        d2 = _make_trace_data(trace_id="t2", session_id="s1", prev_step_hash=d1["step_hash"])
        d3 = _make_trace_data(trace_id="t3", session_id="s1", prev_step_hash=d2["step_hash"])
        f = _write_trace_file(tmp_path, [d1, d2, d3])
        report = replay_session(f, "s1", limit=2)
        assert report.total_records == 2

    def test_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            replay_session(tmp_path / "nonexistent.jsonl", "s1")

    def test_empty_file(self, tmp_path):
        f = tmp_path / "trace.jsonl"
        f.write_text("")
        report = replay_session(f, "s1")
        assert report.status == "OK"
        assert report.total_records == 0


# ---------------------------------------------------------------------------
# print_report
# ---------------------------------------------------------------------------

class TestPrintReport:
    def test_ok_report(self, capsys):
        report = ReplayReport(
            session_id="s1", total_records=5, verified_records=5,
            corrupt_records=0, missing_hash_records=0, broken_chain_records=0,
            first_timestamp="t1", last_timestamp="t5", status="OK", errors=[],
        )
        print_report(report)
        out = capsys.readouterr().out
        assert "Session ID: s1" in out
        assert "OK" in out
        assert "No errors" in out

    def test_error_report(self, capsys):
        report = ReplayReport(
            session_id="s1", total_records=5, verified_records=3,
            corrupt_records=2, missing_hash_records=0, broken_chain_records=0,
            first_timestamp="t1", last_timestamp="t5", status="CORRUPT",
            errors=["line 1: bad", "line 3: bad"],
        )
        print_report(report)
        out = capsys.readouterr().out
        assert "CORRUPT" in out
        assert "Errors" in out

    def test_many_errors_truncated(self, capsys):
        errors = [f"line {i}: error" for i in range(30)]
        report = ReplayReport(
            session_id="s1", total_records=30, verified_records=0,
            corrupt_records=30, missing_hash_records=0, broken_chain_records=0,
            first_timestamp=None, last_timestamp=None, status="CORRUPT",
            errors=errors,
        )
        print_report(report)
        out = capsys.readouterr().out
        assert "more errors" in out


# ---------------------------------------------------------------------------
# save_json_report
# ---------------------------------------------------------------------------

class TestSaveJsonReport:
    def test_saves_file(self, tmp_path, capsys):
        report = ReplayReport(
            session_id="s1", total_records=2, verified_records=2,
            corrupt_records=0, missing_hash_records=0, broken_chain_records=0,
            first_timestamp="t1", last_timestamp="t2", status="OK", errors=[],
        )
        save_json_report(report, tmp_path / "output")
        output_file = tmp_path / "output" / "replay_s1.json"
        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert data["session_id"] == "s1"
        assert data["status"] == "OK"
