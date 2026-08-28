"""Provider boundary. Core does not import this module."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass, field
from typing import Any, Protocol

from hexashard.tokens import estimate_tokens

from .errors import InvalidProviderConfiguration, ProviderUnavailable
from .config import AdapterConfig


#: Schemes the Adapter is willing to hand to ``urlopen``.  ``config.endpoint``
#: is caller-supplied, and urllib would otherwise honour ``file:`` and other
#: local schemes, turning a provider endpoint into a local file read.
_ALLOWED_ENDPOINT_SCHEMES = frozenset({"http", "https"})


def _require_http_endpoint(url: str) -> str:
    scheme = urllib.parse.urlparse(url).scheme.lower()
    if scheme not in _ALLOWED_ENDPOINT_SCHEMES:
        raise InvalidProviderConfiguration(
            f"provider endpoint must be http or https, got {scheme or 'no'} scheme: {url!r}"
        )
    return url


@dataclass
class ProviderResult:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    provider: str = "unknown"
    raw: dict[str, Any] = field(default_factory=dict)


class ChatProvider(Protocol):
    name: str

    def generate(
        self,
        *,
        messages: list[dict[str, str]],
        context: str,
        system: str,
        max_output_tokens: int,
        config: AdapterConfig,
    ) -> ProviderResult: ...


@dataclass
class MockChatProvider:
    """Deterministic. Records the assembled context the Adapter handed over."""

    name: str = "mock"
    calls: list[dict[str, Any]] = field(default_factory=list)
    reply: str | None = None

    def generate(
        self,
        *,
        messages: list[dict[str, str]],
        context: str,
        system: str,
        max_output_tokens: int,
        config: AdapterConfig,
    ) -> ProviderResult:
        payload = json.dumps(
            {"system": system, "messages": messages, "context": context},
            sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        )
        digest = format(zlib.crc32(payload.encode("utf-8")), "08x")
        text = self.reply or f"[mock:{digest}] {messages[-1]['content'][:80] if messages else ''}"
        t0 = time.perf_counter()
        result = ProviderResult(
            text=text,
            input_tokens=estimate_tokens(system) + estimate_tokens(context) + estimate_tokens(
                messages[-1]["content"] if messages else ""
            ),
            output_tokens=estimate_tokens(text),
            latency_ms=int((time.perf_counter() - t0) * 1000),
            provider=self.name,
            raw={"digest": digest, "max_output_tokens": max_output_tokens},
        )
        self.calls.append({
            "system": system,
            "messages": messages,
            "context": context,
            "max_output_tokens": max_output_tokens,
            "budget": config.model_context_budget,
        })
        return result


@dataclass
class UnavailableProvider:
    name: str = "unavailable"

    def generate(
        self,
        *,
        messages: list[dict[str, str]],
        context: str,
        system: str,
        max_output_tokens: int,
        config: AdapterConfig,
    ) -> ProviderResult:
        raise ProviderUnavailable("provider configured as unavailable")


@dataclass
class OllamaChatProvider:
    name: str = "ollama"

    def generate(
        self,
        *,
        messages: list[dict[str, str]],
        context: str,
        system: str,
        max_output_tokens: int,
        config: AdapterConfig,
    ) -> ProviderResult:
        user = messages[-1]["content"] if messages else ""
        prompt = f"{context}\n\nUser:\n{user}" if context else user
        body = {
            "model": config.model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "think": bool(config.think),
            "keep_alive": config.keep_alive,
            "options": {
                "temperature": config.temperature,
                "seed": config.seed,
                "num_predict": max_output_tokens,
                "num_ctx": config.num_ctx,
            },
        }
        req = urllib.request.Request(
            _require_http_endpoint(config.endpoint),
            data=json.dumps(body).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        t0 = time.perf_counter()
        try:
            # scheme validated by _require_http_endpoint above
            with urllib.request.urlopen(req, timeout=config.timeout_s) as resp:  # nosec B310
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise ProviderUnavailable(f"ollama unreachable: {e}") from e
        except TimeoutError as e:
            raise ProviderUnavailable("ollama timeout") from e
        wall = int((time.perf_counter() - t0) * 1000)
        text = data.get("response") or ""
        pec = int(data.get("prompt_eval_count") or 0)
        ecount = int(data.get("eval_count") or 0)
        return ProviderResult(
            text=text,
            input_tokens=pec or estimate_tokens(system + prompt),
            output_tokens=ecount or estimate_tokens(text),
            latency_ms=wall,
            provider=self.name,
            raw={"model": data.get("model", config.model), "done_reason": data.get("done_reason")},
        )


def ollama_available(endpoint: str, timeout_s: float = 2.0) -> bool:
    base = endpoint.rsplit("/api/", 1)[0]
    url = base + "/api/tags"
    try:
        req = urllib.request.Request(_require_http_endpoint(url), method="GET")
        # scheme validated by _require_http_endpoint above
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # nosec B310
            return resp.status == 200
    except Exception:
        return False


def make_provider(config: AdapterConfig) -> ChatProvider:
    if config.provider == "mock":
        return MockChatProvider()
    if config.provider == "ollama":
        return OllamaChatProvider()
    raise ProviderUnavailable(f"unknown provider {config.provider}")
