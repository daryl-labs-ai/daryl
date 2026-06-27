"""P6 tests — collector framework + ChatGPT collector.

Pure: touches only prl + a tmp JSON fixture (faithful to the real backup schema).
No DSM/RR/Storage.
"""

from __future__ import annotations

import json

import pytest

from prl.collectors import (
    ChatGPTCollector,
    Collector,
    FullTextSource,
    get_collector,
    list_collectors,
)
from prl.collectors.base import CollectorError
from prl.types import SessionNode, from_entry, to_entry

_FIXTURE = {
    "conversations": {
        "conv-1": {
            "title": "Daryl strategy",
            "gizmo_id": "g-abc",
            "messages": [
                {"role": "user", "text": "how to monetize Daryl?", "t": 1_700_000_000},
                {"role": "assistant", "text": "sell it as an AI decision audit", "t": 1_700_000_050},
            ],
        },
        "conv-2": {"title": "Empty-ish", "messages": []},
    }
}


def _write(tmp_path, data) -> str:
    p = tmp_path / "export.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


# --- registry --------------------------------------------------------------


def test_registry_has_chatgpt():
    assert "chatgpt" in list_collectors()
    assert get_collector("chatgpt") is ChatGPTCollector


def test_get_unknown_collector_raises():
    with pytest.raises(CollectorError):
        get_collector("nope")


def test_chatgpt_satisfies_protocol(tmp_path):
    assert isinstance(ChatGPTCollector(_write(tmp_path, _FIXTURE)), Collector)


# --- parsing ---------------------------------------------------------------


def test_collect_maps_fields(tmp_path):
    nodes = ChatGPTCollector(_write(tmp_path, _FIXTURE)).collect()
    by_id = {n.session_id: n for n in nodes}
    assert set(by_id) == {"conv-1", "conv-2"}

    c1 = by_id["conv-1"]
    assert c1.tool == "chatgpt"
    assert c1.title == "Daryl strategy"
    assert c1.started_ms == 1_700_000_000_000
    assert c1.ended_ms == 1_700_000_050_000
    # transcript-style preview includes role prefixes, chronological order
    assert c1.text_preview.startswith("user: how to monetize Daryl?")
    assert "assistant: sell it as an AI decision audit" in c1.text_preview
    assert c1.project_id is None  # bound in P7


def test_messages_sorted_by_timestamp(tmp_path):
    data = {"conversations": {"c": {"title": "t", "messages": [
        {"role": "assistant", "text": "second", "t": 200},
        {"role": "user", "text": "first", "t": 100},
    ]}}}
    node = ChatGPTCollector(_write(tmp_path, data)).collect()[0]
    assert node.started_ms == 100_000
    assert node.ended_ms == 200_000
    assert node.text_preview.index("first") < node.text_preview.index("second")


def test_empty_messages_defaults(tmp_path):
    c2 = {n.session_id: n for n in ChatGPTCollector(_write(tmp_path, _FIXTURE)).collect()}["conv-2"]
    assert c2.started_ms == 0
    assert c2.ended_ms is None
    assert c2.text_preview == ""


def test_bare_map_without_wrapper(tmp_path):
    nodes = ChatGPTCollector(_write(tmp_path, _FIXTURE["conversations"])).collect()
    assert {n.session_id for n in nodes} == {"conv-1", "conv-2"}


def test_malformed_entry_skipped(tmp_path):
    data = {"conversations": {"ok": {"title": "t", "messages": []}, "bad": "not-a-dict"}}
    nodes = ChatGPTCollector(_write(tmp_path, data)).collect()
    assert {n.session_id for n in nodes} == {"ok"}


def test_missing_timestamps(tmp_path):
    data = {"conversations": {"c": {"title": "t", "messages": [{"role": "user", "text": "hi", "t": None}]}}}
    node = ChatGPTCollector(_write(tmp_path, data)).collect()[0]
    assert node.started_ms == 0
    assert node.ended_ms is None
    assert node.text_preview == "user: hi"


def test_bad_path_raises(tmp_path):
    with pytest.raises(CollectorError):
        ChatGPTCollector(tmp_path / "missing.json").collect()


def test_bad_json_raises(tmp_path):
    p = tmp_path / "x.json"
    p.write_text("not json{", encoding="utf-8")
    with pytest.raises(CollectorError):
        ChatGPTCollector(str(p)).collect()


# --- full-text provider (Retrieval v2 / R1 — FullTextSource) ---------------


def test_chatgpt_satisfies_full_text_source(tmp_path):
    assert isinstance(ChatGPTCollector(_write(tmp_path, _FIXTURE)), FullTextSource)


def test_full_texts_untruncated_and_keyed_by_id(tmp_path):
    fulls = ChatGPTCollector(_write(tmp_path, _FIXTURE)).full_texts()
    # conv-1 present with full transcript; empty conv-2 omitted (no text)
    assert set(fulls) == {"conv-1"}
    assert fulls["conv-1"] == (
        "user: how to monetize Daryl? | assistant: sell it as an AI decision audit"
    )


def test_full_text_is_superset_of_preview(tmp_path):
    """The preview is exactly the first chars of the full text — same ordered
    transcript, so the P6 node stays consistent with the chunk source."""
    coll = ChatGPTCollector(_write(tmp_path, _FIXTURE))
    node = {n.session_id: n for n in coll.collect()}["conv-1"]
    full = coll.full_texts()["conv-1"]
    assert full.startswith(node.text_preview)


# --- DSM-readiness (collected sessions survive the Entry mapping) -----------


def test_collected_session_round_trips_through_entry(tmp_path):
    node = ChatGPTCollector(_write(tmp_path, _FIXTURE)).collect()[0]
    assert isinstance(node, SessionNode)
    draft = to_entry(node, shard="prl_test", session_id="run-1")
    assert draft.metadata["action_name"] == "prl.session"
    assert from_entry(draft) == node
