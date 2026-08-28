"""Regressions for the findings raised at the pre-GitHub independent gate.

Each test names the finding it locks down.  None of them changes Core
semantics; they assert Adapter-level behaviour only.
"""

from __future__ import annotations

import pytest

from hexashard_adapter import HexaShardAdapter
from hexashard_adapter.config import AdapterConfig
from hexashard_adapter.errors import MalformedProviderResponse
from hexashard_adapter.provider import ChatProvider


def _project(tmp_path, **cfg):
    adapter = HexaShardAdapter.create(
        tmp_path / "p", name="gate", mission="gate regressions",
        config=AdapterConfig(provider="mock", **cfg),
    )
    source = adapter.add_source(
        "spec", "Budget", "The downlink budget per pass is 6.1 TB."
    )
    adapter.pin("downlink", "6.1 TB", source.source_id, critical=True)
    return adapter, source


# F-01 -------------------------------------------------------------------
def test_f01_adapter_imports_without_path_scaffolding():
    """The package imports cold; the lab build needed conftest to seed sys.path."""
    import subprocess
    import sys

    out = subprocess.run(
        [sys.executable, "-c",
         "import hexashard_adapter, hexashard_adapter.__main__; print('ok')"],
        capture_output=True, text=True,
    )
    assert out.returncode == 0, out.stderr
    assert "ok" in out.stdout


def test_f01_cli_entrypoint_runs():
    import subprocess
    import sys

    out = subprocess.run(
        [sys.executable, "-m", "hexashard_adapter", "--help"],
        capture_output=True, text=True,
    )
    assert out.returncode == 0, out.stderr
    assert "hexashard_adapter" in out.stdout


# F-02 -------------------------------------------------------------------
def test_f02_repointed_pin_is_surfaced_as_a_warning(tmp_path):
    """A pin repointed by supersession must not be reported as clean.

    Core stamps the stored pin NEEDS_REVIEW but ``check_pins`` re-resolves it to
    ACTIVE, so Core's own ``pin_warnings`` is empty.  The Adapter reports it.
    """
    adapter, old = _project(tmp_path)
    new = adapter.add_source(
        "spec", "Budget rev2", "The downlink budget per pass is 9.9 TB."
    )
    adapter.supersede(old.source_id, new.source_id)

    result = adapter.chat("what is the downlink budget per pass")

    assert result.pin_warnings, "repointed pin was silently reported as clean"
    warning = result.pin_warnings[0]
    assert warning["key"] == "downlink"
    assert warning["status"] == "NEEDS_REVIEW"


def test_f02_healthy_pin_produces_no_warning(tmp_path):
    adapter, _ = _project(tmp_path)
    assert adapter.chat("what is the downlink budget per pass").pin_warnings == []


# F-04 -------------------------------------------------------------------
def test_f04_malformed_provider_reply_raises_typed_error(tmp_path):
    class Malformed(ChatProvider):
        name = "malformed"

        def generate(self, **kwargs):
            return object()

    adapter, _ = _project(tmp_path)
    adapter.provider = Malformed()
    with pytest.raises(MalformedProviderResponse):
        adapter.chat("what is the downlink budget")


def test_f04_non_string_text_raises_typed_error(tmp_path):
    class BadText(ChatProvider):
        name = "badtext"

        def generate(self, **kwargs):
            class R:
                text = 42
                input_tokens = 1
                output_tokens = 1
                provider = "badtext"

            return R()

    adapter, _ = _project(tmp_path)
    adapter.provider = BadText()
    with pytest.raises(MalformedProviderResponse):
        adapter.chat("what is the downlink budget")


# F-05 -------------------------------------------------------------------
def test_f05_caller_cannot_mutate_core_state_through_the_turn_context(tmp_path):
    """Core hands back live ActiveState references; the Adapter must copy them."""
    adapter, _ = _project(tmp_path)
    before = len(adapter.project.state.active_pins)

    result = adapter.chat("what is the downlink budget")
    result.pin_warnings.append({"pin_id": "INJECTED"})

    turn = adapter.project.handle_turn("what is the downlink budget")
    hardened = __import__(
        "hexashard_adapter.adapter", fromlist=["_harden_context"]
    )._harden_context(turn.response_context)
    hardened["active_pins"].append({"key": "INJECTED", "value": "attacker"})

    assert len(adapter.project.state.active_pins) == before


# F-03 — documented, not fixed -------------------------------------------
def test_f03_provider_failure_still_consumes_a_turn(tmp_path):
    """Documented limitation: NORMAL mode advances state before the model call.

    This locks the behaviour in so a future change to it is deliberate.
    """
    class Boom(ChatProvider):
        name = "boom"

        def generate(self, **kwargs):
            raise RuntimeError("provider exploded")

    adapter, _ = _project(tmp_path)
    adapter.provider = Boom()
    before = adapter.project.state.turn
    with pytest.raises(RuntimeError):
        adapter.chat("what is the downlink budget")
    assert adapter.project.state.turn == before + 1


def test_read_only_mode_consumes_nothing(tmp_path):
    adapter, _ = _project(tmp_path)
    adapter.close()
    adapter = HexaShardAdapter.open(
        tmp_path / "p", config=AdapterConfig(provider="mock", mode="READ_ONLY")
    )
    turn, epoch = adapter.project.state.turn, adapter.project.state.epoch
    for i in range(25):
        adapter.chat(f"question {i}")
    assert (adapter.project.state.turn, adapter.project.state.epoch) == (turn, epoch)
    with pytest.raises(PermissionError):
        adapter.add_source("note", "x", "y")


# F-06 -------------------------------------------------------------------
def test_f06_non_http_provider_endpoint_is_rejected():
    """A provider endpoint is caller-supplied; urllib would honour file:."""
    from hexashard_adapter.errors import InvalidProviderConfiguration
    from hexashard_adapter.provider import _require_http_endpoint, ollama_available

    for bad in ("file:///etc/passwd", "ftp://host/x", "/etc/passwd"):
        with pytest.raises(InvalidProviderConfiguration):
            _require_http_endpoint(bad)

    assert _require_http_endpoint("http://127.0.0.1:11434/api/generate")
    assert _require_http_endpoint("https://host/api/generate")
    # the availability probe must not raise on a hostile endpoint either
    assert ollama_available("file:///etc/passwd") is False
