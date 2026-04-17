"""
Regime detection: decide whether the MultiversX network is pre-Supernova
(andromeda) or post-Supernova (supernova).

Backlog: V0-04.

Decision rule (SPEC §2):

    erd_round_duration == 6000       -> andromeda
    erd_round_duration == 600        -> supernova
    erd_round_duration ∈ [601..5999] -> supernova  (partial cut-over; safer)
    erd_round_duration missing/error -> last_known OR supernova (fail-closed)

Fail-closed-to-supernova is deliberate. See SPEC §2.

Signals NOT used alone:
    - Timestamp precision (ms vs s) — during Phase A of Supernova rollout,
      ms timestamps coexist with 6 s rounds. Do not infer from timestamps.
    - `erd_chain_id` — identifies the network (mainnet/devnet/testnet), not
      the regime within a network.

Invariants:
    - Pure function for detection from a config dict.
    - Cache is keyed by (chain_id, current_epoch) and has a TTL equal to
      `erd_rounds_per_epoch * erd_round_duration_ms` — the length of one
      epoch. Caller queries once at startup, then on epoch transition.
    - Cache persists to disk (~/.dsm/multiversx/regime_cache.json) so cold
      starts after a crash re-use the last known regime rather than paying
      a network round-trip before any anchor can proceed.

Failure modes:
    - RegimeError: underlying network query fails AND no cached value exists.
    - PayloadError: malformed /network/config response.

Test file: tests/multiversx/test_regime_detection.py
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional, Protocol

from dsm.multiversx.errors import PayloadError, RegimeError
from dsm.multiversx.schemas import EpochRegime, NetworkConfigSnapshot

ANDROMEDA_ROUND_DURATION_MS: int = 6000
SUPERNOVA_ROUND_DURATION_MS: int = 600

_METACHAIN_SHARD_ID: int = 4294967295
_DEFAULT_ROUNDS_PER_EPOCH: int = 14400

_log = logging.getLogger("dsm.multiversx.regime")


@dataclass(frozen=True)
class RegimeVerdict:
    """Outcome of regime detection.

    `source` records which path was taken so the audit tool can distinguish
    a verdict derived from a fresh query from one derived from cache or from
    the fail-closed default.

    `epoch_number` — when non-None — is the erd_epoch_number observed at
    capture time; used by on_epoch_transition() to decide whether to refresh.
    """

    regime: EpochRegime
    round_duration_ms: int
    chain_id: str
    source: str  # one of: "network_config", "cache", "fail_closed_default"
    captured_at_ms: int
    epoch_number: Optional[int] = None


def _coerce_round_duration(value: Any) -> Optional[int]:
    """Coerce an arbitrary /network/config value to int; None on failure."""
    if value is None:
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def detect_regime(network_config: dict[str, Any]) -> EpochRegime:
    """Pure decision: given a /network/config response dict, return regime.

    Args:
        network_config: The value of `data.config` from GET /network/config.
            Expected keys include `erd_round_duration` (int, ms) and
            `erd_chain_id` (str).

    Returns:
        "andromeda" if erd_round_duration == 6000.
        "supernova" if erd_round_duration == 600, or in (600, 6000), or
            if erd_round_duration is missing/invalid (fail-closed).

    Raises:
        PayloadError: If `network_config` is not a dict.

    Invariants:
        - Pure function. No I/O. No side effects (logging excepted — warning
          emission on unexpected round durations is mandated by SPEC review).
        - Must accept both int and string representations of
          `erd_round_duration` (gateways have returned both historically).

    Test file: tests/multiversx/test_regime_detection.py
    """
    if not isinstance(network_config, dict):
        raise PayloadError(
            f"network_config must be a dict, got {type(network_config).__name__}"
        )

    raw = network_config.get("erd_round_duration")
    int_value = _coerce_round_duration(raw)
    chain_id = network_config.get("erd_chain_id", "")

    if int_value == ANDROMEDA_ROUND_DURATION_MS:
        return "andromeda"

    decided: EpochRegime = "supernova"
    if int_value not in (ANDROMEDA_ROUND_DURATION_MS, SUPERNOVA_ROUND_DURATION_MS):
        _log.warning(
            "unexpected erd_round_duration; fail-closed to supernova",
            extra={
                "value_observed": int_value,
                "chain_id": chain_id,
                "decided_regime": decided,
            },
        )
    return decided


def build_snapshot(
    network_config: dict[str, Any], captured_at_ms: int
) -> NetworkConfigSnapshot:
    """Build a NetworkConfigSnapshot for inclusion in AnchorIntent.

    Raises:
        PayloadError: If any required field is missing.

    Test file: tests/multiversx/test_regime_detection.py
    """
    if not isinstance(network_config, dict):
        raise PayloadError(
            f"network_config must be a dict, got {type(network_config).__name__}"
        )
    chain_id = network_config.get("erd_chain_id")
    if not chain_id:
        raise PayloadError("erd_chain_id missing from /network/config response")
    protocol_version = network_config.get("erd_latest_tag_software_version")
    if not protocol_version:
        raise PayloadError(
            "erd_latest_tag_software_version missing from /network/config response"
        )
    round_duration = _coerce_round_duration(network_config.get("erd_round_duration"))
    if round_duration is None or round_duration < 1:
        raise PayloadError(
            f"erd_round_duration missing or invalid: {network_config.get('erd_round_duration')!r}"
        )
    return NetworkConfigSnapshot(
        chain_id=str(chain_id),
        round_duration_ms=round_duration,
        protocol_version=str(protocol_version),
        captured_at_ms=captured_at_ms,
    )


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


class Clock(Protocol):
    """Minimal clock interface for testability."""

    def now_ms(self) -> int: ...


class _SystemClock:
    def now_ms(self) -> int:
        return int(time.time() * 1000)


@dataclass(frozen=True)
class _CachedVerdict:
    verdict: RegimeVerdict
    cached_at_ms: int
    ttl_ms: int

    def is_fresh(self, now_ms: int) -> bool:
        return (now_ms - self.cached_at_ms) < self.ttl_ms


def _cached_verdict_to_dict(entry: _CachedVerdict) -> dict[str, Any]:
    return {
        "verdict": asdict(entry.verdict),
        "cached_at_ms": entry.cached_at_ms,
        "ttl_ms": entry.ttl_ms,
    }


def _cached_verdict_from_dict(payload: dict[str, Any]) -> _CachedVerdict:
    v = payload["verdict"]
    return _CachedVerdict(
        verdict=RegimeVerdict(
            regime=v["regime"],
            round_duration_ms=v["round_duration_ms"],
            chain_id=v["chain_id"],
            source=v["source"],
            captured_at_ms=v["captured_at_ms"],
            epoch_number=v.get("epoch_number"),
        ),
        cached_at_ms=payload["cached_at_ms"],
        ttl_ms=payload["ttl_ms"],
    )


class RegimeCache:
    """Persistent TTL cache for the current RegimeVerdict.

    Persists to a JSON file at `cache_path`. Safe to construct with a path
    that doesn't exist yet. On load errors (corrupt file, permission error),
    the cache behaves as empty and logs a warning.
    """

    def __init__(self, cache_path: Path, clock: Optional[Clock] = None) -> None:
        self._path = cache_path
        self._clock = clock or _SystemClock()
        self._in_memory: Optional[_CachedVerdict] = None
        self._loaded_from_disk: bool = False

    def _load_from_disk(self) -> None:
        self._loaded_from_disk = True
        try:
            raw = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return
        except OSError as exc:
            _log.warning("regime cache read failed: %s", exc)
            return
        try:
            payload = json.loads(raw)
            self._in_memory = _cached_verdict_from_dict(payload)
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            _log.warning("regime cache corrupt; treating as empty: %s", exc)
            self._in_memory = None

    def get(self) -> Optional[RegimeVerdict]:
        """Return the cached verdict iff it is fresh. Never raises."""
        if not self._loaded_from_disk:
            self._load_from_disk()
        entry = self._in_memory
        if entry is None:
            return None
        if not entry.is_fresh(self._clock.now_ms()):
            return None
        return entry.verdict

    def get_stale(self) -> Optional[RegimeVerdict]:
        """Return the cached verdict regardless of TTL. Used for network-failure fallback."""
        if not self._loaded_from_disk:
            self._load_from_disk()
        return self._in_memory.verdict if self._in_memory else None

    def put(self, verdict: RegimeVerdict, ttl_ms: int) -> None:
        """Persist `verdict` with the given TTL. Atomic: temp file + fsync + replace."""
        entry = _CachedVerdict(
            verdict=verdict,
            cached_at_ms=self._clock.now_ms(),
            ttl_ms=ttl_ms,
        )
        self._in_memory = entry
        self._loaded_from_disk = True

        parent = self._path.parent
        try:
            parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            _log.warning("regime cache dir create failed: %s", exc)
            return

        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        payload = json.dumps(_cached_verdict_to_dict(entry)).encode("utf-8")
        try:
            fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                os.write(fd, payload)
                try:
                    os.fsync(fd)
                except OSError as exc:
                    _log.warning("regime cache fsync failed (best-effort): %s", exc)
            finally:
                os.close(fd)
            os.replace(tmp_path, self._path)
        except OSError as exc:
            _log.warning("regime cache write failed: %s", exc)
            try:
                tmp_path.unlink()
            except OSError:
                pass

    def invalidate(self) -> None:
        """Drop the cached verdict (memory + disk). Ignore FileNotFoundError."""
        self._in_memory = None
        self._loaded_from_disk = True
        try:
            self._path.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            _log.warning("regime cache unlink failed: %s", exc)


# ---------------------------------------------------------------------------
# RegimeDetector (ties cache + network config query)
# ---------------------------------------------------------------------------


class NetworkConfigFetcher(Protocol):
    """Minimal interface the detector needs from a GatewayClient."""

    def get_network_config(self) -> dict[str, Any]: ...
    def get_network_status(self, shard_id: int) -> dict[str, Any]: ...


def _ttl_from_config(network_config: dict[str, Any], round_duration_ms: int) -> int:
    rounds_per_epoch = _coerce_round_duration(
        network_config.get("erd_rounds_per_epoch")
    )
    if rounds_per_epoch is None or rounds_per_epoch < 1:
        rounds_per_epoch = _DEFAULT_ROUNDS_PER_EPOCH
    return rounds_per_epoch * max(round_duration_ms, 1)


def _verdict_from_config(
    network_config: dict[str, Any],
    *,
    source: str,
    now_ms: int,
    epoch_number: Optional[int] = None,
) -> RegimeVerdict:
    regime = detect_regime(network_config)
    round_duration = _coerce_round_duration(
        network_config.get("erd_round_duration")
    )
    if round_duration is None or round_duration < 1:
        round_duration = (
            ANDROMEDA_ROUND_DURATION_MS
            if regime == "andromeda"
            else SUPERNOVA_ROUND_DURATION_MS
        )
    chain_id = str(network_config.get("erd_chain_id", ""))
    return RegimeVerdict(
        regime=regime,
        round_duration_ms=round_duration,
        chain_id=chain_id,
        source=source,
        captured_at_ms=now_ms,
        epoch_number=epoch_number,
    )


class RegimeDetector:
    """High-level detector: queries the network, caches, handles failure."""

    def __init__(
        self,
        fetcher: NetworkConfigFetcher,
        cache: RegimeCache,
        clock: Optional[Clock] = None,
    ) -> None:
        self._fetcher = fetcher
        self._cache = cache
        self._clock = clock or _SystemClock()

    def _fail_closed(self, now_ms: int) -> RegimeVerdict:
        return RegimeVerdict(
            regime="supernova",
            round_duration_ms=SUPERNOVA_ROUND_DURATION_MS,
            chain_id="",
            source="fail_closed_default",
            captured_at_ms=now_ms,
        )

    def current(self) -> RegimeVerdict:
        """Return the current RegimeVerdict, using cache if fresh. Never raises."""
        fresh = self._cache.get()
        if fresh is not None:
            return fresh
        now_ms = self._clock.now_ms()
        try:
            config = self._fetcher.get_network_config()
            verdict = _verdict_from_config(
                config, source="network_config", now_ms=now_ms
            )
            self._cache.put(verdict, _ttl_from_config(config, verdict.round_duration_ms))
            return verdict
        except Exception as exc:  # noqa: BLE001 — current() is explicitly non-raising
            _log.warning("regime fetch failed; falling back: %s", exc)
            stale = self._cache.get_stale()
            if stale is not None:
                return RegimeVerdict(
                    regime=stale.regime,
                    round_duration_ms=stale.round_duration_ms,
                    chain_id=stale.chain_id,
                    source="cache",
                    captured_at_ms=stale.captured_at_ms,
                )
            return self._fail_closed(now_ms)

    def refresh(self, *, strict: bool = False) -> RegimeVerdict:
        """Force a network query and update the cache."""
        now_ms = self._clock.now_ms()
        try:
            config = self._fetcher.get_network_config()
        except Exception as exc:  # noqa: BLE001
            if strict:
                raise RegimeError(f"strict refresh failed: {exc}") from exc
            _log.warning("regime refresh failed; falling back: %s", exc)
            stale = self._cache.get_stale()
            if stale is not None:
                return RegimeVerdict(
                    regime=stale.regime,
                    round_duration_ms=stale.round_duration_ms,
                    chain_id=stale.chain_id,
                    source="cache",
                    captured_at_ms=stale.captured_at_ms,
                )
            return self._fail_closed(now_ms)
        verdict = _verdict_from_config(config, source="network_config", now_ms=now_ms)
        self._cache.put(verdict, _ttl_from_config(config, verdict.round_duration_ms))
        return verdict

    def on_epoch_transition(self) -> bool:
        """Refresh the cache if the metachain epoch has advanced. Returns True if refreshed.

        Flow: GET /network/status/{metachain} for erd_epoch_number; compare to
        the cached verdict's epoch; if different (or if no cached epoch is
        available), refresh via the network config and stamp the new verdict
        with the observed epoch.
        """
        try:
            status = self._fetcher.get_network_status(_METACHAIN_SHARD_ID)
        except Exception as exc:  # noqa: BLE001
            _log.warning("epoch check failed: %s", exc)
            return False
        current_epoch = _coerce_round_duration(status.get("erd_epoch_number"))
        if current_epoch is None:
            return False
        cached = self._cache.get() or self._cache.get_stale()
        cached_epoch = cached.epoch_number if cached is not None else None
        if cached_epoch is not None and cached_epoch == current_epoch:
            return False
        now_ms = self._clock.now_ms()
        try:
            config = self._fetcher.get_network_config()
        except Exception as exc:  # noqa: BLE001
            _log.warning("epoch refresh config fetch failed: %s", exc)
            return False
        verdict = _verdict_from_config(
            config,
            source="network_config",
            now_ms=now_ms,
            epoch_number=current_epoch,
        )
        self._cache.put(verdict, _ttl_from_config(config, verdict.round_duration_ms))
        return True


def default_cache_path() -> Path:
    """Default on-disk location for the regime cache.

    Follows XDG_CONFIG_HOME when set; else ~/.dsm/multiversx/regime_cache.json.
    Never raises; if directory creation fails, returns the path anyway.
    """
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        base = Path(xdg) / "dsm" / "multiversx"
    else:
        base = Path.home() / ".dsm" / "multiversx"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return base / "regime_cache.json"
