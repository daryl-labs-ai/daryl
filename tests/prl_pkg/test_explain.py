"""R-explain v1 — "why this decision?" (pure tests).

ExplainQuery assembles the certified chain (Proposal facet + Resolution facts + derived
standing) over a faithful stub navigator that serves BOTH prl.consultation and
prl.resolution, and reorders resolve_entries (modeling the real kernel) so the test keeps
guarding ordering. The kernel e2e lives in test_consultation_store.py.
"""

from __future__ import annotations

from types import SimpleNamespace

from prl.collectors import ConsultationAdapter, make_resolution
from prl.query.explain_read import ExplainQuery, ProposalFact, render_explanation
from prl.types import to_entry


def _item(node, node_id: str):
    draft = to_entry(node, shard="prl_consultations", session_id="r")
    entry = SimpleNamespace(id=node_id, metadata=draft.metadata, content=draft.content,
                            hash="v1:" + node_id)
    return {"entry_id": node_id, "timestamp": node_id}, entry


def _consult_item(node):
    return _item(node, node.consultation_id)


def _res_item(node):
    return _item(node, node.resolution_id)


class _Nav:
    """Faithful stub serving both action axes; resolve_entries returns entries
    REVERSED (the real kernel does not preserve action_index order)."""

    def __init__(self, consultations=(), resolutions=()):
        self._c = list(consultations)
        self._r = list(resolutions)
        self._by_id = {e.id: e for _rec, e in (self._c + self._r)}

    def navigate_action(self, action, limit=None):
        if action == "prl.consultation":
            return [rec for rec, _e in self._c]
        if action == "prl.resolution":
            return [rec for rec, _e in self._r]
        return []

    def resolve_entries(self, records, limit=None):
        ids = [r["entry_id"] for r in records]
        return list(reversed([self._by_id[i] for i in ids if i in self._by_id]))


def _proposal(subject="KO-7", answer="X", producer="openai:gpt-4o (consult-adapter v1)"):
    node = ConsultationAdapter().to_act(subject_id=subject, answer=answer, producer=producer,
                                        confidence=0.7, propose=True)
    return node, node.mef.claim_id


def test_explain_full_chain():
    prop, claim = _proposal()
    res = make_resolution(target_claim_id=claim, decision="accepted", producer="human:mohamed")
    nav = _Nav(consultations=[_consult_item(prop)], resolutions=[_res_item(res)])
    e = ExplainQuery(None, None, _navigator=nav).explain(claim)

    assert isinstance(e.proposal, ProposalFact)
    assert e.proposal.producer == "openai:gpt-4o (consult-adapter v1)"
    assert e.proposal.receipt.startswith("v1:")
    assert len(e.resolutions) == 1
    assert e.resolutions[0].decision == "accepted"
    assert e.resolutions[0].resolver == "human:mohamed"
    assert e.resolutions[0].receipt.startswith("v1:")
    assert e.standing == "accepted"


def test_explain_no_proposal_is_not_fabricated():
    res = make_resolution(target_claim_id="claim-X", decision="accepted", producer="human:x")
    nav = _Nav(resolutions=[_res_item(res)])
    e = ExplainQuery(None, None, _navigator=nav).explain("claim-X")
    assert e.proposal is None
    assert len(e.resolutions) == 1 and e.standing == "accepted"
    assert "(none on chain)" in render_explanation(e)


def test_explain_no_resolution_is_proposed():
    prop, claim = _proposal()
    nav = _Nav(consultations=[_consult_item(prop)])
    e = ExplainQuery(None, None, _navigator=nav).explain(claim)
    assert e.proposal is not None
    assert e.resolutions == () and e.standing == "proposed"
    assert "PROPOSED (no resolution)" in render_explanation(e)


def test_explain_multi_resolution_lists_all_standing_is_latest():
    prop, claim = _proposal()
    a = make_resolution(target_claim_id=claim, decision="accepted", producer="human:a")
    s = make_resolution(target_claim_id=claim, decision="superseded", producer="human:b")
    nav = _Nav(consultations=[_consult_item(prop)],
               resolutions=[_res_item(a), _res_item(s)])  # ascending; resolve_entries reverses
    e = ExplainQuery(None, None, _navigator=nav).explain(claim)
    assert tuple(r.decision for r in e.resolutions) == ("accepted", "superseded")
    assert e.standing == "superseded"  # derived latest, not record[-?]


def test_explain_observation_is_not_a_proposal():
    # An Observation (mode != proposal) must NOT become a Proposal facet.
    obs = ConsultationAdapter().to_act(subject_id="KO-7", answer="X",
                                       producer="claude via adapter v1", confidence=0.6)
    nav = _Nav(consultations=[_consult_item(obs)])
    e = ExplainQuery(None, None, _navigator=nav).explain(obs.mef.claim_id)
    assert e.proposal is None


def test_render_has_receipt_on_every_meaningful_line():
    prop, claim = _proposal()
    res = make_resolution(target_claim_id=claim, decision="accepted", producer="human:mohamed")
    nav = _Nav(consultations=[_consult_item(prop)], resolutions=[_res_item(res)])
    out = render_explanation(ExplainQuery(None, None, _navigator=nav).explain(claim))
    assert out.startswith(f"why {claim} is ACCEPTED")
    assert out.count("receipt v1:") == 2  # proposal + resolution lines
    assert "standing   ACCEPTED (derived)" in out
