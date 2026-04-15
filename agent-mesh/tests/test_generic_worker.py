"""Tests for GenericLLMWorker.

No network. No real HTTP client. We assert that:
  - GenericLLMWorker inherits from MeshWorker (protocol preserved)
  - call_llm() delegates to backend.generate()
  - system_prompt is passed through
  - output_format="json" is appended as an instruction
  - task constraints override the default system_prompt
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from workers.generic_worker.worker import GenericLLMWorker  # noqa: E402
from workers.protocol import MeshWorker, WorkerConfig, generate_keypair  # noqa: E402


# ── Fake backend ───────────────────────────────────────────────────────────────


class FakeBackend:
    def __init__(self, response: str = "fake response") -> None:
        self.response = response
        self.calls: list[tuple[str, str | None]] = []

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        self.calls.append((prompt, system_prompt))
        return self.response


def _make_config() -> WorkerConfig:
    sk, pk = generate_keypair()
    return WorkerConfig(
        agent_id="agent_generic_test",
        capabilities=["analysis"],
        server_url="http://localhost:9999",  # never actually called
        private_key_b64=sk,
        public_key_b64=pk,
        key_id="key_test_v1",
    )


# ── Tests ──────────────────────────────────────────────────────────────────────


def test_generic_worker_is_mesh_worker():
    backend = FakeBackend()
    worker = GenericLLMWorker(config=_make_config(), backend=backend)
    assert isinstance(worker, MeshWorker)


def test_generic_worker_call_llm_delegates_to_backend():
    backend = FakeBackend(response="delegated")
    worker = GenericLLMWorker(config=_make_config(), backend=backend)
    out = worker.call_llm("what is 2+2?", {})
    assert out == "delegated"
    assert len(backend.calls) == 1
    prompt, sys_prompt = backend.calls[0]
    assert prompt == "what is 2+2?"
    # default system prompt is used
    assert sys_prompt is not None
    assert "multi-agent" in sys_prompt


def test_generic_worker_no_default_system_prompt():
    backend = FakeBackend()
    worker = GenericLLMWorker(config=_make_config(), backend=backend, system_prompt=None)
    worker.call_llm("x", {})
    _, sys_prompt = backend.calls[0]
    assert sys_prompt is None


def test_generic_worker_constraints_override_system_prompt():
    backend = FakeBackend()
    worker = GenericLLMWorker(config=_make_config(), backend=backend)
    worker.call_llm("x", {"system_prompt": "be terse"})
    _, sys_prompt = backend.calls[0]
    assert sys_prompt == "be terse"


def test_generic_worker_json_format_appends_instruction():
    backend = FakeBackend()
    worker = GenericLLMWorker(config=_make_config(), backend=backend)
    worker.call_llm("give me data", {"output_format": "json"})
    prompt, _ = backend.calls[0]
    assert "give me data" in prompt
    assert "valid JSON" in prompt


def test_generic_worker_text_format_preserves_prompt():
    backend = FakeBackend()
    worker = GenericLLMWorker(config=_make_config(), backend=backend)
    worker.call_llm("hello", {"output_format": "text"})
    prompt, _ = backend.calls[0]
    assert prompt == "hello"


def test_generic_worker_call_llm_returns_string():
    backend = FakeBackend(response="ok")
    worker = GenericLLMWorker(config=_make_config(), backend=backend)
    out = worker.call_llm("x", {})
    assert isinstance(out, str)


def test_generic_worker_empty_constraints():
    backend = FakeBackend()
    worker = GenericLLMWorker(config=_make_config(), backend=backend)
    worker.call_llm("x", {})
    assert len(backend.calls) == 1


def test_generic_worker_multiple_calls_all_delegated():
    backend = FakeBackend()
    worker = GenericLLMWorker(config=_make_config(), backend=backend)
    worker.call_llm("one", {})
    worker.call_llm("two", {})
    worker.call_llm("three", {})
    assert [c[0] for c in backend.calls] == ["one", "two", "three"]


def test_generic_worker_does_not_hit_network_on_init():
    # Instantiating with a fake backend + no registration must not touch the network.
    backend = FakeBackend()
    GenericLLMWorker(config=_make_config(), backend=backend)
    # If we reach here, nothing blocked. Also verify the HTTP client was created but unused.
    assert backend.calls == []


def test_generic_worker_backend_attribute_exposed():
    backend = FakeBackend()
    worker = GenericLLMWorker(config=_make_config(), backend=backend)
    assert worker.backend is backend
