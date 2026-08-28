"""Core identity and immutability under the Adapter.

In the lab this asserted that the Adapter never wrote inside a frozen Core tree
sitting on disk beside it.  In-repo the Core is an installed package, so the
same guarantee is expressed against the frozen per-module digests: the Core
running here must be byte-identical to the Core the published evidence was
produced against.
"""

from __future__ import annotations

import pytest

from hexashard_adapter import core_lock


def test_core_matches_frozen_v01_digests():
    assert core_lock.core_module_digests() == core_lock.FROZEN_CORE_MODULES


def test_assert_core_unmodified_passes():
    assert core_lock.assert_core_unmodified() == core_lock.FROZEN_CORE_MODULES


def test_assert_core_unmodified_detects_a_changed_module(monkeypatch):
    tampered = dict(core_lock.FROZEN_CORE_MODULES)
    tampered["project.py"] = "0" * 64
    monkeypatch.setattr(core_lock, "FROZEN_CORE_MODULES", tampered)
    with pytest.raises(RuntimeError, match="project.py"):
        core_lock.assert_core_unmodified()


def test_frozen_archive_digest_is_recorded():
    assert core_lock.ARCHIVE_SHA256 == (
        "268f0f08362982c2c6e85d5672d9f2e9efcc34f2e3306d40f5ee23e3763ca999"
    )


def test_adapter_run_does_not_mutate_core(tmp_path):
    from hexashard_adapter import HexaShardAdapter
    from hexashard_adapter.config import AdapterConfig

    before = core_lock.core_module_digests()
    adapter = HexaShardAdapter.create(
        tmp_path / "p", name="immutability", mission="m",
        config=AdapterConfig(provider="mock"),
    )
    source = adapter.add_source("spec", "Budget", "The budget is 6.1 TB.")
    adapter.pin("budget", "6.1 TB", source.source_id, critical=True)
    adapter.chat("what is the budget")
    adapter.close()
    assert core_lock.core_module_digests() == before
