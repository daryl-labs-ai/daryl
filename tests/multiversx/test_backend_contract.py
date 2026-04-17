"""
Contract tests for MultiversXAnchorBackend (V0 scope).

Backlog: V0-06.

V0 scope: capability reporting, ABC conformance, factory smoke.
V1 scope (NotImplementedError for now): submit, watch, verify, reconcile.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest

from dsm.anchor_backend import AnchorBackend
from dsm.multiversx.backend import MultiversXAnchorBackend, build_backend_from_config
from dsm.multiversx.regime import (
    ANDROMEDA_ROUND_DURATION_MS,
    SUPERNOVA_ROUND_DURATION_MS,
    RegimeVerdict,
)


class StubRegimeDetector:
    """Returns a fixed RegimeVerdict; never touches the network."""

    def __init__(self, verdict: RegimeVerdict) -> None:
        self._verdict = verdict

    def current(self) -> RegimeVerdict:
        return self._verdict

    def refresh(self, *, strict: bool = False) -> RegimeVerdict:
        return self._verdict

    def on_epoch_transition(self) -> bool:
        return False


class DummySigner:
    def address(self) -> str:
        return "erd1test"

    def sign(self, tx_body: dict[str, Any]) -> Any:  # pragma: no cover — V1
        raise NotImplementedError


class DummyStorage:
    def append(self, entry: Any) -> None:  # pragma: no cover — V1
        pass


def _verdict(regime: str, round_ms: int) -> RegimeVerdict:
    return RegimeVerdict(
        regime=regime,  # type: ignore[arg-type]
        round_duration_ms=round_ms,
        chain_id="1",
        source="network_config",
        captured_at_ms=0,
        epoch_number=42,
    )


def _backend(verdict: RegimeVerdict) -> MultiversXAnchorBackend:
    return MultiversXAnchorBackend(
        gateway_url="https://stub.invalid",
        signer=DummySigner(),
        account_address="erd1test",
        storage=DummyStorage(),
        regime_detector=StubRegimeDetector(verdict),
    )


# ---------------------------------------------------------------------------


class TestBackendContract:
    def test_implements_anchor_backend_abc(self) -> None:
        backend = _backend(_verdict("supernova", SUPERNOVA_ROUND_DURATION_MS))
        assert isinstance(backend, AnchorBackend)

    def test_capabilities_andromeda(self) -> None:
        backend = _backend(_verdict("andromeda", ANDROMEDA_ROUND_DURATION_MS))
        caps = backend.capabilities()
        assert caps.regime == "andromeda"
        assert caps.supports_settlement_stage is True
        assert caps.estimated_t1_ms == 10 * ANDROMEDA_ROUND_DURATION_MS  # 60000
        assert caps.estimated_t3_ms == (10 + 20) * ANDROMEDA_ROUND_DURATION_MS
        assert caps.backend_name == "multiversx"

    def test_capabilities_supernova(self) -> None:
        backend = _backend(_verdict("supernova", SUPERNOVA_ROUND_DURATION_MS))
        caps = backend.capabilities()
        assert caps.regime == "supernova"
        assert caps.supports_settlement_stage is True
        assert caps.estimated_t1_ms == 10 * SUPERNOVA_ROUND_DURATION_MS  # 6000
        assert caps.estimated_t3_ms == (10 + 20) * SUPERNOVA_ROUND_DURATION_MS

    def test_supports_settlement_stage_always_true(self) -> None:
        andromeda = _backend(_verdict("andromeda", ANDROMEDA_ROUND_DURATION_MS))
        supernova = _backend(_verdict("supernova", SUPERNOVA_ROUND_DURATION_MS))
        assert andromeda.capabilities().supports_settlement_stage is True
        assert supernova.capabilities().supports_settlement_stage is True

    def test_current_regime(self) -> None:
        backend = _backend(_verdict("andromeda", ANDROMEDA_ROUND_DURATION_MS))
        assert backend.current_regime() == "andromeda"

    def test_submit_raises_not_implemented(self) -> None:
        """V0 scope guard: V1 will replace this."""
        from dsm.multiversx.schemas import AnchorIntent

        backend = _backend(_verdict("supernova", SUPERNOVA_ROUND_DURATION_MS))
        intent = AnchorIntent(
            intent_id=uuid.UUID("00000000-0000-4000-8000-000000000001"),
            shard_id="sessions",
            last_hash="0x" + "ab" * 32,
            entry_nonce=1,
            epoch_regime="supernova",
        )
        with pytest.raises(NotImplementedError):
            backend.submit(intent)

    def test_build_backend_from_config_smoke(self, tmp_path: Path) -> None:
        """Given a temp config file, the factory answers current_regime() without raising."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            'gateway_url = "https://stub.invalid"\n'
            'account_address = "erd1test"\n',
            encoding="utf-8",
        )
        backend = build_backend_from_config(
            config_path=config_file,
            signer=DummySigner(),
            storage=DummyStorage(),
        )
        # current_regime() must not raise even though the stub URL is unreachable;
        # the detector's fail-closed path returns "supernova".
        assert backend.current_regime() in ("andromeda", "supernova")
