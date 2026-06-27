"""PRL configuration (P0).

``PRLConfig`` declares *which* project folders PRL is allowed to look at (D6:
declared folders only, never the whole machine) plus the knobs the later
milestones consume. P0 only defines the model and a JSON loader — no scan, no
DSM, no RR.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from .exceptions import PRLConfigError

_DEFAULT_CONFIG_PATH = Path.home() / ".daryl" / "prl" / "config.json"

_DEFAULT_EXTENSIONS: tuple[str, ...] = (
    ".md",
    ".txt",
    ".json",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".html",
    ".toml",
    ".yaml",
    ".yml",
)


class PRLConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    declared_projects: list[Path]  # D6 — declared folders only
    storage_dir: Path = Path.home() / ".daryl" / "prl"
    index_extensions: tuple[str, ...] = _DEFAULT_EXTENSIONS
    max_file_bytes: int = 2_000_000
    embedding_model: str = "local"  # D5 — local-first; "openai"/"voyage" optional
    embedding_local_name: str = "all-MiniLM-L6-v2"
    # Retrieval Policy v2.0 (ADR-PRL-0006) — frozen measured optima. Configurable,
    # but these are the ratified defaults, not knobs for re-exploration.
    retrieval_chunk_chars: int = 500
    retrieval_preview_gate: int = 10
    retrieval_rrf_k: int = 10

    @field_validator("declared_projects")
    @classmethod
    def _non_empty(cls, value: list[Path]) -> list[Path]:
        if not value:
            raise ValueError("declared_projects must not be empty")
        return value

    @classmethod
    def load(cls, path: Path | None = None) -> "PRLConfig":
        """Load a config from a JSON file.

        Reads a single config file — this is configuration, not a project scan.
        Raises :class:`PRLConfigError` on a missing file, malformed JSON, or a
        config that fails validation (including empty ``declared_projects``).
        """
        cfg_path = Path(path) if path is not None else _DEFAULT_CONFIG_PATH
        try:
            raw = cfg_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise PRLConfigError(f"cannot read config at {cfg_path}: {exc}") from exc
        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise PRLConfigError(f"config at {cfg_path} is not valid JSON: {exc}") from exc
        try:
            return cls(**data)
        except ValidationError as exc:
            raise PRLConfigError(f"invalid config at {cfg_path}: {exc}") from exc
