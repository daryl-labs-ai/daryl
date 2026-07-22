"""B5 — live-smoke preparation tests. ZERO network, ZERO real key required.

Proves the mechanical security model: dry-run touches no socket, live mode is
refused without the full authorization chain, caps stop BEFORE being crossed,
secrets never reach artifacts, the three-level prompt-hash contract holds on
the live path, manifests validate, strata follow the pre-registered rules,
verify==OK stays a validity condition, and no writer beyond
PRLStore.commit_swarm_entry exists.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.swarm.harness.live import (
    BudgetExceeded,
    BudgetGuard,
    LiveCallError,
    LiveExecutionNotAuthorized,
    LiveProvider,
    NoNetworkTransport,
    SmokeCaps,
    SmokeConfig,
    build_provider,
    estimate_smoke_cost,
)
from benchmarks.swarm.harness.cases import load_cases
from benchmarks.swarm.harness.manifest import PriceEntry
from benchmarks.swarm.harness.parity import step_uid
from benchmarks.swarm.harness.smoke import run_smoke

CONFIG_PATH = Path(__file__).resolve().parents[2] / "benchmarks/swarm/B5_SMOKE_CONFIG.json"


def _config(**over) -> SmokeConfig:
    data = json.loads(CONFIG_PATH.read_text())
    data.update(over)
    return SmokeConfig(**data)


def _guard(config: SmokeConfig, clock=None) -> BudgetGuard:
    kwargs = {"clock": clock} if clock else {}
    return BudgetGuard(config.caps, config.price, **kwargs)


# --- committed config is safe by default -------------------------------------


def test_committed_config_is_unauthorized_by_default():
    config = _config()
    assert config.live_execution_authorized is False
    assert config.authorized_budget_usd is None
    assert config.caps.max_usd <= 10.0
    assert config.caps.max_total_tokens <= 200_000
    assert config.caps.max_wall_seconds <= 900


def test_config_requires_caps_and_authorized_budget():
    with pytest.raises(Exception):  # caps entirely missing
        _config(caps=None)
    with pytest.raises(Exception, match="authorized_budget_usd"):
        _config(live_execution_authorized=True, authorized_budget_usd=None)
    with pytest.raises(Exception, match="exceeds the authorized"):
        _config(live_execution_authorized=True, authorized_budget_usd=5.0)  # caps=10 > 5


# --- live refusals -----------------------------------------------------------


def test_live_refused_without_authorization():
    config = _config()
    with pytest.raises(LiveExecutionNotAuthorized, match="live_execution_authorized"):
        build_provider(config, _guard(config), "live")


def test_live_refused_without_env_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = _config(live_execution_authorized=True, authorized_budget_usd=10.0)
    with pytest.raises(LiveExecutionNotAuthorized, match="OPENAI_API_KEY"):
        build_provider(config, _guard(config), "live")


def test_dry_run_allowed_without_any_authorization():
    config = _config()
    provider = build_provider(config, _guard(config), "dry_run")
    call = provider.complete(step_uid("worker", "implement", "task:1"), "hello world")
    assert call.response_text.startswith("dry-run-response:")
    assert provider.results[0].network is False


# --- budget guard: refuse BEFORE, never after --------------------------------


def test_budget_guard_stops_before_call_cap():
    config = _config(caps={**_config().caps.model_dump(), "max_calls": 2})
    guard = _guard(config)
    provider = build_provider(config, guard, "dry_run")
    provider.complete(step_uid("worker", "implement", "t"), "p1")
    provider.complete(step_uid("worker", "self_check", "t"), "p2")
    with pytest.raises(BudgetExceeded, match="max_calls"):
        provider.complete(step_uid("worker", "submit_work", "t"), "p3")
    assert guard.calls == 2  # the third call spent NOTHING


def test_budget_guard_stops_before_token_cap():
    config = _config(caps={**_config().caps.model_dump(), "max_total_tokens": 600})
    guard = _guard(config)
    provider = build_provider(config, guard, "dry_run")
    with pytest.raises(BudgetExceeded, match="max_total_tokens"):
        provider.complete(step_uid("worker", "implement", "t"), "x" * 4000)
    assert guard.calls == 0 and guard.tokens_in == 0


def test_budget_guard_stops_on_wall_clock():
    config = _config()
    fake_now = [0.0]
    guard = BudgetGuard(config.caps, config.price, clock=lambda: fake_now[0])
    fake_now[0] = config.caps.max_wall_seconds + 1.0
    with pytest.raises(BudgetExceeded, match="max_wall_seconds"):
        guard.precheck(10)


def test_budget_guard_cost_cap_uses_price_table():
    config = _config(
        price={"input_usd_per_mtok": 1_000_000.0, "output_usd_per_mtok": 1_000_000.0}
    )
    guard = _guard(config)
    with pytest.raises(BudgetExceeded, match="max_usd"):
        guard.precheck(est_tokens_in=100)
    assert guard.calls == 0


# --- retries and invalidity --------------------------------------------------


class _FailingTransport:
    network = False

    def __init__(self):
        self.attempts = 0

    def send(self, prompt, config):
        self.attempts += 1
        raise ConnectionError("simulated provider failure")


def test_failed_call_after_retries_is_invalid_not_scored():
    config = _config(retry={"max_retries": 1, "backoff_seconds": 0.0})
    guard = _guard(config)
    transport = _FailingTransport()
    provider = LiveProvider(config, guard, transport)
    with pytest.raises(LiveCallError):
        provider.complete(step_uid("worker", "implement", "t"), "p")
    assert transport.attempts == 2      # initial + 1 retry
    assert guard.calls == 0             # nothing committed


# --- full dry-run smoke ------------------------------------------------------


def test_dry_run_smoke_full_pair_zero_network(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-FAKE-SECRET-b5-test-000")
    config = _config()
    report = run_smoke(config, tmp_path / "smoke", mode="dry_run")

    assert report.aborted is None
    assert report.provenance.mode == "dry_run"
    assert report.provenance.live_execution_authorized is False
    assert report.provenance.api_key_env_name == "OPENAI_API_KEY"  # NAME only
    # all three runs valid; verify==OK is validity, not a score
    assert set(report.validity) == {"A", "Bprime", "B"}
    assert all(v["valid"] for v in report.validity.values())
    # pre-registered strata rules applied
    assert report.stratum == {"Bprime": "eligible", "B": "eligible"}
    # spend accounted and within caps
    assert 0 < report.spend["tokens_in"] < config.caps.max_total_tokens
    assert report.spend["cost_usd"] < config.caps.max_usd
    # SECRETS: the fake key value appears in NO artifact
    for artifact in (tmp_path / "smoke").rglob("*"):
        if artifact.is_file():
            assert b"sk-FAKE-SECRET-b5-test-000" not in artifact.read_bytes(), artifact


def test_dry_run_smoke_three_level_hashes(tmp_path):
    config = _config()
    run_smoke(config, tmp_path / "smoke", mode="dry_run")
    records = {
        cond: json.loads((tmp_path / "smoke" / cond / "prompt_records.json").read_text())
        for cond in ("A", "Bprime", "B")
    }
    base = {cond: {r["step_key"]: r["base_prompt_hash"] for r in rec}
            for cond, rec in records.items()}
    assert base["A"] == base["Bprime"] == base["B"]
    for r in records["A"] + records["Bprime"]:
        assert r["effective_prompt_hash"] == r["base_prompt_hash"]
        assert r["grounding_block_hash"] == ""
    for r in records["B"]:
        assert r["effective_prompt_hash"] != r["base_prompt_hash"]
        assert r["grounding_block_hash"] != ""


def test_dry_run_smoke_manifests_valid(tmp_path):
    from benchmarks.swarm.harness.manifest import RunManifest

    run_smoke(_config(), tmp_path / "smoke", mode="dry_run")
    for cond in ("A", "Bprime", "B"):
        manifest = RunManifest(
            **json.loads((tmp_path / "smoke" / cond / "manifest.json").read_text())
        )
        assert manifest.condition == cond
        if cond != "A":
            assert manifest.grounding.kernel_version == "1.0"
            assert manifest.grounding.verify_status == "OK"


def test_smoke_aborts_and_reports_stop(tmp_path):
    # a cap so small the FIRST call cannot be afforded -> STOP before spending
    config = _config(caps={**_config().caps.model_dump(), "max_total_tokens": 10})
    report = run_smoke(config, tmp_path / "smoke", mode="dry_run")
    assert report.aborted is not None and "BudgetExceeded" in report.aborted
    assert report.spend["tokens_in"] == 0
    assert report.stratum["B"] == "invalid"  # missing runs never masked as scores


# --- estimation --------------------------------------------------------------


def test_estimate_is_conservative_and_within_caps(tmp_path):
    config = _config()
    case = next(c for c in load_cases() if c.case_id == config.case_id)
    estimate = estimate_smoke_cost(config, case)
    assert estimate.calls == 15  # 5 agent steps x 3 conditions
    assert estimate.tokens_in_est + estimate.tokens_out_est < config.caps.max_total_tokens
    assert estimate.usd_est < config.caps.max_usd
    report = run_smoke(config, tmp_path / "smoke", mode="dry_run")
    assert estimate.tokens_in_est >= report.spend["tokens_in"]  # conservative


# --- no additional writer ----------------------------------------------------


def test_no_new_writer_and_no_kernel_import_in_live_modules():
    """The live modules add NO write path: no kernel import, no PRLStore
    import — every Swarm append still flows through the recorders built by the
    runner (which wrap PRLStore.commit_swarm_entry exclusively)."""
    for module in ("live", "smoke"):
        text = (
            Path(__file__).resolve().parents[2]
            / "benchmarks/swarm/harness" / f"{module}.py"
        ).read_text()
        assert "dsm.core.storage" not in text, module
        assert "from prl.store" not in text and "import prl.store" not in text, module
        assert "Storage(" not in text, module
