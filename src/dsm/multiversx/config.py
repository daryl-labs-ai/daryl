"""
Adapter configuration.

Backlog: V0-08.

Loads a TOML config file (default: ~/.dsm/multiversx/config.toml) and applies
environment variable overrides. Every flag value is captured at adapter init
and recorded in each `anchor_settled` entry's metadata so post-hoc audits
can reconstruct runtime state.

See SPEC §11 for the TOML layout.

Two flags matter most and must be explicitly settable:

    ANCHOR_REGIME:       "auto" | "andromeda" | "supernova"
    ANCHOR_SDK_SCHEMA:   "legacy_only" | "dual" | "new_only"

Invariants:
    - Defaults are the compatibility-safe values: regime="auto",
      schema="dual". Any production deployment during the transition window
      must run on the defaults unless deliberately overridden.
    - All timeouts are expressed in blocks, not milliseconds. Conversion
      to ms happens inside the watcher using the current regime's round
      duration.
    - Env vars override TOML values. TOML values override defaults.

Failure modes:
    - FileNotFoundError is swallowed (defaults are used).
    - Invalid TOML raises the stdlib tomllib.TOMLDecodeError.
    - Invalid field values raise pydantic.ValidationError.

Test file: tests/multiversx/test_config.py  (not in the mandatory skeleton
list; mark as scaffold if created).
"""
from __future__ import annotations

import copy
import os
import sys
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

AnchorRegimeFlag = Literal["auto", "andromeda", "supernova"]
SdkSchemaFlag = Literal["legacy_only", "dual", "new_only"]


class AdapterFlags(BaseModel):
    """Runtime flags controlling regime and schema behavior."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    anchor_regime: AnchorRegimeFlag = "auto"
    sdk_schema: SdkSchemaFlag = "dual"


class RetryConfig(BaseModel):
    """Timeouts expressed in block counts (multiplied by round duration at runtime)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    t1_timeout_blocks: int = Field(10, ge=1)
    t3_timeout_blocks: int = Field(20, ge=1)
    stuck_multiplier: int = Field(3, ge=1)
    max_submission_retries: int = Field(5, ge=0)


class WatcherConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ws_url: str = "wss://gateway.multiversx.com/hub/ws"
    reconnect_base_ms: int = Field(1000, ge=0)
    reconnect_max_ms: int = Field(60000, ge=0)
    polling_fallback_after_ms: int = Field(1800, ge=0)


class AdapterConfig(BaseModel):
    """Top-level adapter config, matching the TOML layout in SPEC §11."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    gateway_url: str = "https://gateway.multiversx.com"
    account_address: str = ""
    anchor_shards: list[str] = Field(default_factory=lambda: ["sessions"])
    flags: AdapterFlags = Field(default_factory=AdapterFlags)
    # mypy note: pydantic v2's stubs don't advertise `Field(10, ...)` as a
    # field-with-default, so constructing the model with no positional args
    # is flagged as missing-required-arg. The call is correct at runtime
    # (every inner field has a default via Field(value, ge=...)); the
    # call-arg ignore is narrow and carries this comment.
    retry: RetryConfig = Field(default_factory=lambda: RetryConfig())  # type: ignore[call-arg]
    watcher: WatcherConfig = Field(default_factory=lambda: WatcherConfig())  # type: ignore[call-arg]


def default_config_path() -> Path:
    """Default config file location.

    Honors XDG_CONFIG_HOME when set; else ~/.dsm/multiversx/config.toml.

    Test file: tests/multiversx/test_config.py (scaffold)
    """
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        base = Path(xdg) / "dsm" / "multiversx"
    else:
        base = Path.home() / ".dsm" / "multiversx"
    return base / "config.toml"


def load_config(path: Optional[Path] = None) -> AdapterConfig:
    """Load adapter config from TOML, apply env overrides, return AdapterConfig.

    Args:
        path: Path to the TOML file. If None, uses default_config_path().
            A missing file yields the defaults (no error).

    Returns:
        AdapterConfig populated from TOML + env overrides + defaults.

    Env overrides (SPEC §11):
        DSM_MVX_GATEWAY_URL             -> gateway_url
        DSM_MVX_ACCOUNT_ADDRESS         -> account_address
        DSM_MVX_ANCHOR_REGIME           -> flags.anchor_regime
        DSM_MVX_SDK_SCHEMA              -> flags.sdk_schema
        DSM_MVX_WS_URL                  -> watcher.ws_url

    Raises:
        tomllib.TOMLDecodeError: If the file exists but is malformed.
        pydantic.ValidationError: If values fail schema validation.

    Test file: tests/multiversx/test_config.py (scaffold)
    """
    target = path if path is not None else default_config_path()
    raw: dict[str, Any] = {}
    if target.exists():
        raw = tomllib.loads(target.read_text(encoding="utf-8"))
    overridden = env_overrides(raw)
    return AdapterConfig.model_validate(overridden)


def env_overrides(base: dict) -> dict:
    """Return `base` with DSM_MVX_* environment variables applied.

    Pure function for ease of testing. Does not read TOML.

    Test file: tests/multiversx/test_config.py (scaffold)
    """
    result = copy.deepcopy(base)
    mapping = {
        "DSM_MVX_GATEWAY_URL": ("gateway_url",),
        "DSM_MVX_ACCOUNT_ADDRESS": ("account_address",),
        "DSM_MVX_ANCHOR_REGIME": ("flags", "anchor_regime"),
        "DSM_MVX_SDK_SCHEMA": ("flags", "sdk_schema"),
        "DSM_MVX_WS_URL": ("watcher", "ws_url"),
    }
    for env_key, path in mapping.items():
        value = os.environ.get(env_key)
        if value is None:
            continue
        cursor = result
        for segment in path[:-1]:
            cursor = cursor.setdefault(segment, {})
            if not isinstance(cursor, dict):
                cursor = {}
                result[segment] = cursor
        cursor[path[-1]] = value
    return result


def flags_for_audit_entry(config: AdapterConfig) -> dict[str, str]:
    """Extract the flag values to embed in each anchor_settled entry's metadata.

    Returns a plain dict (not AdapterFlags) so it can be JSON-serialized
    into the DSM entry payload.

    Test file: tests/multiversx/test_config.py (scaffold)
    """
    return {
        "anchor_regime": config.flags.anchor_regime,
        "sdk_schema": config.flags.sdk_schema,
    }
