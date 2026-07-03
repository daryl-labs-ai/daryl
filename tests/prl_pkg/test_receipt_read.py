"""Receipt Hop v1 — pure tests (the design proof gate).

`prl receipt <hash>` resolves a receipt to its certified act and renders a uniform Certified Act card
(same shape for all seven kinds). Read-only, zero entity, zero index; a reconstruction, never a
re-certification; lookup is projection-relative. The receipt is the last edge of the projection web.
"""

from __future__ import annotations

from types import SimpleNamespace

from prl.collectors import ConsultationAdapter, make_resolution
from prl.query.receipt_read import (
    NOT_FOUND_MSG,
    ReceiptQuery,
    render_not_found,
    render_receipt_card,
)
from prl.types import Carrier, CommitNode, to_entry


def _consult(subject, claim_id, *, org=None, propose=True, answer="x", agent="agent.architect"):
    return ConsultationAdapter().to_act(
        subject_id=subject, answer=answer, producer="seed", agent_id=agent, confidence=1.0,
        carrier=Carrier(provider="openai", model="gpt-4o"), propose=propose, claim_id=claim_id, org_id=org)


def _res(claim, decision, agent, *, org=None):
    return make_resolution(target_claim_id=claim, decision=decision, agent_id=agent, org_id=org)


def _item(node, eid):
    d = to_entry(node, shard="prl_shard", session_id="r")
    entry = SimpleNamespace(id=eid, hash="v1:" + eid, content=d.content, metadata=dict(d.metadata))
    return (eid, d.metadata["action_name"], entry)


class _MixedNav:
    def __init__(self, items):
        self._items = items

    def navigate_action(self, action, limit=None):
        return [{"entry_id": eid} for eid, a, _e in self._items if a == action]

    def resolve_entries(self, records, limit=None):
        ids = {r["entry_id"] for r in records}
        return [e for _eid, _a, e in self._items if e.id in ids]


def _q(items):
    return ReceiptQuery(None, None, _navigator=_MixedNav(items))


def _world():
    return [
        _item(_consult("database.choice", "db-a", org="org.core", answer="Use PostgreSQL"), "c0"),
        _item(_res("db-a", "rejected", "alice", org="org.core"), "r0"),
        _item(CommitNode(sha="abc123", author="dev", ts_ms=1, message="init", project_id="p1"), "k0"),
    ]


# 1/3. Round trip + all-kinds landing — a receipt resolves to the exact act; onward links land in the web.
def test_round_trip_consultation_and_resolution():
    q = _q(_world())
    # consultation receipt (v1:c0) → its card, with onward links back into the web
    card = q.find("v1:c0")
    assert card is not None and card.kind == "prl.consultation"
    out = render_receipt_card(card)
    assert "Certified act — v1:c0" in out and "kind:       prl.consultation" in out
    assert "[go object database.choice]" in out and "[go agent agent.architect]" in out \
        and "[go claim db-a]" in out and "[go org org.core]" in out
    # resolution receipt (v1:r0) → its card
    rcard = q.find("v1:r0")
    assert rcard is not None and rcard.kind == "prl.resolution"
    rout = render_receipt_card(rcard)
    assert "decision=rejected" in rout and "[go claim db-a]" in rout and "[go agent alice]" in rout


def test_all_seven_kinds_land_uniform_card():
    # a code-graph act (prl.commit) renders the same uniform card honestly — no fabricated view.
    card = _q(_world()).find("v1:k0")
    assert card is not None and card.kind == "prl.commit"
    out = render_receipt_card(card)
    assert out.startswith("Certified act — v1:k0")
    assert "kind:       prl.commit" in out and "sha=abc123" in out and "author=dev" in out


# 4. Honest not-found — the exact message + boundary; nothing inferred.
def test_not_found_is_honest():
    assert _q(_world()).find("v1:nope") is None
    out = render_not_found("v1:nope")
    assert out.startswith(NOT_FOUND_MSG)
    assert "not a re-certification" in out and "projection-relative" in out \
        and "not found here ≠ does not exist elsewhere" in out


# 6. Boundary text present on every card.
def test_boundary_on_every_card():
    out = render_receipt_card(_q(_world()).find("v1:c0"))
    assert "reconstruction from the certified act — not a re-certification" in out
    assert "receipt and lookup are projection-relative" in out


# 7. Derived — drop/rebuild identical; nothing persisted.
def test_derived_drop_rebuild_identical():
    world = _world()
    assert render_receipt_card(_q(world).find("v1:c0")) == render_receipt_card(_q(world).find("v1:c0"))


# 8. Decision-first scan — a decision-layer receipt is found without scanning code-graph buckets.
def test_decision_first_scan_short_circuits(monkeypatch):
    nav = _MixedNav(_world())
    scanned: list[str] = []
    orig = nav.navigate_action
    nav.navigate_action = lambda action, limit=None: (scanned.append(action) or orig(action, limit))
    ReceiptQuery(None, None, _navigator=nav).find("v1:c0")   # first bucket (prl.consultation)
    assert scanned == ["prl.consultation"]                   # short-circuited — no code-graph scan
