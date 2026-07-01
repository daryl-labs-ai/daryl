"""Governed standing layer (ADR-PRL-0011) — pure tests.

The first governance *rule*: `raw_standing` stays latest-wins (the projection primitive);
`governed_standing` is the **authoritative reading** — `contested` when the claim is #2-contested
(derived from the conflict signal, NOT `MEF.contested`), else `= raw_standing`. The governed reading
is added **above** the projection, never into it.

The four gate cases (ADR-0011): (1) a contested claim reads `governed == contested` with `raw`
unchanged; (2) a non-contested claim reads `governed == raw`; (3) derived (drop/rebuild identical);
(4) #4b coherence is unaffected — it still reads raw.
"""

from __future__ import annotations

from types import SimpleNamespace

from prl.collectors import ConsultationAdapter, make_resolution
from prl.query.explain_read import ExplainQuery, render_explanation
from prl.query.standing_read import StandingQuery, derive_governed_standing, render_standing
from prl.query.subject_read import SubjectStandingsQuery
from prl.types import Carrier, to_entry


# ── pure derivation (ADR-0011) ───────────────────────────────────────────────────────────────
def test_derive_governed_standing_pure():
    assert derive_governed_standing("accepted", False) == "accepted"   # not contested → raw
    assert derive_governed_standing("rejected", False) == "rejected"
    assert derive_governed_standing("proposed", False) == "proposed"
    assert derive_governed_standing("rejected", True) == "contested"    # contested → governed value
    assert derive_governed_standing("accepted", True) == "contested"    # raw irrelevant when contested


# ── end-to-end via the queries ───────────────────────────────────────────────────────────────
def _consult(subject, claim_id):
    return ConsultationAdapter().to_act(
        subject_id=subject, answer="x", producer="openai:gpt-4o", agent_id="agent.architect",
        confidence=1.0, carrier=Carrier(provider="openai", model="gpt-4o"), propose=True,
        claim_id=claim_id)


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


def _contested_items(subject="S", claim="claim-x"):
    # alice accepts, bob rejects the SAME claim → #2 conflict; raw = latest (rejected).
    return [
        _item(_consult(subject, claim), "c0"),
        _item(make_resolution(target_claim_id=claim, decision="accepted", agent_id="alice"), "r0"),
        _item(make_resolution(target_claim_id=claim, decision="rejected", agent_id="bob"), "r1"),
    ]


# ── Gate 1 — contested claim: governed == contested, raw unchanged ───────────────────────────
def test_contested_claim_governed_contested_raw_unchanged():
    sq = StandingQuery(None, None, _navigator=_MixedNav(_contested_items()))
    v = sq.standing_of("claim-x")
    assert v.standing == "rejected"            # RAW = latest-wins, UNCHANGED
    assert v.conflict is True
    assert v.governed_standing == "contested"  # AUTHORITATIVE reading (ADR-0011)
    # render: headline is governed, raw shown in context.
    out = render_standing(v)
    assert "CONTESTED" in out and "raw REJECTED" in out


# ── Gate 2 — non-contested claim: governed == raw ────────────────────────────────────────────
def test_non_contested_claim_governed_equals_raw():
    items = [
        _item(_consult("S", "claim-a"), "c0"),
        _item(make_resolution(target_claim_id="claim-a", decision="accepted", agent_id="mohamed.azizi"), "r0"),
    ]
    v = StandingQuery(None, None, _navigator=_MixedNav(items)).standing_of("claim-a")
    assert v.standing == "accepted" and v.governed_standing == "accepted"   # coincide
    assert v.conflict is False
    out = render_standing(v)
    assert "ACCEPTED" in out and "raw " not in out   # no raw note when they coincide


# ── Gate 3 — derived: drop/rebuild identical; governed = f(raw, conflict) ─────────────────────
def test_governed_is_derived_drop_rebuild_identical():
    items = _contested_items()
    first = StandingQuery(None, None, _navigator=_MixedNav(items)).standing_of("claim-x")
    second = StandingQuery(None, None, _navigator=_MixedNav(items)).standing_of("claim-x")
    assert first == second                                   # derived, never stored
    assert first.governed_standing == derive_governed_standing(first.standing, first.conflict)
    # no stored governed field on the acts: the ResolutionNode carries no such thing.
    node = make_resolution(target_claim_id="claim-x", decision="rejected", agent_id="bob")
    assert not hasattr(node, "governed_standing")


# ── Gate 4 — #4b coherence unaffected: it still reads RAW ─────────────────────────────────────
def test_hashtag_4b_coherence_reads_raw_not_governed():
    # subject with a single contested claim → raw standing is 'rejected' (latest-wins).
    sub = SubjectStandingsQuery(None, None, _navigator=_MixedNav(_contested_items("KO", "claim-x")))
    view = sub.standings_of_subject("KO")
    # #4b's per-claim standing is the RAW standing, NOT the governed 'contested'.
    assert view.claims[0].standing == "rejected"     # raw, unchanged — no rewire
    assert view.claims[0].conflict is True
    # one live governed (rejected) claim ⇒ coherence 'aligned' (computed on raw, unaffected by ADR-0011).
    assert view.coherence == "aligned"


# ── explain shows BOTH governed and raw ──────────────────────────────────────────────────────
def test_explain_shows_both_governed_and_raw():
    e = ExplainQuery(None, None, _navigator=_MixedNav(_contested_items())).explain("claim-x")
    assert e.standing == "rejected" and e.governed_standing == "contested"
    out = render_explanation(e)
    assert "governed=CONTESTED" in out and "raw=REJECTED" in out
    assert out.startswith("why claim-x is CONTESTED")   # headline = governed (authoritative)
