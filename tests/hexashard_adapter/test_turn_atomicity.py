"""Product Seam v0.1.1 — a turn that produces no response must not persist.

`Project.handle_turn` advances and persists state before a provider can be
called, because it is what builds the context to send. Two independent dogfoods
reproduced the consequence: a provider failure left the project looking as though
a conversation had happened.

The invariant these tests hold:

    project truth unchanged, conversational state unchanged, no epoch advance,
    the attempt still recorded, and a retry costs exactly one turn.

Observability is deliberately *not* rolled back: a failure that leaves no trace
is worse than one that leaves a metrics row.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from hexashard import Project
from hexashard_adapter import AdapterConfig, HexaShardAdapter, MockChatProvider
from hexashard_adapter.errors import (
    ContextBudgetExceeded,
    MalformedProviderResponse,
    ProviderUnavailable,
)
from hexashard_adapter.provider import ChatProvider

METRICS = "adapter_metrics.jsonl"


class Boom(ChatProvider):
    name = "boom"

    def generate(self, **kwargs):
        raise ProviderUnavailable("provider exploded")


class Malformed(ChatProvider):
    name = "malformed"

    def generate(self, **kwargs):
        return object()


def _project(tmp_path, *, sources: int = 8, budget: int = 6000):
    adapter = HexaShardAdapter.create(
        tmp_path / "p", name="atomic", mission="hold the line",
        config=AdapterConfig(provider="mock"), active_context_budget_tokens=budget,
    )
    for i in range(sources):
        adapter.add_source("note", f"N{i}",
                           f"Ground station GS-{i} elevation is {10 + i} degrees. " * 6)
    src = adapter.add_source("spec", "Budget", "The downlink budget is 6.1 TB.")
    adapter.pin("downlink", "6.1 TB", src.source_id, critical=True)
    adapter.project.state.add_open_question("Q1", "who handles Spain?")
    adapter.project.save()
    return adapter


def _truth(project) -> str:
    """Project truth: sources, pins, open questions."""
    return json.dumps({
        "sources": sorted((s.source_id, s.title, s.status.value, s.content)
                          for s in project.sources.all()),
        "pins": sorted((p.pin_id, p.key, p.value, p.source_ref, p.status.value)
                       for p in project.pins.all()),
        "questions": project.state.open_questions,
    }, sort_keys=True)


def _conversational(project) -> str:
    return json.dumps({
        "turn": project.state.turn,
        "epoch": project.state.epoch,
        "tokens": project.state.tokens(project.counter),
        "hints": list(project.state.retrieval_hints),
        "hex_refs": list(project.state.active_hex_refs),
        "decisions": list(project.state.recent_decisions),
    }, sort_keys=True)


def _state_bytes(root: Path) -> str:
    """Everything durable except observability."""
    h = hashlib.sha256()
    for f in sorted(root.rglob("*")):
        if f.is_file() and f.name not in (METRICS, "adapter_config.json"):
            h.update(str(f.relative_to(root)).encode())
            h.update(hashlib.sha256(f.read_bytes()).digest())
    return h.hexdigest()


# -- F1: the error surfaces -----------------------------------------------

def test_f1_provider_failure_raises_typed_error(tmp_path):
    adapter = _project(tmp_path)
    adapter.provider = Boom()
    with pytest.raises(ProviderUnavailable):
        adapter.chat("what is the downlink budget?")


# -- F2-F4: project truth is untouched ------------------------------------

def test_f2_f3_f4_project_truth_unchanged(tmp_path):
    adapter = _project(tmp_path)
    before = _truth(adapter.project)
    adapter.provider = Boom()
    for _ in range(3):
        with pytest.raises(ProviderUnavailable):
            adapter.chat("what is the downlink budget?")
    assert _truth(adapter.project) == before


# -- F5-F7: conversational state is untouched -----------------------------

def test_f5_turn_counter_unchanged(tmp_path):
    adapter = _project(tmp_path)
    turn = adapter.project.state.turn
    adapter.provider = Boom()
    with pytest.raises(ProviderUnavailable):
        adapter.chat("anything")
    assert adapter.project.state.turn == turn


def test_f6_active_state_unchanged(tmp_path):
    adapter = _project(tmp_path)
    before = _conversational(adapter.project)
    adapter.provider = Boom()
    with pytest.raises(ProviderUnavailable):
        adapter.chat("what is the downlink budget?")
    assert _conversational(adapter.project) == before


def test_f7_epoch_cannot_advance_because_of_a_failed_generation(tmp_path):
    """With a tiny budget a turn would rotate. A failed one must not."""
    adapter = _project(tmp_path, budget=260)
    epoch = adapter.project.state.epoch
    adapter.provider = Boom()
    for i in range(15):
        with pytest.raises(ProviderUnavailable):
            adapter.chat(f"what is the elevation of ground station GS-{i} on pass {i}?")
    assert adapter.project.state.epoch == epoch
    assert not list((adapter.project.root / "epochs").glob("*"))


# -- F8: persistence ------------------------------------------------------

def test_f8_durable_state_is_byte_identical_apart_from_observability(tmp_path):
    adapter = _project(tmp_path)
    before = _state_bytes(adapter.project.root)
    adapter.provider = Boom()
    with pytest.raises(ProviderUnavailable):
        adapter.chat("what is the downlink budget?")
    assert _state_bytes(adapter.project.root) == before


# -- F9: observability survives -------------------------------------------

def test_f9_failure_is_recorded_even_though_the_turn_is_rolled_back(tmp_path):
    adapter = _project(tmp_path)
    adapter.provider = Boom()
    with pytest.raises(ProviderUnavailable):
        adapter.chat("what is the downlink budget?")
    rows = [json.loads(x) for x in
            (adapter.project.root / METRICS).read_text().splitlines() if x.strip()]
    failures = [r for r in rows if r.get("outcome") == "failed"]
    assert len(failures) == 1
    assert failures[0]["error"] == "ProviderUnavailable"
    assert failures[0]["turn_rolled_back"] is True


# -- F10-F11: retry -------------------------------------------------------

def test_f10_f11_retry_succeeds_and_costs_exactly_one_turn(tmp_path):
    adapter = _project(tmp_path)
    turn = adapter.project.state.turn
    adapter.provider = Boom()
    for _ in range(4):
        with pytest.raises(ProviderUnavailable):
            adapter.chat("what is the downlink budget?")
    assert adapter.project.state.turn == turn

    adapter.provider = MockChatProvider(reply="6.1 TB.")
    result = adapter.chat("what is the downlink budget?")
    assert result.response_text
    assert adapter.project.state.turn == turn + 1


# -- F12: success is unchanged --------------------------------------------

def test_f12_successful_turn_behaviour_is_unchanged(tmp_path):
    """A success after failures must match a success with no failures at all."""
    clean = _project(tmp_path / "a")
    clean.provider = MockChatProvider(reply="6.1 TB.")
    good = clean.chat("what is the downlink budget?")

    dirty = _project(tmp_path / "b")
    dirty.provider = Boom()
    for _ in range(3):
        with pytest.raises(ProviderUnavailable):
            dirty.chat("what is the downlink budget?")
    dirty.provider = MockChatProvider(reply="6.1 TB.")
    after = dirty.chat("what is the downlink budget?")

    assert after.retrieved_source_ids == good.retrieved_source_ids
    assert after.total_context_tokens == good.total_context_tokens
    assert after.active_state_tokens == good.active_state_tokens
    assert after.retrieved_context_tokens == good.retrieved_context_tokens
    assert after.epoch == good.epoch
    assert after.turn == good.turn
    assert after.pin_warnings == good.pin_warnings
    assert _conversational(dirty.project) == _conversational(clean.project)


# -- F13: READ_ONLY -------------------------------------------------------

def test_f13_read_only_failure_remains_non_mutating(tmp_path):
    adapter = _project(tmp_path)
    adapter.close()
    adapter = HexaShardAdapter.open(
        tmp_path / "p", config=AdapterConfig(provider="mock", mode="READ_ONLY"))
    before_truth, before_conv = _truth(adapter.project), _conversational(adapter.project)
    adapter.provider = Boom()
    with pytest.raises(ProviderUnavailable):
        adapter.chat("what is the downlink budget?")
    assert _truth(adapter.project) == before_truth
    assert _conversational(adapter.project) == before_conv


# -- F14: no accumulation -------------------------------------------------

def test_f14_repeated_failures_do_not_accumulate_conversational_state(tmp_path):
    adapter = _project(tmp_path)
    before = _conversational(adapter.project)
    adapter.provider = Boom()
    for i in range(20):
        with pytest.raises(ProviderUnavailable):
            adapter.chat(f"a different question number {i} about ground stations")
    assert _conversational(adapter.project) == before


# -- F15: reload ----------------------------------------------------------

def test_f15_reload_after_failure_shows_clean_state(tmp_path):
    adapter = _project(tmp_path)
    before = _conversational(adapter.project)
    adapter.provider = Boom()
    for _ in range(3):
        with pytest.raises(ProviderUnavailable):
            adapter.chat("what is the downlink budget?")
    adapter.close()
    assert _conversational(Project.open(tmp_path / "p")) == before


# -- the other two failure shapes in the same window ----------------------

def test_malformed_provider_reply_also_rolls_back(tmp_path):
    adapter = _project(tmp_path)
    before = _conversational(adapter.project)
    adapter.provider = Malformed()
    with pytest.raises(MalformedProviderResponse):
        adapter.chat("what is the downlink budget?")
    assert _conversational(adapter.project) == before


def test_context_budget_failure_also_rolls_back(tmp_path):
    """Same window: state advanced, no response produced."""
    adapter = _project(tmp_path)
    before = _conversational(adapter.project)
    adapter.config.model_context_budget = 40
    adapter.config.provider_context_limit = 40
    with pytest.raises(ContextBudgetExceeded):
        adapter.chat("what is the downlink budget?")
    assert _conversational(adapter.project) == before


def test_rollback_survives_a_rotation_the_failed_turn_caused(tmp_path):
    """The failed turn's epoch artifacts must be removed, not merely ignored."""
    adapter = _project(tmp_path, budget=260)
    before = _conversational(adapter.project)
    adapter.provider = MockChatProvider(reply="ok")
    for i in range(30):
        adapter.chat(f"question {i} about ground station GS-{i % 8} on pass {i}")
    rotated_epoch = adapter.project.state.epoch
    assert rotated_epoch > 1, "test needs a rotation to have happened"
    artifacts = sorted(p.name for p in (adapter.project.root / "epochs").glob("*"))

    adapter.provider = Boom()
    for i in range(10):
        with pytest.raises(ProviderUnavailable):
            adapter.chat(f"another question {i} about ground station GS-{i}")
    assert adapter.project.state.epoch == rotated_epoch
    assert sorted(p.name for p in (adapter.project.root / "epochs").glob("*")) == artifacts
    assert before != _conversational(adapter.project)  # the successful turns did count
