"""
Tests for regime detection.

Backlog: V0-04.

Acceptance criteria (from BACKLOG.md):
    - Table-driven: erd_round_duration ∈ {6000, 600, 3000, 0, None}.
    - Fail-closed-to-supernova verified explicitly.
    - Cache layer tested against a mock clock.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

import pytest

from dsm.multiversx.errors import PayloadError, RegimeError
from dsm.multiversx.regime import (
    ANDROMEDA_ROUND_DURATION_MS,
    SUPERNOVA_ROUND_DURATION_MS,
    Clock,
    RegimeCache,
    RegimeDetector,
    RegimeVerdict,
    build_snapshot,
    detect_regime,
)


class FakeClock:
    def __init__(self, start_ms: int = 1_000_000) -> None:
        self._now = start_ms

    def now_ms(self) -> int:
        return self._now

    def advance(self, ms: int) -> None:
        self._now += ms


class FakeFetcher:
    def __init__(
        self,
        configs: Optional[Iterable[dict[str, Any]]] = None,
        statuses: Optional[Iterable[dict[str, Any]]] = None,
        raise_on_config: Optional[Exception] = None,
    ) -> None:
        self._configs = list(configs) if configs else []
        self._statuses = list(statuses) if statuses else []
        self._raise_on_config = raise_on_config
        self.config_calls = 0
        self.status_calls = 0

    def get_network_config(self) -> dict[str, Any]:
        self.config_calls += 1
        if self._raise_on_config is not None:
            raise self._raise_on_config
        idx = min(self.config_calls - 1, len(self._configs) - 1)
        return dict(self._configs[idx])

    def get_network_status(self, shard_id: int) -> dict[str, Any]:
        self.status_calls += 1
        idx = min(self.status_calls - 1, len(self._statuses) - 1)
        return dict(self._statuses[idx])


# ---------------------------------------------------------------------------
# Pure detect_regime()
# ---------------------------------------------------------------------------


class TestDetectRegimePure:
    def test_6000_is_andromeda(self, andromeda_network_config) -> None:
        assert detect_regime(andromeda_network_config) == "andromeda"

    def test_600_is_supernova(self, supernova_network_config) -> None:
        assert detect_regime(supernova_network_config) == "supernova"

    def test_partial_cutover_is_supernova(self) -> None:
        cfg = {"erd_chain_id": "1", "erd_round_duration": 3000}
        assert detect_regime(cfg) == "supernova"

    def test_missing_field_is_supernova(self) -> None:
        cfg = {"erd_chain_id": "1"}
        assert detect_regime(cfg) == "supernova"

    def test_zero_is_supernova(self) -> None:
        cfg = {"erd_chain_id": "1", "erd_round_duration": 0}
        assert detect_regime(cfg) == "supernova"

    def test_string_value_is_coerced(self) -> None:
        cfg = {"erd_chain_id": "1", "erd_round_duration": "6000"}
        assert detect_regime(cfg) == "andromeda"

    def test_non_dict_input_raises(self) -> None:
        with pytest.raises(PayloadError):
            detect_regime(None)  # type: ignore[arg-type]
        with pytest.raises(PayloadError):
            detect_regime("not a dict")  # type: ignore[arg-type]

    def test_warning_on_unexpected_round_duration(self, caplog) -> None:
        """I8: WARNING emitted when round_duration ∉ {6000, 600}."""
        import logging as _logging

        with caplog.at_level(_logging.WARNING, logger="dsm.multiversx.regime"):
            detect_regime({"erd_chain_id": "1", "erd_round_duration": 3000})
        assert any(
            rec.name == "dsm.multiversx.regime" and rec.levelno == _logging.WARNING
            for rec in caplog.records
        )

    def test_no_warning_for_expected_values(self, caplog) -> None:
        import logging as _logging

        with caplog.at_level(_logging.WARNING, logger="dsm.multiversx.regime"):
            detect_regime({"erd_chain_id": "1", "erd_round_duration": 6000})
            detect_regime({"erd_chain_id": "1", "erd_round_duration": 600})
        warnings = [r for r in caplog.records if r.levelno == _logging.WARNING]
        assert warnings == []


class TestPhaseAEdgeCase:
    """F10 guard: ms timestamps with 6s rounds must stay andromeda."""

    def test_phase_a_is_andromeda(self, phase_a_network_config) -> None:
        assert detect_regime(phase_a_network_config) == "andromeda"


class TestBuildSnapshot:
    def test_happy_path(self, supernova_network_config) -> None:
        snap = build_snapshot(supernova_network_config, captured_at_ms=1234)
        assert snap.chain_id == "1"
        assert snap.round_duration_ms == 600
        assert snap.protocol_version == "v2.0.0"
        assert snap.captured_at_ms == 1234

    def test_missing_chain_id_raises(self) -> None:
        cfg = {
            "erd_round_duration": 6000,
            "erd_latest_tag_software_version": "v1.10.0",
        }
        with pytest.raises(PayloadError, match="erd_chain_id"):
            build_snapshot(cfg, captured_at_ms=1)

    def test_missing_protocol_version_raises(self) -> None:
        cfg = {"erd_chain_id": "1", "erd_round_duration": 600}
        with pytest.raises(PayloadError, match="erd_latest_tag_software_version"):
            build_snapshot(cfg, captured_at_ms=1)


# ---------------------------------------------------------------------------
# RegimeCache
# ---------------------------------------------------------------------------


def _verdict(regime: str = "andromeda", round_ms: int = 6000, epoch: int = 100) -> RegimeVerdict:
    return RegimeVerdict(
        regime=regime,  # type: ignore[arg-type]
        round_duration_ms=round_ms,
        chain_id="1",
        source="network_config",
        captured_at_ms=1_000_000,
        epoch_number=epoch,
    )


class TestRegimeCache:
    def test_fresh_cache_returned(self, tmp_cache_path) -> None:
        clock = FakeClock()
        cache = RegimeCache(tmp_cache_path, clock=clock)
        cache.put(_verdict(), ttl_ms=60_000)
        clock.advance(30_000)
        assert cache.get() is not None
        assert cache.get().regime == "andromeda"  # type: ignore[union-attr]

    def test_stale_cache_is_not_returned(self, tmp_cache_path) -> None:
        clock = FakeClock()
        cache = RegimeCache(tmp_cache_path, clock=clock)
        cache.put(_verdict(), ttl_ms=60_000)
        clock.advance(120_000)
        assert cache.get() is None

    def test_atomic_write(self, tmp_cache_path) -> None:
        """After put(), the cache file exists with no stray .tmp file."""
        cache = RegimeCache(tmp_cache_path, clock=FakeClock())
        cache.put(_verdict(), ttl_ms=60_000)
        assert tmp_cache_path.exists()
        assert not tmp_cache_path.with_suffix(tmp_cache_path.suffix + ".tmp").exists()
        # And a second cache instance can read it.
        reader = RegimeCache(tmp_cache_path, clock=FakeClock())
        reader_get = reader.get()
        assert reader_get is not None and reader_get.regime == "andromeda"

    def test_corrupt_cache_behaves_as_empty(self, tmp_cache_path) -> None:
        tmp_cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_cache_path.write_text("{ not valid json", encoding="utf-8")
        cache = RegimeCache(tmp_cache_path, clock=FakeClock())
        assert cache.get() is None

    def test_invalidate_removes_disk_file(self, tmp_cache_path) -> None:
        cache = RegimeCache(tmp_cache_path, clock=FakeClock())
        cache.put(_verdict(), ttl_ms=60_000)
        assert tmp_cache_path.exists()
        cache.invalidate()
        assert not tmp_cache_path.exists()
        assert cache.get() is None


# ---------------------------------------------------------------------------
# RegimeDetector orchestration
# ---------------------------------------------------------------------------


class TestRegimeDetectorOrchestration:
    def test_first_call_queries_network(
        self, tmp_cache_path, andromeda_network_config
    ) -> None:
        cache = RegimeCache(tmp_cache_path, clock=FakeClock())
        fetcher = FakeFetcher(configs=[andromeda_network_config])
        detector = RegimeDetector(fetcher, cache, clock=FakeClock())
        verdict = detector.current()
        assert fetcher.config_calls == 1
        assert verdict.regime == "andromeda"
        assert verdict.source == "network_config"

    def test_second_call_uses_cache(
        self, tmp_cache_path, andromeda_network_config
    ) -> None:
        clock = FakeClock()
        cache = RegimeCache(tmp_cache_path, clock=clock)
        fetcher = FakeFetcher(configs=[andromeda_network_config])
        detector = RegimeDetector(fetcher, cache, clock=clock)
        detector.current()
        detector.current()
        assert fetcher.config_calls == 1

    def test_network_failure_with_stale_cache(
        self, tmp_cache_path, andromeda_network_config
    ) -> None:
        clock = FakeClock()
        # First: successful cache population.
        good = FakeFetcher(configs=[andromeda_network_config])
        cache = RegimeCache(tmp_cache_path, clock=clock)
        RegimeDetector(good, cache, clock=clock).current()
        # Advance past TTL so cache is stale.
        clock.advance(10**12)
        # New detector whose fetcher always fails.
        bad = FakeFetcher(raise_on_config=RuntimeError("network down"))
        stale_detector = RegimeDetector(bad, cache, clock=clock)
        verdict = stale_detector.current()
        assert verdict.regime == "andromeda"
        assert verdict.source == "cache"

    def test_network_failure_with_empty_cache(self, tmp_cache_path) -> None:
        cache = RegimeCache(tmp_cache_path, clock=FakeClock())
        fetcher = FakeFetcher(raise_on_config=RuntimeError("network down"))
        detector = RegimeDetector(fetcher, cache, clock=FakeClock())
        verdict = detector.current()
        assert verdict.regime == "supernova"
        assert verdict.source == "fail_closed_default"

    def test_strict_refresh_raises_on_network_failure(self, tmp_cache_path) -> None:
        cache = RegimeCache(tmp_cache_path, clock=FakeClock())
        fetcher = FakeFetcher(raise_on_config=RuntimeError("network down"))
        detector = RegimeDetector(fetcher, cache, clock=FakeClock())
        with pytest.raises(RegimeError):
            detector.refresh(strict=True)


# ---------------------------------------------------------------------------
# Epoch transition handling
# ---------------------------------------------------------------------------


class TestEpochTransition:
    def test_no_change_returns_false(
        self, tmp_cache_path, andromeda_network_config
    ) -> None:
        clock = FakeClock()
        cache = RegimeCache(tmp_cache_path, clock=clock)
        fetcher = FakeFetcher(
            configs=[andromeda_network_config],
            statuses=[{"erd_epoch_number": 100}],
        )
        detector = RegimeDetector(fetcher, cache, clock=clock)
        # Prime cache with epoch=100.
        from dsm.multiversx.regime import _verdict_from_config, _ttl_from_config

        verdict = _verdict_from_config(
            andromeda_network_config,
            source="network_config",
            now_ms=clock.now_ms(),
            epoch_number=100,
        )
        cache.put(verdict, _ttl_from_config(andromeda_network_config, 6000))
        # Status reports same epoch.
        assert detector.on_epoch_transition() is False
        assert fetcher.config_calls == 0

    def test_epoch_change_triggers_refresh(
        self, tmp_cache_path, andromeda_network_config
    ) -> None:
        clock = FakeClock()
        cache = RegimeCache(tmp_cache_path, clock=clock)
        fetcher = FakeFetcher(
            configs=[andromeda_network_config],
            statuses=[{"erd_epoch_number": 101}],
        )
        detector = RegimeDetector(fetcher, cache, clock=clock)
        # Prime cache with epoch=100.
        from dsm.multiversx.regime import _verdict_from_config, _ttl_from_config

        verdict = _verdict_from_config(
            andromeda_network_config,
            source="network_config",
            now_ms=clock.now_ms(),
            epoch_number=100,
        )
        cache.put(verdict, _ttl_from_config(andromeda_network_config, 6000))
        # Now status says epoch=101 → refresh.
        assert detector.on_epoch_transition() is True
        assert fetcher.config_calls == 1

    def test_regime_change_across_epochs(
        self, tmp_cache_path, andromeda_network_config, supernova_network_config
    ) -> None:
        """Mainnet activation: epoch N (andromeda) → epoch N+1 (supernova)."""
        clock = FakeClock()
        cache = RegimeCache(tmp_cache_path, clock=clock)
        # Fetcher serves andromeda on first call, supernova on second.
        fetcher = FakeFetcher(
            configs=[andromeda_network_config, supernova_network_config],
            statuses=[{"erd_epoch_number": 101}],
        )
        detector = RegimeDetector(fetcher, cache, clock=clock)
        # Prime cache with epoch=100, andromeda config.
        from dsm.multiversx.regime import _verdict_from_config, _ttl_from_config

        andromeda_v = _verdict_from_config(
            andromeda_network_config,
            source="network_config",
            now_ms=clock.now_ms(),
            epoch_number=100,
        )
        cache.put(andromeda_v, _ttl_from_config(andromeda_network_config, 6000))
        # Epoch transition → refresh → serves supernova config on call #1 of
        # the fetcher's config stream (index 0), but we already consumed 0 via
        # the prime. So wire a fresh fetcher scenario: the `configs` list
        # above advances its index on each call, so the first get_network_config()
        # returns andromeda_network_config. To test the activation, we instead
        # prime without touching the fetcher, then trigger refresh which will
        # call get_network_config once — expected to return andromeda on index
        # 0. That doesn't match the activation scenario, so re-prime via a
        # supernova-only fetcher after the first epoch.
        fetcher_after = FakeFetcher(
            configs=[supernova_network_config],
            statuses=[{"erd_epoch_number": 101}],
        )
        detector_after = RegimeDetector(fetcher_after, cache, clock=clock)
        assert detector_after.on_epoch_transition() is True
        assert detector_after.current().regime == "supernova"
