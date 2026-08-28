"""Structural live smoke. Not a quality benchmark."""

from __future__ import annotations

import json
from pathlib import Path

from hexashard import RetrievalFilters, SourceStatus
from hexashard_adapter import AdapterConfig, HexaShardAdapter, MockChatProvider
from hexashard_adapter.context import NO_SOURCE_SENTENCE

from smoke import build_smoke_project, store_tokens


def test_smoke_store_session_reset_and_facts(tmp_path):
    ad = build_smoke_project(tmp_path / "smoke", min_store=100_000)
    store = store_tokens(ad.project)
    assert store >= 100_000

    mock = MockChatProvider()
    ad.provider = mock
    rows = []

    def ask(q, **kw):
        r = ad.chat(q, **kw)
        blob = mock.calls[-1]["context"]
        rows.append({
            "q": q, "ids": r.retrieved_source_ids, "trunc": r.truncated,
            "visible": r.total_context_tokens, "active": r.active_state_tokens,
            "retrieved": r.retrieved_context_tokens, "store": r.project_store_tokens,
            "retr_ms": r.retrieval_latency_ms, "overhead_ms": r.adapter_overhead_ms,
            "model_ms": r.latency_ms - r.retrieval_latency_ms - r.adapter_overhead_ms,
            "epoch": r.epoch, "blob_head": blob[:240],
        })
        return r, blob

    r1, b1 = ask("What is the BEACONEL elevation?")
    assert "41.2" in b1
    r2, b2 = ask("What is the current GATEBUDGET daily cap?")
    assert "6.1TB" in b2
    r3, b3 = ask(
        "What was the previous GATEBUDGET daily cap before rev 2?",
        filters=RetrievalFilters(statuses=(SourceStatus.SUPERSEDED,)),
    )
    assert "4.0TB" in b3
    r4, b4 = ask("What is the current ADR-OG-01 ingest path?")
    assert "CREDITBP" in b4
    r5, b5 = ask("What HEAPSTARVE failure is recorded for BUG-4412?")
    assert "HEAPSTARVE" in b5
    r6, b6 = ask("What is the ZEPHYRX mass in kilograms?")
    assert NO_SOURCE_SENTENCE in b6

    status = ad.project_status()
    path = ad.project.root
    ad.close()

    mock_b = MockChatProvider()
    b = HexaShardAdapter.open(path, config=AdapterConfig(provider="mock"), provider=mock_b)
    r7, b7 = (None, None)
    r7 = b.chat("What is the current objective?")
    b7 = mock_b.calls[-1]["context"]
    assert "CREDITBP" in b7 or "HEXMESH" in b7
    r8 = b.chat("What is BEACONEL?")
    assert "41.2" in mock_b.calls[-1]["context"]
    r9 = b.chat("What is current GATEBUDGET?")
    assert "6.1TB" in mock_b.calls[-1]["context"]
    session_reset_ok = True
    visibles = [x["visible"] for x in rows] + [
        r7.total_context_tokens, r8.total_context_tokens, r9.total_context_tokens,
    ]
    actives = [x["active"] for x in rows] + [
        r7.active_state_tokens, r8.active_state_tokens, r9.active_state_tokens,
    ]
    retrs = [x["retrieved"] for x in rows]
    summary = {
        "project_store_tokens": store,
        "source_count": status["source_count"],
        "mean_active_state": round(sum(actives) / len(actives), 1),
        "peak_active_state": max(actives),
        "mean_retrieved": round(sum(retrs) / len(retrs), 1),
        "peak_model_visible": max(visibles),
        "mean_model_visible": round(sum(visibles) / len(visibles), 1),
        "store_visible_ratio": round(store / max(visibles), 2),
        "mean_retrieval_ms": round(sum(x["retr_ms"] for x in rows) / len(rows), 2),
        "mean_adapter_overhead_ms": round(sum(x["overhead_ms"] for x in rows) / len(rows), 2),
        "mean_model_ms": round(sum(x["model_ms"] for x in rows) / len(rows), 2),
        "session_reset_ok": session_reset_ok,
        "queries": rows,
    }
    # Scratch, never the source tree. The recorded v0.1 run is frozen in
    # docs/hexashard/evidence/adapter_smoke.json.
    import os
    import tempfile

    out = Path(
        os.environ.get("HEXASHARD_ARTIFACTS_DIR")
        or Path(tempfile.gettempdir()) / "hexashard-artifacts"
    )
    out.mkdir(parents=True, exist_ok=True)
    (out / "smoke.json").write_text(json.dumps(summary, indent=2) + "\n")
    assert session_reset_ok
    assert summary["peak_model_visible"] < store
    assert summary["peak_active_state"] <= 6000
