"""Knowledge Object as a projection (first product surface) — pure tests.

A `KnowledgeObjectProjection` is a **derived view**, never stored, keyed by `subject_id` (no
`object_id`). v1 = **Discovery** (`discover_objects`) + **Object View** (`project`), composing only the
proven derivations (object standing, coherence, governance, per-claim governed state, the certified
timeline) — recomputing nothing. Actions and content-compilation (#4b-C) are deferred.
"""

from __future__ import annotations

from types import SimpleNamespace

from prl.collectors import ConsultationAdapter, make_resolution
from prl.query.knowledge_object import KnowledgeObjectQuery, render_knowledge_object
from prl.types import Carrier, to_entry


def _consult(subject, claim_id, *, org=None):
    return ConsultationAdapter().to_act(
        subject_id=subject, answer="x", producer="openai:gpt-4o", agent_id="agent.architect",
        confidence=1.0, carrier=Carrier(provider="openai", model="gpt-4o"), propose=True,
        claim_id=claim_id, org_id=org)


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


def _res(claim, decision, agent):
    return make_resolution(target_claim_id=claim, decision=decision, agent_id=agent)


def _world():
    # Object "KO" (org.acme): claim-a accepted, claim-b rejected → divergent → object CONTESTED.
    # Object "CLEAN" (org.acme): claim-c accepted → aligned → object ACCEPTED.
    return [
        _item(_consult("KO", "claim-a", org="org.acme"), "c0"),
        _item(_consult("KO", "claim-b", org="org.acme"), "c1"),
        _item(_consult("CLEAN", "claim-c", org="org.acme"), "c2"),
        _item(_res("claim-a", "accepted", "mohamed.azizi"), "r0"),
        _item(_res("claim-b", "rejected", "mohamed.azizi"), "r1"),
        _item(_res("claim-c", "accepted", "mohamed.azizi"), "r2"),
    ]


def _q(items):
    return KnowledgeObjectQuery(None, None, _navigator=_MixedNav(items))


# ── Discovery ────────────────────────────────────────────────────────────────────────────────
def test_discovery_enumerates_and_summarizes():
    objs = _q(_world()).discover_objects()
    by_id = {o.subject_id: o for o in objs}
    assert set(by_id) == {"KO", "CLEAN"}                         # enumerates distinct objects
    assert by_id["KO"].object_standing == "contested" and by_id["KO"].coherence == "divergent"
    # object_standing (ADR-0012) maps divergent→contested; the governance POSTURE (G-1) is 'divergent'.
    assert by_id["KO"].n_claims == 2 and by_id["KO"].governance == "divergent"
    assert by_id["CLEAN"].object_standing == "accepted" and by_id["CLEAN"].coherence == "aligned"
    assert by_id["KO"].org_id == "org.acme"


def test_discovery_filters():
    q = _q(_world())
    assert {o.subject_id for o in q.discover_objects(contested=True)} == {"KO"}   # contested standing
    assert {o.subject_id for o in q.discover_objects(org_id="org.acme")} == {"KO", "CLEAN"}
    assert {o.subject_id for o in q.discover_objects(org_id="org.other")} == set()
    assert {o.subject_id for o in q.discover_objects(search="cle")} == {"CLEAN"}   # substring on id
    # a subject whose claims are #2-conflicted → surfaced by --conflicts
    conflict_world = [
        _item(_consult("X", "claim-x"), "c0"),
        _item(_res("claim-x", "accepted", "alice"), "r0"),
        _item(_res("claim-x", "rejected", "bob"), "r1"),
    ]
    assert {o.subject_id for o in _q(conflict_world).discover_objects(conflicts=True)} == {"X"}


# ── Object View (composition only) ────────────────────────────────────────────────────────────
def test_object_view_composes_proven_derivations():
    proj = _q(_world()).project("KO")
    assert proj.object_standing == "contested" and proj.coherence == "divergent"
    assert proj.governance == "divergent"       # G-1 posture (distinct vocabulary from object_standing)
    by_claim = {c.claim_id: c for c in proj.claims}
    assert by_claim["claim-a"].governed_standing == "accepted"   # governed == raw (not contested)
    assert by_claim["claim-b"].governed_standing == "rejected"
    # timeline: each claim's proposal + resolution(s), receipt-backed, nothing invented.
    kinds = {(t.claim_id, t.kind) for t in proj.timeline}
    assert ("claim-a", "proposal") in kinds and ("claim-a", "resolution") in kinds
    assert all(t.receipt.startswith("v1:") for t in proj.timeline if t.kind == "resolution")
    # render is a single page; no object_id anywhere.
    out = render_knowledge_object(proj)
    assert out.startswith("Knowledge Object — KO")
    assert "object standing: CONTESTED" in out and "governance:      DIVERGENT" in out


# ── it is a projection, not an entity: derived, no object_id, drop/rebuild identical ───────────
def test_projection_is_derived_no_entity():
    items = _world()
    first = _q(items).project("KO")
    assert _q(items).project("KO") == first                      # derived, never stored
    # keyed by subject_id; no object_id field anywhere on the projection.
    assert not hasattr(first, "object_id")
    assert "object_id" not in first.__dataclass_fields__
    # composition-only: object_standing equals the underlying SubjectStandingsQuery result.
    from prl.query.subject_read import SubjectStandingsQuery
    sv = SubjectStandingsQuery(None, None, _navigator=_MixedNav(items)).standings_of_subject("KO")
    assert first.object_standing == sv.object_standing and first.coherence == sv.coherence
