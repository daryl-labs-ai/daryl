"""Object referent (#4a) — `subject-standings` read-gather, pure tests.

The experiment (yours): #4a does **not** assume `subject_id` is a viable referent; it tests
whether `subject_id` can **reach the governed state** of all its claims, read-only, with **no
new identity**. The discipline: it **GATHERS** (subject → its claims → each claim's standing,
side by side), it does **NOT COMPILE** (no merge into one object standing). The four checks:
(1) spanning across producers, (2) reaching the governed layer, (3) gather ≠ compile,
(4) derived (drop/rebuild identical, no stored field).
"""

from __future__ import annotations

from types import SimpleNamespace

from prl.collectors import ConsultationAdapter, make_resolution
from prl.query.subject_read import SubjectStandingsQuery, SubjectStandingsView
from prl.types import Carrier, to_entry


def _consult(subject, claim_id, *, carrier="gpt-4o", propose=False, agent="agent.architect"):
    return ConsultationAdapter().to_act(
        subject_id=subject, answer="x", producer=f"openai:{carrier}", agent_id=agent,
        confidence=1.0, carrier=Carrier(provider="openai", model=carrier),
        propose=propose, claim_id=claim_id)


def _item(node, eid):
    d = to_entry(node, shard="prl_shard", session_id="r")
    action = d.metadata["action_name"]
    entry = SimpleNamespace(id=eid, hash="v1:" + eid, content=d.content, metadata=dict(d.metadata))
    return (eid, action, entry)


class _MixedNav:
    """Faithful shared RegistryProjection holding BOTH consultations and resolutions —
    `SubjectStandingsQuery` composes ConsultationQuery (prl.consultation) + StandingQuery
    (prl.resolution) over one navigator, so the fake must serve both action buckets."""

    def __init__(self, items):  # items: list[(eid, action, entry)] in record order
        self._items = items

    def navigate_action(self, action, limit=None):
        return [{"entry_id": eid} for eid, a, _e in self._items if a == action]

    def resolve_entries(self, records, limit=None):
        ids = {r["entry_id"] for r in records}
        return [e for _eid, _a, e in self._items if e.id in ids]


def _query(items):
    return SubjectStandingsQuery(None, None, _navigator=_MixedNav(items))


# ── Gate 1 — spanning across producers (the KO shape) ───────────────────────────────────────
def test_subject_spans_producers_observations_are_proposed():
    # subject "KO": 4 observations, 2 carriers, 4 distinct claim_ids, NO resolutions.
    items = [
        _item(_consult("KO", "claim-a", carrier="gpt-5"), "c0"),
        _item(_consult("KO", "claim-b", carrier="gpt-4o"), "c1"),
        _item(_consult("KO", "claim-c", carrier="gpt-5"), "c2"),
        _item(_consult("KO", "claim-d", carrier="gpt-4o"), "c3"),
        _item(_consult("OTHER", "claim-z", carrier="gpt-4o"), "c4"),  # decoy: must not leak
    ]
    view = _query(items).standings_of_subject("KO")
    assert isinstance(view, SubjectStandingsView) and view.subject_id == "KO"
    assert [c.claim_id for c in view.claims] == ["claim-a", "claim-b", "claim-c", "claim-d"]
    assert {c.carrier for c in view.claims} == {"openai:gpt-5", "openai:gpt-4o"}  # spans producers
    assert all(c.standing == "proposed" for c in view.claims)   # observations → ungoverned
    assert all(c.mode == "observation" for c in view.claims)


# ── Gate 2 — reaches the governed layer (subject → claim → resolution → standing) ────────────
def test_subject_reaches_governed_standing_mixed():
    items = [
        _item(_consult("S", "claim-p", propose=True), "c0"),   # proposal, will be resolved
        _item(_consult("S", "claim-q", propose=True), "c1"),   # proposal, left ungoverned
        _item(make_resolution(target_claim_id="claim-p", decision="accepted",
                              agent_id="mohamed.azizi"), "r0"),
    ]
    view = _query(items).standings_of_subject("S")
    by_claim = {c.claim_id: c for c in view.claims}
    assert by_claim["claim-p"].standing == "accepted"   # gather crossed into resolutions/standing
    assert by_claim["claim-q"].standing == "proposed"   # ungoverned claim, distinct
    assert by_claim["claim-p"].mode == "proposal"


# ── Gate 3 — gather ≠ compile (two opposite standings stay side by side) ─────────────────────
def test_gather_not_compile_opposite_standings_side_by_side():
    items = [
        _item(_consult("T", "claim-a", propose=True), "c0"),
        _item(_consult("T", "claim-b", propose=True), "c1"),
        _item(make_resolution(target_claim_id="claim-a", decision="accepted",
                              agent_id="mohamed.azizi"), "r0"),
        _item(make_resolution(target_claim_id="claim-b", decision="rejected",
                              agent_id="mohamed.azizi"), "r1"),
    ]
    view = _query(items).standings_of_subject("T")
    standings = {c.claim_id: c.standing for c in view.claims}
    assert standings == {"claim-a": "accepted", "claim-b": "rejected"}  # both, side by side
    assert len(view.claims) == 2
    # The view is a GATHER, not a compiled object: no single "object standing" field exists.
    assert not hasattr(view, "standing")

    # Per-claim conflict (#2) is inherited verbatim, never aggregated across claims:
    conflict_items = [
        _item(_consult("U", "claim-x", propose=True), "c0"),
        _item(make_resolution(target_claim_id="claim-x", decision="accepted", agent_id="alice"), "r0"),
        _item(make_resolution(target_claim_id="claim-x", decision="rejected", agent_id="bob"), "r1"),
    ]
    cview = _query(conflict_items).standings_of_subject("U")
    assert cview.claims[0].standing == "rejected" and cview.claims[0].conflict is True


# ── Gate 4 — derived: drop/rebuild identical, no stored field ────────────────────────────────
def test_gather_is_derived_drop_rebuild_identical():
    items = [
        _item(_consult("KO", "claim-a", carrier="gpt-5"), "c0"),
        _item(_consult("KO", "claim-b", carrier="gpt-4o"), "c1"),
        _item(make_resolution(target_claim_id="claim-b", decision="accepted",
                              agent_id="mohamed.azizi"), "r0"),
    ]
    first = _query(items).standings_of_subject("KO")
    second = _query(items).standings_of_subject("KO")   # rebuilt from the SAME acts
    assert first == second                               # derived; the gather was never stored

    # No write path on the query; the gather equals a fresh recomputation from the acts.
    q = _query(items)
    assert not hasattr(q, "set_standing") and not hasattr(q, "store")
    assert q.standings_of_subject("KO") == first
