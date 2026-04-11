"""Phase 4.3 tests for ``dsm.context`` (daryl port).

Mirrors the 9 priority contracts from ``dsm_v0/test_context.py``,
using daryl's native Storage + Entry primitives.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dsm.context import (
    DEFAULT_MAX_TOKENS,
    SECTION_ORDER,
    build_context,
    build_prompt_context,
)
from dsm.core.models import Entry
from dsm.core.storage import Storage


@pytest.fixture
def tmp_storage(tmp_path):
    return Storage(data_dir=str(tmp_path / "data"))


def _append(
    storage: Storage,
    shard: str,
    session_id: str,
    text: str,
    event_type: str = "user_prompt",
    ts: datetime | None = None,
) -> Entry:
    entry = Entry(
        id=str(uuid.uuid4()),
        timestamp=ts or datetime.now(timezone.utc),
        session_id=session_id,
        source="claude",
        content=text,
        shard=shard,
        hash="",
        prev_hash=None,
        metadata={"event_type": event_type},
        version="v2.0",
    )
    return storage.append(entry)


# ---------------------------------------------------------------------------
# Test 1 — section order stable on empty corpus
# ---------------------------------------------------------------------------


def test_section_order_stable_empty(tmp_storage):
    ctx = build_context("anything", storage=tmp_storage)
    expected = [s for s in SECTION_ORDER if s != "provenance"]
    assert list(ctx["sections"].keys()) == expected
    for items in ctx["sections"].values():
        assert items == []
    assert ctx["provenance"] is not None
    assert ctx["trimmed"] is False
    assert "digest" in ctx


# ---------------------------------------------------------------------------
# Test 2 — routing: recent vs past vs superseded
# ---------------------------------------------------------------------------


def test_routing_recent_vs_past_vs_superseded(tmp_storage):
    _append(
        tmp_storage, "sessions", "sess-a",
        "alpha beta gamma delta old decision",
    )
    _append(
        tmp_storage, "sessions", "sess-b",
        "alpha beta gamma delta new decision stronger",
    )
    real_now = time.time()

    ctx_now = build_context(
        "alpha beta gamma delta", storage=tmp_storage, now=real_now,
    )
    sections_now = ctx_now["sections"]
    recent_sids = {m["session_id"] for m in sections_now["recent_relevant_events"]}
    unc_sids = {m["session_id"] for m in sections_now["uncertain_or_superseded"]}
    assert "sess-b" in recent_sids
    assert "sess-a" in unc_sids
    assert "sess-a" not in recent_sids

    ctx_later = build_context(
        "alpha beta gamma delta", storage=tmp_storage,
        now=real_now + 26 * 3600,
    )
    recent_later = {m["session_id"] for m in ctx_later["sections"]["recent_relevant_events"]}
    past_later = {m["session_id"] for m in ctx_later["sections"]["past_session_recall"]}
    unc_later = {m["session_id"] for m in ctx_later["sections"]["uncertain_or_superseded"]}
    assert recent_later == set()
    assert "sess-b" in past_later
    assert "sess-a" in unc_later


# ---------------------------------------------------------------------------
# Test 3 — token budget respected
# ---------------------------------------------------------------------------


def test_token_budget_respected_on_large_corpus(tmp_storage):
    big = "consumption layer " + ("filler token " * 200)
    for _ in range(20):
        _append(tmp_storage, "sessions", "sess-big", big)

    small_budget = 300
    ctx = build_context(
        "consumption layer",
        storage=tmp_storage,
        max_tokens=small_budget,
        max_results=50,
    )
    assert ctx["trimmed"] is True
    assert ctx["token_estimate"] <= small_budget * 1.05
    assert ctx["provenance"] is not None
    assert list(ctx["sections"].keys()) == [
        s for s in SECTION_ORDER if s != "provenance"
    ]


# ---------------------------------------------------------------------------
# Test 4 — reverse-priority trim invariant
# ---------------------------------------------------------------------------


def test_trim_order_drops_lowest_priority_first(tmp_storage):
    _append(
        tmp_storage, "sessions", "sess-n",
        "omega theta sigma pivotal decision early",
    )
    _append(
        tmp_storage, "sessions", "sess-m",
        "omega theta sigma pivotal decision updated stronger",
    )
    for i in range(5):
        _append(
            tmp_storage, "sessions", f"sess-filler-{i}",
            f"omega theta sigma filler {i} early form",
        )

    from dsm.context.builder import _bucket_matches
    from dsm.recall import search_memory

    raw = search_memory(
        "omega theta sigma", storage=tmp_storage, max_results=50,
    )
    pre_buckets = _bucket_matches(raw, now_seconds=time.time())
    pre_counts = {k: len(v) for k, v in pre_buckets.items()}

    ctx = build_context(
        "omega theta sigma",
        storage=tmp_storage,
        max_tokens=250,
        max_results=50,
    )
    post_counts = {k: len(v) for k, v in ctx["sections"].items()}
    dropped = {
        k: pre_counts.get(k, 0) - post_counts.get(k, 0) for k in pre_counts
    }

    assert ctx["trimmed"] is True
    low = dropped["uncertain_or_superseded"]
    for higher in (
        "past_session_recall",
        "recent_relevant_events",
        "working_state",
        "verified_facts",
    ):
        assert low >= dropped[higher], (
            f"priority violated: dropped(uncertain)={low} "
            f"< dropped({higher})={dropped[higher]}"
        )
    assert low > 0


# ---------------------------------------------------------------------------
# Test 5 — provenance never dropped
# ---------------------------------------------------------------------------


def test_provenance_never_dropped_even_at_tiny_budget(tmp_storage):
    _append(tmp_storage, "sessions", "sess-x",
            "provenance must survive the budget")
    _append(tmp_storage, "sessions", "sess-x",
            "provenance must survive the budget twice")
    ctx = build_context(
        "provenance survive budget",
        storage=tmp_storage,
        max_tokens=50,
    )
    assert ctx["provenance"] is not None
    prov = ctx["provenance"]
    assert "entry_hashes" in prov
    assert "trust_level" in prov


# ---------------------------------------------------------------------------
# Test 6 — prompt rendering
# ---------------------------------------------------------------------------


def test_prompt_context_renders_and_respects_budget(tmp_storage):
    _append(tmp_storage, "sessions", "sess-p",
            "prompt rendering alpha beta gamma")
    _append(tmp_storage, "sessions", "sess-p",
            "prompt rendering alpha beta gamma tool",
            event_type="tool_exec:call")
    rendered = build_prompt_context(
        "prompt rendering alpha beta gamma",
        storage=tmp_storage,
        max_tokens=500,
    )
    assert isinstance(rendered, str)
    assert "DSM context for query" in rendered
    assert "## Provenance" in rendered
    assert "- [sess-p]" in rendered
    assert "_[truncated]_" not in rendered
    assert len(rendered) // 4 <= 500 * 1.1


def test_prompt_context_hard_truncates_oversized(tmp_storage):
    huge = "prompt overflow " + ("word " * 500)
    for _ in range(10):
        _append(tmp_storage, "sessions", "sess-huge", huge)
    rendered = build_prompt_context(
        "prompt overflow",
        storage=tmp_storage,
        max_tokens=150,
    )
    assert isinstance(rendered, str)
    assert ("_[context trimmed" in rendered) or ("_[truncated]_" in rendered)
    assert len(rendered) <= 150 * 4 + 40


# ---------------------------------------------------------------------------
# Test 7 — no-write guarantee
# ---------------------------------------------------------------------------


def test_context_never_writes(tmp_storage):
    _append(tmp_storage, "sessions", "sess-ro", "context readonly guarantee")
    data_dir = Path(tmp_storage.data_dir)

    before_files = sorted(p.relative_to(data_dir) for p in data_dir.rglob("*") if p.is_file())
    before_bytes = {str(p): (data_dir / p).read_bytes() for p in before_files}
    before_mtimes = {str(p): (data_dir / p).stat().st_mtime_ns for p in before_files}

    for _ in range(3):
        build_context("context readonly", storage=tmp_storage)
        build_prompt_context("context readonly", storage=tmp_storage)

    after_files = sorted(p.relative_to(data_dir) for p in data_dir.rglob("*") if p.is_file())
    assert after_files == before_files
    for p in after_files:
        assert (data_dir / p).read_bytes() == before_bytes[str(p)]
        assert (data_dir / p).stat().st_mtime_ns == before_mtimes[str(p)]
