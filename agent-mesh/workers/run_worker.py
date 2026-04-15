"""
workers/run_worker.py
---------------------
Entry point — reads env, builds backend, runs a GenericLLMWorker.

Usage::

    LLM_PROVIDER=openai LLM_API_KEY=sk-... LLM_MODEL=gpt-4o-mini python -m workers.run_worker
    LLM_PROVIDER=anthropic LLM_API_KEY=sk-ant-... python -m workers.run_worker
    LLM_PROVIDER=ollama LLM_MODEL=qwen2.5 python -m workers.run_worker
    LLM_PROVIDER=openai_compatible LLM_BASE_URL=https://openrouter.ai/api/v1 \
        LLM_API_KEY=or-... LLM_MODEL=anthropic/claude-3.5-sonnet python -m workers.run_worker
    LLM_PROVIDER=zhipu ZHIPU_API_KEY=... ZHIPU_MODEL=glm-4 python -m workers.run_worker
    LLM_PROVIDER=zhipu ZHIPU_API_KEY=... ZHIPU_MODEL=glm-code python -m workers.run_worker  # coding API
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Make `workers.*` importable when running as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from workers.generic_worker.worker import build_worker_from_env


# ── Provider-specific env var forwarding ────────────────────────────────────
#
# The generic env-based builder (`build_worker_from_env`) reads a flat set of
# LLM_* variables. Some providers ship their own conventionally-named env
# variables (Zhipu uses ZHIPU_API_KEY, ZHIPU_MODEL, ZHIPU_BASE_URL). For
# convenience, if LLM_PROVIDER selects such a provider and the provider-
# specific variables are set, we forward them into the LLM_* slots IFF the
# latter are unset. Never overwrite LLM_* — they stay authoritative.


def _forward_zhipu_env() -> None:
    """Copy ZHIPU_* → LLM_* for the generic builder, without overwriting."""
    mapping = {
        "ZHIPU_API_KEY": "LLM_API_KEY",
        "ZHIPU_MODEL": "LLM_MODEL",
        "ZHIPU_BASE_URL": "LLM_BASE_URL",
    }
    for src, dst in mapping.items():
        val = os.environ.get(src)
        if val and not os.environ.get(dst):
            os.environ[dst] = val


def _apply_env_shims() -> None:
    provider = (os.environ.get("LLM_PROVIDER") or "").lower()
    if provider == "zhipu":
        _forward_zhipu_env()


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
    )
    _apply_env_shims()
    worker = build_worker_from_env()
    worker.run()


if __name__ == "__main__":
    main()
