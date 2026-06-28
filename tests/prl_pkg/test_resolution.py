"""Resolution / Standing v1 (ADR-PRL-0008) — pure tests.

Resolution act building, ConsultationNode↔Entry round-trip, the agent-cannot-ratify
boundary, and standing *derivation* via a stub navigator (no DSM/kernel). The kernel
e2e (commit + RR derive + CLI resolve/standing) lives in test_consultation_store.py.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from prl.collectors import ConsultationAdapter, make_resolution
from prl.query.standing_read import StandingQuery, StandingView, render_standing
from prl.types import ResolutionNode, from_entry, to_entry


# --- make_resolution (human/witnessed act) ---------------------------------

def test_make_resolution_is_human_act():
    r = make_resolution(target_claim_id="claim-1", decision="accepted", producer="human:mohamed")
    assert isinstance(r, ResolutionNode)
    assert r.target_claim_id == "claim-1" and r.decision == "accepted"
    assert r.mef.producer == "human:mohamed" and r.mef.confidence == 1.0


def test_invalid_decision_refused():
    with pytest.raises(ValidationError):
        make_resolution(target_claim_id="c", decision="maybe", producer="human:x")  # type: ignore[arg-type]


def test_resolution_round_trips_with_action_name():
    r = make_resolution(target_claim_id="c", decision="rejected", producer="human:x")
    draft = to_entry(r, shard="prl_consultations", session_id="run")
    assert draft.metadata["action_name"] == "prl.resolution"
    assert from_entry(draft) == r


def test_agent_cannot_ratify():
    # No path from the agent/adapter to a Resolution — ratification is human-only.
    adapter = ConsultationAdapter()
    assert not hasattr(adapter, "resolve")
    assert not hasattr(adapter, "ratify")


# --- standing is DERIVED (stub navigator, no kernel) -----------------------

def _res_entry(node: ResolutionNode):
    draft = to_entry(node, shard="prl_consultations", session_id="r")
    return SimpleNamespace(id=node.resolution_id, metadata=draft.metadata,
                           content=draft.content, hash="v1:" + node.resolution_id)


class _Nav:
    """Faithful RR stub. ``navigate_action`` yields metadata records in append/ascending
    order; ``resolve_entries`` returns the resolved entries **reordered** — as the real
    kernel does when it regroups by shard. Standing derivation must join entries to
    records by id and replay in records order, so this reorder must not change the
    result (it would, if the code naively trusted resolve_entries order)."""

    def __init__(self, nodes: list[ResolutionNode]):
        self._records = [{"entry_id": n.resolution_id} for n in nodes]      # ascending
        self._entries = list(reversed([_res_entry(n) for n in nodes]))      # kernel reorders

    def navigate_action(self, action, limit=None):
        return self._records if action == "prl.resolution" else []

    def resolve_entries(self, records, limit=None):
        return self._entries


def test_standing_proposed_when_no_resolution():
    v = StandingQuery(None, None, _navigator=_Nav([])).standing_of("claim-X")
    assert v.standing == "proposed" and v.decisions == ()


def test_standing_accepted_from_one_resolution():
    r = make_resolution(target_claim_id="claim-A", decision="accepted", producer="human:x")
    v = StandingQuery(None, None, _navigator=_Nav([r])).standing_of("claim-A")
    assert v.standing == "accepted" and v.decisions == ("accepted",)
    assert v.last_receipt.startswith("v1:")


def test_standing_latest_wins_and_filters_by_claim():
    # Built in append order accepted → superseded; the stub hands them back reversed,
    # proving the derivation replays by record order (latest wins), not resolve order.
    a = make_resolution(target_claim_id="claim-A", decision="accepted", producer="human:x")
    s = make_resolution(target_claim_id="claim-A", decision="superseded", producer="human:x")
    other = make_resolution(target_claim_id="claim-B", decision="rejected", producer="human:x")
    nav = _Nav([a, s, other])
    v = StandingQuery(None, None, _navigator=nav).standing_of("claim-A")
    assert v.standing == "superseded"               # latest decision wins
    assert v.decisions == ("accepted", "superseded")  # claim-B's rejection excluded


def test_render_standing():
    assert "PROPOSED" in render_standing(StandingView("c", "proposed", (), ""))
    out = render_standing(StandingView("c", "accepted", ("accepted",), "v1:r"))
    assert "ACCEPTED" in out and "v1:r" in out
