"""
DSM LLM Summarizer — Pluggable interface for LLM-powered distillation.

Provides an abstract SummarizerBackend that can be implemented with any
LLM provider (Anthropic, OpenAI, local models). The Summarizer class
uses the backend to produce:

1. Smart summaries: Tier 1 projections from raw entries
2. Smart details: Tier 2 projections (detail + key_findings)
3. Digest narratives: Human-readable digest from DigestEntry

Default backend: StructuralSummarizer (no LLM, deterministic extraction).
LLM backends are optional — the system works fully without them.

Usage:
    # Without LLM (default — fully deterministic)
    summarizer = Summarizer()
    summary = summarizer.summarize(entry)        # Tier 1
    detail = summarizer.detail(entry)             # Tier 2

    # With LLM backend (optional)
    summarizer = Summarizer(backend=AnthropicBackend(api_key="..."))
    summary = summarizer.summarize(entry)         # LLM-powered
"""

import hashlib
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .core.models import Entry

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Result types
# ------------------------------------------------------------------


@dataclass(frozen=True)
class SummaryResult:
    """Result of summarization."""
    summary: str               # Tier 1 text (~100 chars)
    detail: str                # Tier 2 text (~1000 chars)
    key_findings: tuple        # structured findings
    confidence: float          # 0.0 (structural) to 1.0 (LLM-verified)
    backend_name: str          # which backend produced this


# ------------------------------------------------------------------
# Backend interface
# ------------------------------------------------------------------


class SummarizerBackend(ABC):
    """Abstract backend for summarization."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend identifier."""
        ...

    @abstractmethod
    def summarize_entry(self, entry: Entry) -> SummaryResult:
        """Produce summary + detail for a single entry."""
        ...

    @abstractmethod
    def summarize_batch(self, entries: List[Entry]) -> SummaryResult:
        """Produce aggregate summary for multiple entries."""
        ...


# ------------------------------------------------------------------
# Default: Structural Summarizer (no LLM)
# ------------------------------------------------------------------


class StructuralSummarizer(SummarizerBackend):
    """Deterministic summarizer — extracts structure from content.

    No LLM calls, no external deps. Produces reasonable summaries
    by parsing JSON content and extracting key fields.
    """

    @property
    def name(self) -> str:
        return "structural"

    def summarize_entry(self, entry: Entry) -> SummaryResult:
        """Extract summary from entry content."""
        try:
            data = json.loads(entry.content)
        except (json.JSONDecodeError, TypeError):
            data = {"raw": str(entry.content)[:200]}

        # Extract action/event type
        action = (entry.metadata or {}).get("action_name", "")
        event_type = (entry.metadata or {}).get("event_type", "")
        source = entry.source or ""

        # Build Tier 1 summary
        if action:
            summary = f"{source}: {action}"
        elif event_type:
            summary = f"{source}: {event_type}"
        else:
            summary = f"{source}: entry"

        # Add key data to summary
        if isinstance(data, dict):
            # Take first 2-3 meaningful keys
            skip_keys = {"type", "event_type", "action_name", "timestamp"}
            meaningful = {k: v for k, v in data.items()
                         if k not in skip_keys and v is not None}
            if meaningful:
                preview = ", ".join(
                    f"{k}={_truncate(str(v), 30)}"
                    for k, v in list(meaningful.items())[:3]
                )
                summary = f"{summary} ({preview})"

        summary = _truncate(summary, 120)

        # Build Tier 2 detail
        if isinstance(data, dict):
            detail = json.dumps(data, ensure_ascii=False, indent=None)[:1000]
        else:
            detail = str(data)[:1000]

        # Extract key findings
        findings = []
        if isinstance(data, dict):
            if "result" in data:
                findings.append(f"result: {_truncate(str(data['result']), 50)}")
            if "status" in data:
                findings.append(f"status: {data['status']}")
            if "error" in data:
                findings.append(f"error: {_truncate(str(data['error']), 50)}")
            if "value" in data:
                findings.append(f"value: {_truncate(str(data['value']), 50)}")

        return SummaryResult(
            summary=summary,
            detail=detail,
            key_findings=tuple(findings),
            confidence=0.3,  # structural = low confidence
            backend_name=self.name,
        )

    def summarize_batch(self, entries: List[Entry]) -> SummaryResult:
        """Aggregate summary from multiple entries."""
        if not entries:
            return SummaryResult(
                summary="empty batch",
                detail="",
                key_findings=(),
                confidence=0.0,
                backend_name=self.name,
            )

        sources = set()
        actions = set()
        all_findings = []

        for e in entries:
            result = self.summarize_entry(e)
            sources.add(e.source or "unknown")
            action = (e.metadata or {}).get("action_name", "")
            if action:
                actions.add(action)
            all_findings.extend(result.key_findings)

        summary = f"{len(entries)} entries from {', '.join(sorted(sources))}"
        if actions:
            summary += f" [{', '.join(sorted(actions)[:5])}]"
        summary = _truncate(summary, 120)

        detail = f"Batch of {len(entries)} entries. "
        detail += f"Sources: {', '.join(sorted(sources))}. "
        detail += f"Actions: {', '.join(sorted(actions)[:10])}. "
        detail += f"Findings: {len(all_findings)} total."

        return SummaryResult(
            summary=summary,
            detail=detail,
            key_findings=tuple(all_findings[:30]),
            confidence=0.2,
            backend_name=self.name,
        )


# ------------------------------------------------------------------
# Main Summarizer class
# ------------------------------------------------------------------


class Summarizer:
    """Pluggable summarizer with fallback to structural extraction.

    Usage:
        s = Summarizer()                           # structural only
        s = Summarizer(backend=MyLLMBackend())      # LLM-powered
    """

    def __init__(self, backend: Optional[SummarizerBackend] = None):
        self._backend = backend or StructuralSummarizer()

    @property
    def backend_name(self) -> str:
        return self._backend.name

    def summarize(self, entry: Entry) -> SummaryResult:
        """Produce summary for a single entry."""
        try:
            return self._backend.summarize_entry(entry)
        except Exception as e:
            logger.warning("Summarizer backend failed, falling back: %s", e)
            return StructuralSummarizer().summarize_entry(entry)

    def summarize_batch(self, entries: List[Entry]) -> SummaryResult:
        """Produce aggregate summary for a batch of entries."""
        try:
            return self._backend.summarize_batch(entries)
        except Exception as e:
            logger.warning("Summarizer batch failed, falling back: %s", e)
            return StructuralSummarizer().summarize_batch(entries)

    def summary_fn(self, entry: Entry) -> str:
        """Convenience: returns just the summary string.

        Compatible with push_to_collective(summary_fn=...) signature.
        """
        return self.summarize(entry).summary

    def detail_fn(self, entry: Entry) -> Tuple[str, List[str]]:
        """Convenience: returns (detail, key_findings).

        Compatible with push_to_collective(detail_fn=...) signature.
        """
        result = self.summarize(entry)
        return result.detail, list(result.key_findings)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _truncate(s: str, max_len: int) -> str:
    """Truncate string with ellipsis."""
    if len(s) <= max_len:
        return s
    return s[:max_len - 3] + "..."
