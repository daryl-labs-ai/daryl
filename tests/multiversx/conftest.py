"""
Shared pytest fixtures for DSM × MultiversX adapter tests.

Fixtures are intentionally minimal at scaffold time. Real fixtures arrive
alongside implementation PRs.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def intent_id() -> uuid.UUID:
    """A deterministic UUIDv7 for test reproducibility.

    TODO[V0-01]: replace with a UUIDv7 generator once implementation lands.
    For now, a fixed v4 is acceptable for scaffold.
    """
    return uuid.UUID("00000000-0000-4000-8000-000000000001")


@pytest.fixture
def sample_last_hash() -> str:
    """A fixed 32-byte SHA-256 hash in 0x-hex form."""
    return "0x" + "ab" * 32


@pytest.fixture
def sample_shard_id() -> str:
    return "sessions"


@pytest.fixture
def andromeda_network_config() -> dict[str, Any]:
    """Sample /network/config response for pre-Supernova mainnet.

    Kept pared-down to the fields the adapter consults.
    """
    return {
        "erd_chain_id": "1",
        "erd_round_duration": 6000,
        "erd_latest_tag_software_version": "v1.10.0",
        "erd_num_shards_without_meta": 3,
        "erd_num_nodes_in_shard": 400,
        "erd_num_metachain_nodes": 400,
        "erd_min_gas_price": 1000000000,
        "erd_min_gas_limit": 50000,
    }


@pytest.fixture
def supernova_network_config() -> dict[str, Any]:
    """Sample /network/config response for post-Supernova mainnet."""
    return {
        "erd_chain_id": "1",
        "erd_round_duration": 600,
        "erd_latest_tag_software_version": "v2.0.0",
        "erd_num_shards_without_meta": 3,
        "erd_num_nodes_in_shard": 400,
        "erd_num_metachain_nodes": 400,
        "erd_min_gas_price": 1000000000,
        "erd_min_gas_limit": 50000,
    }


@pytest.fixture
def phase_a_network_config() -> dict[str, Any]:
    """Sample config during Supernova Phase A: ms timestamps but 6s rounds.

    This is the regime-detection edge case F10 guards against (SPEC §6).
    Regime MUST be "andromeda" here — the timestamp precision change
    alone does not flip the regime; only round_duration does.
    """
    return {
        "erd_chain_id": "1",
        "erd_round_duration": 6000,
        "erd_latest_tag_software_version": "v1.11.0-supernova-phase-a",
        "erd_num_shards_without_meta": 3,
        "erd_num_nodes_in_shard": 400,
        "erd_num_metachain_nodes": 400,
        "erd_min_gas_price": 1000000000,
        "erd_min_gas_limit": 50000,
    }


@pytest.fixture
def tmp_cache_path(tmp_path: Path) -> Path:
    """Per-test isolated regime cache path."""
    return tmp_path / "regime_cache.json"
