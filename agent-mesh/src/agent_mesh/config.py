"""Configuration loader for agent-mesh."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


# Defaults for the P0 anti-DoS guards (overridable via env).
DEFAULT_MAX_EVENT_BYTES = 1 * 1024 * 1024           # 1 MiB per event line
DEFAULT_MAX_LOG_BYTES = 2 * 1024 * 1024 * 1024       # 2 GiB events.jsonl ceiling
DEFAULT_MAX_RESULT_CONTENT_BYTES = 256 * 1024        # 256 KiB per task-result content


@dataclass
class Config:
    data_dir: Path
    server_id: str
    log_level: str
    # P0 hardening (C2/H7): authentication + write bounds.
    api_key: str | None = None
    app_env: str = "development"
    max_event_bytes: int = DEFAULT_MAX_EVENT_BYTES
    max_log_bytes: int = DEFAULT_MAX_LOG_BYTES
    max_result_content_bytes: int = DEFAULT_MAX_RESULT_CONTENT_BYTES

    @classmethod
    def load(cls, env_file: str | None = None) -> "Config":
        if env_file:
            load_dotenv(env_file, override=False)
        else:
            load_dotenv(override=False)
        data_dir = Path(os.environ.get("AGENT_MESH_DATA_DIR", "./data")).resolve()
        server_id = os.environ.get("AGENT_MESH_SERVER_ID", "server_main")
        log_level = os.environ.get("AGENT_MESH_LOG_LEVEL", "INFO")
        api_key = (os.environ.get("AGENT_MESH_API_KEY") or "").strip() or None
        app_env = os.environ.get("APP_ENV", "development").strip().lower()

        def _int_env(name: str, default: int) -> int:
            try:
                return int(os.environ[name])
            except (KeyError, ValueError):
                return default

        data_dir.mkdir(parents=True, exist_ok=True)
        return cls(
            data_dir=data_dir,
            server_id=server_id,
            log_level=log_level,
            api_key=api_key,
            app_env=app_env,
            max_event_bytes=_int_env("AGENT_MESH_MAX_EVENT_BYTES", DEFAULT_MAX_EVENT_BYTES),
            max_log_bytes=_int_env("AGENT_MESH_MAX_LOG_BYTES", DEFAULT_MAX_LOG_BYTES),
            max_result_content_bytes=_int_env(
                "AGENT_MESH_MAX_RESULT_CONTENT_BYTES", DEFAULT_MAX_RESULT_CONTENT_BYTES
            ),
        )
