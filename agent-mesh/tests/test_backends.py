"""Tests for LLM backends.

These tests NEVER make real network calls. Each backend is constructed with an
injected fake client that mirrors the shape of the real SDK's relevant methods.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# Make the `workers` package importable from tests.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from workers.backends import LLMBackend, create_backend  # noqa: E402
from workers.backends.anthropic_backend import AnthropicBackend  # noqa: E402
from workers.backends.ollama_backend import OllamaBackend  # noqa: E402
from workers.backends.openai_backend import OpenAIBackend  # noqa: E402
from workers.backends.openai_compatible_backend import OpenAICompatibleBackend  # noqa: E402
from workers.backends.zhipu_backend import (  # noqa: E402
    CODING_API_URL,
    GENERAL_API_URL,
    ZhipuBackend,
    is_coding_model,
    resolve_base_url,
)


# ── Fake SDK clients ───────────────────────────────────────────────────────────


class FakeAnthropicMessages:
    def __init__(self) -> None:
        self.last_kwargs: dict | None = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return SimpleNamespace(content=[SimpleNamespace(text="anthropic response")])


class FakeAnthropicClient:
    def __init__(self) -> None:
        self.messages = FakeAnthropicMessages()


class FakeOpenAIChatCompletions:
    def __init__(self) -> None:
        self.last_kwargs: dict | None = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        choice = SimpleNamespace(message=SimpleNamespace(content="openai response"))
        return SimpleNamespace(choices=[choice])


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=FakeOpenAIChatCompletions())


class FakeHttpResponse:
    def __init__(self, json_body: dict, status_code: int = 200) -> None:
        self._json = json_body
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if not (200 <= self.status_code < 300):
            raise RuntimeError(f"http {self.status_code}")

    def json(self) -> dict:
        return self._json


class FakeHttpxClient:
    def __init__(self, response: FakeHttpResponse) -> None:
        self._response = response
        self.last_post: dict | None = None

    def post(self, url: str, json: dict):
        self.last_post = {"url": url, "json": json}
        return self._response


# ── Anthropic backend ──────────────────────────────────────────────────────────


def test_anthropic_backend_generate_returns_string():
    client = FakeAnthropicClient()
    backend = AnthropicBackend(client=client, model="claude-sonnet-4-20250514")
    out = backend.generate("hello")
    assert isinstance(out, str)
    assert out == "anthropic response"


def test_anthropic_backend_passes_system_prompt():
    client = FakeAnthropicClient()
    backend = AnthropicBackend(client=client)
    backend.generate("hello", system_prompt="be concise")
    assert client.messages.last_kwargs["system"] == "be concise"
    assert client.messages.last_kwargs["messages"][0]["content"] == "hello"


def test_anthropic_backend_omits_system_when_none():
    client = FakeAnthropicClient()
    backend = AnthropicBackend(client=client)
    backend.generate("hello")
    assert "system" not in client.messages.last_kwargs


def test_anthropic_backend_honors_model_and_max_tokens():
    client = FakeAnthropicClient()
    backend = AnthropicBackend(client=client, model="claude-3-opus", max_tokens=500)
    backend.generate("x")
    kw = client.messages.last_kwargs
    assert kw["model"] == "claude-3-opus"
    assert kw["max_tokens"] == 500


def test_anthropic_backend_requires_api_key_without_client():
    with pytest.raises(ValueError):
        AnthropicBackend(api_key=None)


def test_anthropic_backend_satisfies_protocol():
    backend = AnthropicBackend(client=FakeAnthropicClient())
    assert isinstance(backend, LLMBackend)


# ── OpenAI backend ─────────────────────────────────────────────────────────────


def test_openai_backend_generate_returns_string():
    client = FakeOpenAIClient()
    backend = OpenAIBackend(client=client)
    out = backend.generate("hello")
    assert out == "openai response"


def test_openai_backend_system_prompt_prepended_as_message():
    client = FakeOpenAIClient()
    backend = OpenAIBackend(client=client)
    backend.generate("hi", system_prompt="be factual")
    msgs = client.chat.completions.last_kwargs["messages"]
    assert msgs[0] == {"role": "system", "content": "be factual"}
    assert msgs[1] == {"role": "user", "content": "hi"}


def test_openai_backend_without_system_prompt_sends_only_user():
    client = FakeOpenAIClient()
    backend = OpenAIBackend(client=client)
    backend.generate("only user")
    msgs = client.chat.completions.last_kwargs["messages"]
    assert len(msgs) == 1
    assert msgs[0]["role"] == "user"


def test_openai_backend_honors_model():
    client = FakeOpenAIClient()
    backend = OpenAIBackend(client=client, model="gpt-4o")
    backend.generate("x")
    assert client.chat.completions.last_kwargs["model"] == "gpt-4o"


def test_openai_backend_requires_api_key_without_client():
    with pytest.raises(ValueError):
        OpenAIBackend(api_key=None)


def test_openai_backend_satisfies_protocol():
    assert isinstance(OpenAIBackend(client=FakeOpenAIClient()), LLMBackend)


# ── Ollama backend ─────────────────────────────────────────────────────────────


def test_ollama_backend_generate_returns_string():
    http = FakeHttpxClient(FakeHttpResponse({"response": "qwen says hi"}))
    backend = OllamaBackend(model="qwen2.5", client=http)
    out = backend.generate("hello")
    assert out == "qwen says hi"


def test_ollama_backend_sends_correct_payload():
    http = FakeHttpxClient(FakeHttpResponse({"response": "ok"}))
    backend = OllamaBackend(model="llama3.1", client=http)
    backend.generate("what time is it", system_prompt="be brief")
    assert http.last_post["url"] == "/api/generate"
    payload = http.last_post["json"]
    assert payload["model"] == "llama3.1"
    assert payload["prompt"] == "what time is it"
    assert payload["system"] == "be brief"
    assert payload["stream"] is False


def test_ollama_backend_no_system_prompt_field_when_none():
    http = FakeHttpxClient(FakeHttpResponse({"response": "ok"}))
    backend = OllamaBackend(model="qwen2.5", client=http)
    backend.generate("x")
    assert "system" not in http.last_post["json"]


def test_ollama_backend_raises_on_non_2xx():
    http = FakeHttpxClient(FakeHttpResponse({}, status_code=500))
    backend = OllamaBackend(model="qwen2.5", client=http)
    with pytest.raises(RuntimeError):
        backend.generate("x")


def test_ollama_backend_satisfies_protocol():
    http = FakeHttpxClient(FakeHttpResponse({"response": "ok"}))
    backend = OllamaBackend(model="qwen2.5", client=http)
    assert isinstance(backend, LLMBackend)


# ── OpenAI-compatible backend ──────────────────────────────────────────────────


def test_openai_compatible_generate_returns_string():
    client = FakeOpenAIClient()
    backend = OpenAICompatibleBackend(
        base_url="https://openrouter.ai/api/v1",
        client=client,
        model="anthropic/claude-3.5-sonnet",
    )
    assert backend.generate("hi") == "openai response"


def test_openai_compatible_requires_model():
    with pytest.raises(ValueError):
        OpenAICompatibleBackend(base_url="https://x/v1", client=FakeOpenAIClient(), model="")


def test_openai_compatible_requires_api_key_without_client():
    with pytest.raises(ValueError):
        OpenAICompatibleBackend(base_url="https://x/v1", model="m")


def test_openai_compatible_honors_custom_model():
    client = FakeOpenAIClient()
    backend = OpenAICompatibleBackend(
        base_url="https://api.groq.com/openai/v1",
        client=client,
        model="llama-3.3-70b",
    )
    backend.generate("x")
    assert client.chat.completions.last_kwargs["model"] == "llama-3.3-70b"


def test_openai_compatible_satisfies_protocol():
    backend = OpenAICompatibleBackend(
        base_url="https://x/v1", client=FakeOpenAIClient(), model="m"
    )
    assert isinstance(backend, LLMBackend)


# ── Factory ────────────────────────────────────────────────────────────────────


def test_factory_anthropic():
    backend = create_backend(
        {"provider": "anthropic", "client": FakeAnthropicClient(), "model": "claude-x"}
    )
    assert isinstance(backend, AnthropicBackend)
    assert backend.generate("x") == "anthropic response"


def test_factory_openai():
    backend = create_backend(
        {"provider": "openai", "client": FakeOpenAIClient(), "model": "gpt-x"}
    )
    assert isinstance(backend, OpenAIBackend)
    assert backend.generate("x") == "openai response"


def test_factory_ollama():
    http = FakeHttpxClient(FakeHttpResponse({"response": "local"}))
    backend = create_backend(
        {"provider": "ollama", "client": http, "model": "qwen2.5"}
    )
    assert isinstance(backend, OllamaBackend)
    assert backend.generate("x") == "local"


def test_factory_openai_compatible():
    backend = create_backend(
        {
            "provider": "openai_compatible",
            "base_url": "https://openrouter.ai/api/v1",
            "client": FakeOpenAIClient(),
            "model": "some/model",
        }
    )
    assert isinstance(backend, OpenAICompatibleBackend)
    assert backend.generate("x") == "openai response"


def test_factory_openai_compatible_requires_base_url():
    with pytest.raises(ValueError):
        create_backend(
            {"provider": "openai_compatible", "client": FakeOpenAIClient(), "model": "m"}
        )


def test_factory_unknown_provider_raises():
    with pytest.raises(ValueError):
        create_backend({"provider": "banana"})


def test_factory_missing_provider_raises():
    with pytest.raises(ValueError):
        create_backend({})


# ── Zhipu backend (GLM) ────────────────────────────────────────────────────────


def test_zhipu_general_model_uses_general_api():
    """A general model like 'glm-4' must auto-route to the general endpoint."""
    assert resolve_base_url("glm-4") == GENERAL_API_URL
    assert resolve_base_url("glm-4-flash") == GENERAL_API_URL
    assert resolve_base_url("glm-4-plus") == GENERAL_API_URL
    backend = ZhipuBackend(client=FakeOpenAIClient(), model="glm-4")
    assert backend._base_url == GENERAL_API_URL


def test_zhipu_coding_model_uses_coding_api():
    """A coding model (glm-code, codegeex, …) must auto-route to the coding endpoint."""
    assert is_coding_model("glm-code") is True
    assert is_coding_model("glm-coding") is True
    assert is_coding_model("codegeex") is True
    assert is_coding_model("codegeex-4") is True
    assert is_coding_model("glm-4") is False  # baseline — not a coding model
    assert resolve_base_url("glm-code") == CODING_API_URL
    assert resolve_base_url("codegeex-4") == CODING_API_URL
    backend = ZhipuBackend(client=FakeOpenAIClient(), model="glm-code")
    assert backend._base_url == CODING_API_URL


def test_zhipu_explicit_base_url_overrides_auto():
    """An explicit base_url must win over the auto-routing heuristic."""
    custom = "https://custom.zhipu-internal.example/v1"
    backend = ZhipuBackend(
        client=FakeOpenAIClient(),
        model="glm-code",  # would normally go to CODING_API_URL
        base_url=custom,
    )
    assert backend._base_url == custom


def test_zhipu_generate():
    """Normal generate() call — delegates to the injected chat.completions client."""
    client = FakeOpenAIClient()
    backend = ZhipuBackend(client=client, model="glm-4")
    out = backend.generate("hello world")
    assert isinstance(out, str)
    assert out == "openai response"  # fake client returns this stub
    kw = client.chat.completions.last_kwargs
    assert kw["model"] == "glm-4"
    assert kw["messages"] == [{"role": "user", "content": "hello world"}]


def test_zhipu_generate_with_system_prompt():
    """system_prompt is prepended as a system message, matching OpenAI schema."""
    client = FakeOpenAIClient()
    backend = ZhipuBackend(client=client, model="glm-4")
    backend.generate("analyze this", system_prompt="be precise")
    msgs = client.chat.completions.last_kwargs["messages"]
    assert msgs[0] == {"role": "system", "content": "be precise"}
    assert msgs[1] == {"role": "user", "content": "analyze this"}


def test_zhipu_uses_default_model():
    """When no model is passed, the backend falls back to DEFAULT_MODEL (glm-4)."""
    from workers.backends.zhipu_backend import DEFAULT_MODEL

    assert DEFAULT_MODEL == "glm-4"
    backend = ZhipuBackend(client=FakeOpenAIClient())
    assert backend._model == "glm-4"
    assert backend._base_url == GENERAL_API_URL


def test_zhipu_api_key_required():
    """Without a client injection, api_key is mandatory."""
    with pytest.raises(ValueError):
        ZhipuBackend(api_key=None, model="glm-4")


def test_zhipu_satisfies_protocol():
    """Runtime LLMBackend protocol check."""
    assert isinstance(ZhipuBackend(client=FakeOpenAIClient(), model="glm-4"), LLMBackend)


def test_factory_zhipu():
    """Factory routes 'zhipu' to ZhipuBackend."""
    backend = create_backend(
        {
            "provider": "zhipu",
            "client": FakeOpenAIClient(),
            "model": "glm-4",
        }
    )
    assert isinstance(backend, ZhipuBackend)
    assert backend._model == "glm-4"
    assert backend._base_url == GENERAL_API_URL
    assert backend.generate("hi") == "openai response"


def test_factory_zhipu_coding_model_routes_to_coding_url():
    """Factory with a coding model picks the coding endpoint."""
    backend = create_backend(
        {
            "provider": "zhipu",
            "client": FakeOpenAIClient(),
            "model": "codegeex-4",
        }
    )
    assert isinstance(backend, ZhipuBackend)
    assert backend._base_url == CODING_API_URL


def test_factory_zhipu_explicit_base_url_passthrough():
    """Factory forwards base_url override to ZhipuBackend."""
    custom = "https://custom.zhipu/v1"
    backend = create_backend(
        {
            "provider": "zhipu",
            "client": FakeOpenAIClient(),
            "model": "glm-code",  # would auto-route to CODING_API_URL
            "base_url": custom,
        }
    )
    assert backend._base_url == custom
