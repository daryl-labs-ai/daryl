"""Configuration loader for agent-mesh."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class Config:
    data_dir: Path
    server_id: str
    log_level: str

    @classmethod
    def load(cls, env_file: str | None = None) -> "Config":
        if env_file:
            load_dotenv(env_file, override=False)
        else:
            load_dotenv(override=False)
        data_dir = Path(os.environ.get("AGENT_MESH_DATA_DIR", "./data")).resolve()
        server_id = os.environ.get("AGENT_MESH_SERVER_ID", "server_main")
        log_level = os.environ.get("AGENT_MESH_LOG_LEVEL", "INFO")
        data_dir.mkdir(parents=True, exist_ok=True)
        return cls(data_dir=data_dir, server_id=server_id, log_level=log_level)
