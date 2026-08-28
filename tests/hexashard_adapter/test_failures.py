from __future__ import annotations

from pathlib import Path

import pytest

from hexashard import HexType, SourceStatus
from hexashard_adapter import (
    AdapterConfig,
    ContextBudgetExceeded,
    HexaShardAdapter,
    InvalidProviderConfiguration,
    MockChatProvider,
    ProjectNotFound,
    ProviderUnavailable,
    UnavailableProvider,
)
from hexashard_adapter.context import NO_SOURCE_SENTENCE, assemble


def _tiny(tmp_path: Path, **cfg_kw) -> HexaShardAdapter:
    cfg = AdapterConfig(provider="mock", **cfg_kw)
    ad = HexaShardAdapter.create(
        tmp_path / "proj", name="tiny", mission="m", config=cfg, provider=MockChatProvider(),
    )
    hx = ad.add_hex("architecture", HexType.SOURCE)
    src = ad.add_source(
        "spec", "SG-01", "BEACONEL elevation is 41.2 degrees.",
        hex_id=hx.hex_id, claim_key="beacon_elevation", claim_value="41.2",
    )
    ad.pin("BEACONEL", "41.2", src.source_id, critical=True)
    return ad


def test_f1_no_relevant_source(tmp_path):
    ad = _tiny(tmp_path)
    mock = MockChatProvider()
    ad.provider = mock
    r = ad.chat("ZEPHYRX mass?")
    assert r.no_source_retrieved
    assert NO_SOURCE_SENTENCE in mock.calls[-1]["context"]


def test_f2_retrieved_exceeds_budget_is_truncated_not_silent(tmp_path):
    ctx = {
        "mission": "m", "current_objective": "o",
        "active_pins": [
            {"key": "K", "value": "1", "source_ref": "P1.S0001", "critical": True, "status": "ACTIVE"},
        ],
        "retrieved": [
            {"source_id": f"P1.S{i:04d}", "source_status": "CURRENT", "source_title": "n",
             "text": "tokenfiller " * 50}
            for i in range(12)
        ],
        "pin_warnings": [], "ambiguities": [], "current_summary": "s" * 200,
        "recent_decisions": [], "open_questions": [],
    }
    assembled = assemble(user_message="q", response_context=ctx, budget=500)
    assert assembled.truncated
    assert assembled.tokens <= 500
    assert "K" in assembled.sections["critical_pins"]


def test_f3_provider_context_smaller_than_budget():
    with pytest.raises(InvalidProviderConfiguration):
        AdapterConfig(model_context_budget=9000, provider_context_limit=100).validate()


def test_f4_provider_unavailable(tmp_path):
    ad = _tiny(tmp_path)
    ad.provider = UnavailableProvider()
    with pytest.raises(ProviderUnavailable):
        ad.chat("hello")


def test_f5_project_reload(tmp_path):
    ad = _tiny(tmp_path)
    path = ad.project.root
    n = ad.project_status()["source_count"]
    ad.close()
    b = HexaShardAdapter.open(path, provider=MockChatProvider())
    assert b.project_status()["source_count"] == n


def test_f6_stale_pin(tmp_path):
    ad = _tiny(tmp_path)
    hx = next(iter(ad.project.hexmap.all()))
    old = next(s for s in ad.project.sources.all() if s.claim_key == "beacon_elevation")
    new = ad.add_source(
        "spec", "SG-02", "BEACONEL restated.",
        hex_id=hx.hex_id, claim_key="beacon_elevation", claim_value="41.2",
    )
    ad.supersede(old.source_id, new.source_id, reconcile_pins=False)
    mock = MockChatProvider()
    ad.provider = mock
    r = ad.chat("BEACONEL?")
    assert r.pin_warnings
    assert "PROJECT WARNING" in mock.calls[-1]["context"]
    assert any(w.get("status") == "STALE" for w in r.pin_warnings)


def test_f7_supersede_between_turns(tmp_path):
    ad = _tiny(tmp_path)
    hx = next(iter(ad.project.hexmap.all()))
    v1 = ad.add_source(
        "spec", "rev1", "GATEBUDGET is 4.0TB.",
        hex_id=hx.hex_id, claim_key="gate_budget", claim_value="4.0TB",
    )
    mock = MockChatProvider()
    ad.provider = mock
    ad.chat("GATEBUDGET?")
    assert "4.0TB" in mock.calls[-1]["context"]
    v2 = ad.add_source(
        "spec", "rev2", "GATEBUDGET is 6.1TB.",
        hex_id=hx.hex_id, claim_key="gate_budget", claim_value="6.1TB",
    )
    ad.supersede(v1.source_id, v2.source_id)
    ad.pin("GATEBUDGET", "6.1TB", v2.source_id, critical=True)
    mock2 = MockChatProvider()
    ad.provider = mock2
    ad.chat("What is current GATEBUDGET?")
    assert "6.1TB" in mock2.calls[-1]["context"]


def test_f8_empty_visible_chat_existing_project(tmp_path):
    ad = _tiny(tmp_path)
    path = ad.project.root
    ad.close()
    mock = MockChatProvider()
    b = HexaShardAdapter.open(path, provider=mock)
    b.chat("What is BEACONEL?")
    assert "41.2" in mock.calls[-1]["context"]


def test_f9_huge_store_small_budget(tmp_path):
    ad = _tiny(tmp_path, model_context_budget=700)
    for i in range(30):
        ad.add_source("minutes", f"m{i}", ("cafeteria kettle badge " * 80) + f" row{i}")
    mock = MockChatProvider()
    ad.provider = mock
    r = ad.chat("cafeteria kettle")
    assert r.total_context_tokens <= 700
    assert r.project_store_tokens > r.total_context_tokens
    assert "BEACONEL" in mock.calls[-1]["system"] + mock.calls[-1]["context"]


def test_project_not_found(tmp_path):
    with pytest.raises(ProjectNotFound):
        HexaShardAdapter.open(tmp_path / "missing")


def test_protected_overflow_raises():
    ctx = {
        "mission": "M" * 4000,
        "current_objective": "O" * 4000,
        "active_pins": [
            {"key": "K", "value": "V" * 4000, "source_ref": "P1.S0001",
             "critical": True, "status": "ACTIVE"},
        ],
        "retrieved": [], "pin_warnings": [], "ambiguities": [],
        "current_summary": "", "recent_decisions": [], "open_questions": [],
    }
    with pytest.raises(ContextBudgetExceeded):
        assemble(user_message="u" * 4000, response_context=ctx, budget=200)


def test_read_only_does_not_increment_turn(tmp_path):
    ad = _tiny(tmp_path)
    ad.config.mode = "READ_ONLY"
    before = ad.project.state.turn
    ad.chat("BEACONEL?")
    assert ad.project.state.turn == before
    with pytest.raises(PermissionError):
        ad.add_source("n", "t", "c")
