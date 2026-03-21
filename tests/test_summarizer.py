"""Tests for DSM LLM Summarizer — structural backend and pluggable interface."""

import json
from datetime import datetime, timezone

import pytest

from dsm.core.models import Entry
from dsm.summarizer import (
    Summarizer, StructuralSummarizer, SummarizerBackend,
    SummaryResult, _truncate,
)


def _make_entry(content=None, action_name=None, event_type="tool_call",
                source="agent1"):
    if content is None:
        content = json.dumps({"value": 42, "status": "ok"})
    return Entry(
        id="e1",
        timestamp=datetime.now(timezone.utc),
        session_id="s1",
        source=source,
        content=content,
        shard="test_shard",
        hash="abc123",
        prev_hash=None,
        metadata={
            "event_type": event_type,
            **({"action_name": action_name} if action_name else {}),
        },
        version="v2.0",
    )


class TestTruncate:
    def test_short_string(self):
        assert _truncate("hello", 10) == "hello"

    def test_exact_length(self):
        assert _truncate("hello", 5) == "hello"

    def test_long_string(self):
        result = _truncate("hello world", 8)
        assert result == "hello..."
        assert len(result) == 8


class TestStructuralSummarizer:
    def test_name(self):
        s = StructuralSummarizer()
        assert s.name == "structural"

    def test_summarize_json_entry(self):
        entry = _make_entry(action_name="analyze")
        s = StructuralSummarizer()
        result = s.summarize_entry(entry)
        assert isinstance(result, SummaryResult)
        assert "analyze" in result.summary
        assert result.confidence == 0.3
        assert result.backend_name == "structural"

    def test_summarize_with_event_type(self):
        entry = _make_entry(event_type="session_start")
        s = StructuralSummarizer()
        result = s.summarize_entry(entry)
        assert "session_start" in result.summary

    def test_summarize_non_json_content(self):
        entry = _make_entry(content="plain text content here")
        s = StructuralSummarizer()
        result = s.summarize_entry(entry)
        assert result.summary != ""
        assert result.detail != ""

    def test_key_findings_extracted(self):
        content = json.dumps({"status": "success", "value": 42, "error": None})
        entry = _make_entry(content=content)
        s = StructuralSummarizer()
        result = s.summarize_entry(entry)
        findings = list(result.key_findings)
        assert any("status" in f for f in findings)

    def test_detail_is_string(self):
        entry = _make_entry()
        s = StructuralSummarizer()
        result = s.summarize_entry(entry)
        assert isinstance(result.detail, str)
        assert len(result.detail) > 0

    def test_summary_max_length(self):
        """Summary should be capped at 120 chars."""
        content = json.dumps({f"key_{i}": f"value_{i}" * 10 for i in range(20)})
        entry = _make_entry(content=content, action_name="very_long_action")
        s = StructuralSummarizer()
        result = s.summarize_entry(entry)
        assert len(result.summary) <= 120

    def test_batch_summarize(self):
        entries = [
            _make_entry(action_name="a1", source="alice"),
            _make_entry(action_name="a2", source="bob"),
            _make_entry(action_name="a1", source="alice"),
        ]
        s = StructuralSummarizer()
        result = s.summarize_batch(entries)
        assert "3 entries" in result.summary
        assert result.confidence == 0.2

    def test_batch_empty(self):
        s = StructuralSummarizer()
        result = s.summarize_batch([])
        assert result.summary == "empty batch"
        assert result.confidence == 0.0


class TestSummarizer:
    def test_default_backend(self):
        s = Summarizer()
        assert s.backend_name == "structural"

    def test_summarize(self):
        s = Summarizer()
        entry = _make_entry(action_name="test")
        result = s.summarize(entry)
        assert isinstance(result, SummaryResult)

    def test_summarize_batch(self):
        s = Summarizer()
        entries = [_make_entry(), _make_entry()]
        result = s.summarize_batch(entries)
        assert "2 entries" in result.summary

    def test_summary_fn(self):
        """summary_fn returns just the string — for push_to_collective."""
        s = Summarizer()
        entry = _make_entry(action_name="test_action")
        text = s.summary_fn(entry)
        assert isinstance(text, str)
        assert len(text) > 0

    def test_detail_fn(self):
        """detail_fn returns (detail, findings) tuple."""
        s = Summarizer()
        entry = _make_entry()
        detail, findings = s.detail_fn(entry)
        assert isinstance(detail, str)
        assert isinstance(findings, list)

    def test_custom_backend(self):
        """Pluggable backend works."""
        class MockBackend(SummarizerBackend):
            @property
            def name(self):
                return "mock_llm"

            def summarize_entry(self, entry):
                return SummaryResult(
                    summary="LLM summary",
                    detail="LLM detail",
                    key_findings=("llm_finding",),
                    confidence=0.9,
                    backend_name=self.name,
                )

            def summarize_batch(self, entries):
                return SummaryResult(
                    summary=f"LLM batch of {len(entries)}",
                    detail="",
                    key_findings=(),
                    confidence=0.9,
                    backend_name=self.name,
                )

        s = Summarizer(backend=MockBackend())
        assert s.backend_name == "mock_llm"
        result = s.summarize(_make_entry())
        assert result.summary == "LLM summary"
        assert result.confidence == 0.9

    def test_fallback_on_backend_error(self):
        """If backend raises, falls back to structural."""
        class FailingBackend(SummarizerBackend):
            @property
            def name(self):
                return "failing"

            def summarize_entry(self, entry):
                raise RuntimeError("LLM unavailable")

            def summarize_batch(self, entries):
                raise RuntimeError("LLM unavailable")

        s = Summarizer(backend=FailingBackend())
        result = s.summarize(_make_entry(action_name="test"))
        assert result.backend_name == "structural"  # fell back
        assert result.summary != ""

    def test_batch_fallback_on_error(self):
        class FailingBackend(SummarizerBackend):
            @property
            def name(self):
                return "failing"

            def summarize_entry(self, entry):
                raise RuntimeError()

            def summarize_batch(self, entries):
                raise RuntimeError()

        s = Summarizer(backend=FailingBackend())
        result = s.summarize_batch([_make_entry()])
        assert result.backend_name == "structural"
