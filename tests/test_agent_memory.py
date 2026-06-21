import json
from pathlib import Path

import pytest

from dsm.core.storage import Storage
from dsm.memory import (
    DEFAULT_MEMORY_SHARD,
    MEMORY_SCHEMA_VERSION,
    explain_decision,
    record_decision,
    record_fact,
    record_hypothesis,
    record_inference,
)
from dsm.status import VerifyStatus
from dsm.verify import verify_shard


@pytest.fixture
def storage(tmp_path):
    return Storage(data_dir=str(tmp_path / "data"))


def _payload(entry):
    return json.loads(entry.content)


def test_record_fact_writes_fact_entry(storage):
    source = record_fact("DSM can provide a verifiable source entry.", storage=storage)
    source_ref = {"shard": source.shard, "entry_hash": source.hash}

    entry = record_fact(
        "The package imports dsm_primitives at runtime.",
        source_refs=[source_ref],
        confidence=0.9,
        session_id="s1",
        storage=storage,
    )

    payload = _payload(entry)
    assert payload["schema"] == MEMORY_SCHEMA_VERSION
    assert payload["schema_version"] == MEMORY_SCHEMA_VERSION
    assert payload["kind"] == "fact"
    assert payload["statement"] == "The package imports dsm_primitives at runtime."
    assert payload["source_refs"] == [source_ref]
    assert payload["confidence"] == 0.9
    assert entry.metadata["event_type"] == "agent_memory"
    assert entry.metadata["memory_kind"] == "fact"

    stored = storage.read(DEFAULT_MEMORY_SHARD, limit=1)[0]
    assert stored.hash == entry.hash


def test_record_hypothesis_writes_hypothesis_entry(storage):
    entry = record_hypothesis(
        "The packaging risk may block a PyPI release.",
        confidence=0.6,
        storage=storage,
    )

    payload = _payload(entry)
    assert payload["kind"] == "hypothesis"
    assert payload["statement"] == "The packaging risk may block a PyPI release."
    assert entry.metadata["memory_kind"] == "hypothesis"


def test_record_inference_can_depend_on_fact_and_hypothesis(storage):
    fact = record_fact("Runtime import exists.", storage=storage)
    hypothesis = record_hypothesis("Release may fail without dependency.", storage=storage)

    inference = record_inference(
        "The release needs a dsm-primitives packaging decision.",
        depends_on=[fact.hash, hypothesis.hash],
        confidence=0.8,
        storage=storage,
    )

    payload = _payload(inference)
    assert payload["kind"] == "inference"
    assert payload["depends_on"] == [fact.hash, hypothesis.hash]
    assert inference.metadata["depends_on"] == [fact.hash, hypothesis.hash]


def test_record_decision_can_depend_on_inference(storage):
    fact = record_fact("Runtime import exists.", storage=storage)
    hypothesis = record_hypothesis("Release may fail without dependency.", storage=storage)
    inference = record_inference(
        "Open a release blocker ticket.",
        depends_on=[fact.hash, hypothesis.hash],
        storage=storage,
    )

    decision = record_decision(
        "Do not change packaging in P1; create a release blocker.",
        depends_on=[inference.hash],
        storage=storage,
    )

    payload = _payload(decision)
    assert payload["kind"] == "decision"
    assert payload["depends_on"] == [inference.hash]


def test_explain_decision_returns_minimal_chain(storage):
    fact = record_fact("DSM stores append-only entries.", storage=storage)
    hypothesis = record_hypothesis("The answer needs local trust caveat.", storage=storage)
    inference = record_inference(
        "The answer should cite DSM verification and local trust limits.",
        depends_on=[fact.hash, hypothesis.hash],
        storage=storage,
    )
    decision = record_decision(
        "Answer with a verifiable DSM-backed justification.",
        depends_on=[inference.hash],
        storage=storage,
    )

    explanation = explain_decision(decision.hash, storage=storage)

    assert explanation["decision"]["entry_hash"] == decision.hash
    assert explanation["decision"]["kind"] == "decision"
    assert [d["entry_hash"] for d in explanation["dependencies"]] == [inference.hash]
    assert explanation["dependency_map"][inference.hash][0]["entry_hash"] == fact.hash
    assert explanation["dependency_map"][inference.hash][1]["entry_hash"] == hypothesis.hash
    supporting_hashes = {e["entry_hash"] for e in explanation["supporting_entries"]}
    assert {fact.hash, hypothesis.hash, inference.hash}.issubset(supporting_hashes)
    assert explanation["missing_dependencies"] == []
    assert explanation["verification"]["hint"] == "dsm verify --shard agent_memory"

    verdict = verify_shard(storage, DEFAULT_MEMORY_SHARD)
    assert verdict["status"] == VerifyStatus.OK


def test_source_refs_must_be_verifiable_shard_entry_hash_refs(storage):
    fact = record_fact("DSM source reference target.", storage=storage)
    entry = record_hypothesis(
        "Hypothesis backed by a DSM entry ref.",
        source_refs=[{"shard": fact.shard, "entry_hash": fact.hash}],
        storage=storage,
    )
    payload = _payload(entry)
    assert payload["source_refs"] == [{"shard": fact.shard, "entry_hash": fact.hash}]

    with pytest.raises(ValueError, match="source_refs entries must be dicts"):
        record_fact("bad ref", source_refs=["free text"], storage=storage)
    with pytest.raises(ValueError, match="entry_hash"):
        record_fact("missing hash", source_refs=[{"shard": fact.shard}], storage=storage)


def test_confidence_must_be_between_zero_and_one(storage):
    assert _payload(record_fact("low", confidence=0.0, storage=storage))["confidence"] == 0.0
    assert _payload(record_fact("high", confidence=1.0, storage=storage))["confidence"] == 1.0

    with pytest.raises(ValueError, match="between 0.0 and 1.0"):
        record_fact("too high", confidence=1.5, storage=storage)
    with pytest.raises(ValueError, match="between 0.0 and 1.0"):
        record_fact("too low", confidence=-0.1, storage=storage)


def test_agent_memory_module_is_outside_kernel():
    import dsm.memory.agent_memory as agent_memory

    module_path = Path(agent_memory.__file__).as_posix()
    assert "/src/dsm/memory/" in module_path
    assert "/src/dsm/core/" not in module_path
