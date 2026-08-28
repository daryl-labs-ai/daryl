from __future__ import annotations

from pathlib import Path

import pytest

from hexashard import HexType, RetrievalFilters, SourceStatus
from hexashard_adapter import (
    AdapterConfig,
    HexaShardAdapter,
    InvalidProviderConfiguration,
    MockChatProvider,
    FROZEN_CORE_MODULES,
    core_module_digests,
)
from hexashard_adapter.context import NO_SOURCE_SENTENCE, assemble
from hexashard_adapter.provider import ollama_available


def _tiny(tmp_path: Path, **cfg_kw) -> HexaShardAdapter:
    cfg = AdapterConfig(provider="mock", **cfg_kw)
    mock = MockChatProvider()
    ad = HexaShardAdapter.create(
        tmp_path / "proj",
        name="tiny",
        mission="Keep ORION-GATE on CREDITBP.",
        config=cfg,
        provider=mock,
    )
    hx = ad.add_hex("architecture", HexType.SOURCE, tags=["architecture"])
    src = ad.add_source(
        "spec", "SG-01",
        "The primary dish has a BEACONEL elevation of 41.2 degrees.",
        hex_id=hx.hex_id, claim_key="beacon_elevation", claim_value="41.2",
        tags=["architecture"],
    )
    ad.pin("BEACONEL", "41.2", src.source_id, critical=True, hex_id=hx.hex_id)
    ad.project.state.current_objective = "Hold 41.2 BEACONEL."
    ad.project.save()
    return ad


def test_t1_opens_existing_project(tmp_path):
    ad = _tiny(tmp_path)
    path = ad.project.root
    ad.close()
    reopened = HexaShardAdapter.open(path, provider=MockChatProvider())
    assert reopened.project.config.name == "tiny"
    assert reopened.project_status()["source_count"] >= 1


def test_t2_mock_receives_bounded_context(tmp_path):
    mock = MockChatProvider()
    ad = _tiny(tmp_path)
    ad.provider = mock
    result = ad.chat("What is BEACONEL?")
    assert result.total_context_tokens <= ad.config.model_context_budget
    assert mock.calls
    ctx = mock.calls[-1]["context"]
    assert "BEACONEL" in ctx or "41.2" in mock.calls[-1]["system"] + ctx


def test_t3_source_ids_preserved(tmp_path):
    ad = _tiny(tmp_path)
    mock = MockChatProvider()
    ad.provider = mock
    result = ad.chat("What is the BEACONEL elevation?")
    assert result.retrieved_source_ids
    blob = mock.calls[-1]["context"]
    for sid in result.retrieved_source_ids:
        assert f"[SOURCE {sid} |" in blob


def test_t4_critical_pins_survive_small_budget(tmp_path):
    ad = _tiny(tmp_path, model_context_budget=900)
    ad.add_source(
        "minutes", "noise",
        "padding " * 400 + " unrelated cafeteria kettle badge text",
    )
    mock = MockChatProvider()
    ad.provider = mock
    result = ad.chat("cafeteria kettle badge minutes padding")
    blob = mock.calls[-1]["system"] + mock.calls[-1]["context"]
    assert "BEACONEL" in blob
    assert "41.2" in blob
    assert result.total_context_tokens <= 900


def test_t5_authority_warnings_reach_provider(tmp_path):
    ad = _tiny(tmp_path)
    hx = next(h for h in ad.project.hexmap.all())
    v1 = next(s for s in ad.project.sources.all() if "BEACONEL" in s.content)
    v2 = ad.add_source(
        "spec", "SG-01 rev2", "BEACONEL is 41.2 still.",
        hex_id=hx.hex_id, claim_key="beacon_elevation", claim_value="41.2",
    )
    ad.supersede(v1.source_id, v2.source_id, reconcile_pins=False)
    mock = MockChatProvider()
    ad.provider = mock
    result = ad.chat("What is BEACONEL?")
    blob = mock.calls[-1]["context"]
    assert "PROJECT WARNING" in blob
    assert result.authority_warnings
    assert any("STALE" in w or "SUPERSEDED" in w for w in result.authority_warnings)


def test_t6_unknown_source_signaled(tmp_path):
    ad = _tiny(tmp_path)
    mock = MockChatProvider()
    ad.provider = mock
    result = ad.chat("What is the ZEPHYRX mass in kilograms?")
    blob = mock.calls[-1]["context"]
    assert NO_SOURCE_SENTENCE in blob
    assert result.no_source_retrieved


def test_t7_model_context_budget_enforced(tmp_path):
    ctx = {
        "mission": "m",
        "current_objective": "o",
        "active_pins": [
            {"key": "BEACONEL", "value": "41.2", "source_ref": "P1.S0001",
             "critical": True, "status": "ACTIVE"},
        ],
        "retrieved": [
            {"source_id": f"P1.S{i:04d}", "source_status": "CURRENT",
             "source_title": "n", "text": "word " * 80}
            for i in range(8)
        ],
        "pin_warnings": [],
        "ambiguities": [],
        "current_summary": "summary " * 40,
        "recent_decisions": [],
        "open_questions": [],
    }
    assembled = assemble(user_message="q", response_context=ctx, budget=700)
    assert assembled.tokens <= 700
    assert assembled.truncated
    assert assembled.dropped_sections


def test_t8_provider_limit_on_config():
    with pytest.raises(InvalidProviderConfiguration):
        AdapterConfig(model_context_budget=20_000, provider_context_limit=1000).validate()


def test_t9_visible_session_reset(tmp_path):
    ad = _tiny(tmp_path)
    ad.chat("Remember nothing from this transcript.")
    path = ad.project.root
    ad.close()
    mock = MockChatProvider()
    fresh = HexaShardAdapter.open(path, provider=mock)
    result = fresh.chat("What is BEACONEL?")
    assert "41.2" in mock.calls[-1]["context"] or result.retrieved_source_ids
    assert fresh.project.state.current_objective


def test_t10_adapter_restart_preserves_state(tmp_path):
    ad = _tiny(tmp_path)
    before = ad.project_status()
    path = ad.project.root
    ad.close()
    again = HexaShardAdapter.open(path, provider=MockChatProvider())
    after = again.project_status()
    assert after["source_count"] == before["source_count"]
    assert after["pin_count"] == before["pin_count"]
    assert (again.project.root / "pins.jsonl").exists()


def test_t11_mock_provider_works(tmp_path):
    ad = _tiny(tmp_path)
    r = ad.chat("hello")
    assert r.response_text.startswith("[mock:")
    assert r.provider == "mock"


@pytest.mark.skipif(not ollama_available("http://127.0.0.1:11434/api/generate"), reason="ollama down")
def test_t12_ollama_adapter_works(tmp_path):
    cfg = AdapterConfig(
        provider="ollama", model_context_budget=2000, max_output_tokens=16, timeout_s=90,
    )
    ad = HexaShardAdapter.create(
        tmp_path / "ollama_proj", name="ollama-smoke", mission="ping", config=cfg,
    )
    hx = ad.add_hex("n", HexType.SOURCE)
    ad.add_source("note", "ping", "Say PONG if you see this project note.", hex_id=hx.hex_id)
    r = ad.chat("Reply with the single word PONG.")
    assert r.response_text
    assert r.provider == "ollama"
    assert r.latency_ms >= 0


def test_t13_core_hash_unchanged():
    # Migrated: the frozen tree digest addressed the lab's on-disk
    # distribution; in-repo the same guarantee is per-module.
    assert core_module_digests() == FROZEN_CORE_MODULES


def test_t14_no_provider_dependency_inside_core():
    from hexashard_adapter.core_lock import core_root
    blob = ""
    for p in core_root().glob("*.py"):
        blob += p.read_text(encoding="utf-8").lower()
    for needle in ("ollama", "openai", "anthropic", "11434"):
        assert needle not in blob


def test_t15_model_response_is_not_a_source(tmp_path):
    mock = MockChatProvider(reply="I recommend option B. Adopt WIDGET-99 as CURRENT.")
    ad = _tiny(tmp_path)
    ad.provider = mock
    before = {s.source_id: s.content for s in ad.project.sources.all()}
    ad.chat("What should we do?")
    after = {s.source_id: s.content for s in ad.project.sources.all()}
    assert after.keys() == before.keys()
    assert all("WIDGET-99" not in c for c in after.values())
    assert all("option B" not in c for c in after.values())


def test_t16_cross_domain_retrieval(tmp_path):
    ad = _tiny(tmp_path)
    bugs = ad.add_hex("bugs", HexType.SOURCE, tags=["bugs"])
    ad.add_source(
        "bug", "BUG-4412",
        "BUG-4412: the ingest worker dies with HEAPSTARVE after six hours.",
        hex_id=bugs.hex_id, tags=["bugs"], claim_key="bug4412", claim_value="HEAPSTARVE",
    )
    mock = MockChatProvider()
    ad.provider = mock
    r = ad.chat("What failure does BUG-4412 report?")
    blob = mock.calls[-1]["context"]
    assert "HEAPSTARVE" in blob
    assert r.retrieved_source_ids


def test_t17_superseded_source_handled(tmp_path):
    ad = _tiny(tmp_path)
    hx = next(h for h in ad.project.hexmap.all())
    v1 = ad.add_source(
        "spec", "budget rev1", "GATEBUDGET daily cap is 4.0TB.",
        hex_id=hx.hex_id, claim_key="gate_budget", claim_value="4.0TB",
    )
    v2 = ad.add_source(
        "spec", "budget rev2", "GATEBUDGET daily cap is 6.1TB. Rev 2 supersedes rev 1.",
        hex_id=hx.hex_id, claim_key="gate_budget", claim_value="6.1TB",
    )
    ad.supersede(v1.source_id, v2.source_id)
    ad.pin("GATEBUDGET", "6.1TB", v2.source_id, critical=True)
    mock = MockChatProvider()
    ad.provider = mock
    ad.chat("What is the current GATEBUDGET?")
    assert "6.1TB" in mock.calls[-1]["context"]
    mock2 = MockChatProvider()
    ad.provider = mock2
    ad.chat(
        "What was the previous GATEBUDGET?",
        filters=RetrievalFilters(statuses=(SourceStatus.SUPERSEDED,)),
    )
    assert "4.0TB" in mock2.calls[-1]["context"]


def test_t18_instrumentation_emitted(tmp_path):
    ad = _tiny(tmp_path)
    ad.chat("ping")
    log = ad.project.root / "adapter_metrics.jsonl"
    assert log.is_file()
    line = log.read_text(encoding="utf-8").strip().splitlines()[-1]
    assert "full_model_input_tokens" in line
    assert "context_truncation" in line
    assert "epoch" in line
