"""Knowledge Object as a projection (first product surface) — pure tests.

A `KnowledgeObjectProjection` is a **derived view**, never stored, keyed by `subject_id` (no
`object_id`). v1 = **Discovery** (`discover_objects`) + **Object View** (`project`), composing only the
proven derivations (object standing, coherence, governance, per-claim governed state, the certified
timeline) — recomputing nothing. Actions and content-compilation (#4b-C) are deferred.
"""

from __future__ import annotations

from types import SimpleNamespace

from prl.collectors import ConsultationAdapter, make_resolution
from prl.query.knowledge_object import (
    KnowledgeObjectQuery,
    object_reason,
    render_knowledge_object,
)
from prl.types import Carrier, to_entry


def _consult(subject, claim_id, *, org=None, propose=True, answer="x"):
    return ConsultationAdapter().to_act(
        subject_id=subject, answer=answer, producer="openai:gpt-4o", agent_id="agent.architect",
        confidence=1.0, carrier=Carrier(provider="openai", model="gpt-4o"), propose=propose,
        claim_id=claim_id, org_id=org)


def _obs(subject, claim_id, *, answer="noted"):
    return _consult(subject, claim_id, propose=False, answer=answer)


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


# ── Object search v1 — content + certified metadata (Knowledge Map, first cut) ──────────────────
def _search_world():
    # database.choice: PostgreSQL accepted (mohamed) / SQLite rejected (alice) + an observation.
    # auth.method (org.acme): OAuth2 accepted (bob).
    return [
        _item(_consult("database.choice", "db-a", answer="Use PostgreSQL"), "c0"),
        _item(_consult("database.choice", "db-b", answer="Use SQLite (simpler ops)"), "c1"),
        _item(_obs("database.choice", "db-o", answer="Team has prior Postgres experience"), "c2"),
        _item(_consult("auth.method", "au-a", answer="OAuth2 with PKCE", org="org.acme"), "c3"),
        _item(_res("db-a", "accepted", "mohamed.azizi"), "r0"),
        _item(_res("db-b", "rejected", "alice"), "r1"),
        _item(_res("au-a", "accepted", "bob"), "r2"),
    ]


def test_search_matches_raw_answer_not_only_id():
    res = _q(_search_world()).discover_objects(search="postgres")
    by = {o.subject_id: o for o in res}
    assert set(by) == {"database.choice"}                    # matched via answer, not subject_id
    assert "answer" in by["database.choice"].match_fields    # provenance names the field
    assert "postgres" in by["database.choice"].match_snippet.lower()


def test_search_matches_certified_metadata():
    q = _q(_search_world())
    # resolver agent (alice appears ONLY as a resolver — requires resolver indexing)
    assert {o.subject_id for o in q.discover_objects(search="alice")} == {"database.choice"}
    # org, claim_id, decision word
    assert {o.subject_id for o in q.discover_objects(search="org.acme")} == {"auth.method"}
    assert {o.subject_id for o in q.discover_objects(search="db-a")} == {"database.choice"}
    assert {o.subject_id for o in q.discover_objects(search="rejected")} == {"database.choice"}
    assert {o.subject_id for o in q.discover_objects(search="oauth")} == {"auth.method"}
    # a term in no field matches nothing
    assert q.discover_objects(search="zzz-nothing") == []


def test_search_composes_with_filters_and_names_provenance():
    q = _q(_search_world())
    # database.choice is divergent (accepted+rejected) → object contested; auth.method is not.
    assert {o.subject_id for o in q.discover_objects(search="use", contested=True)} == {"database.choice"}
    a = next(o for o in q.discover_objects(search="alice"))
    assert "agent" in a.match_fields                          # resolver surfaced under 'agent'
    # rows carry derived context: reason + last activity.
    assert a.reason and a.last_kind in {"observation", "proposal"} and a.last_agent


# ── Object View (composition only) ────────────────────────────────────────────────────────────
def test_object_view_composes_proven_derivations():
    proj = _q(_world()).project("KO")
    assert proj.object_standing == "contested" and proj.coherence == "divergent"
    assert proj.governance == "divergent"       # G-1 posture (distinct vocabulary from object_standing)
    by_claim = {c.claim_id: c for c in proj.claims}
    assert by_claim["claim-a"].governed_standing == "accepted"   # governed == raw (not contested)
    assert by_claim["claim-b"].governed_standing == "rejected"
    # history (decision-thread): each proposal act + its resolution(s), receipt-backed, nothing invented.
    kinds = {(t.claim_id, t.kind) for t in proj.timeline}
    assert ("claim-a", "proposal") in kinds and ("claim-a", "resolution") in kinds
    assert all(t.receipt.startswith("v1:") for t in proj.timeline if t.kind == "resolution")
    # decision-thread order: a proposal's resolution comes IMMEDIATELY after that proposal.
    seq = [(t.claim_id, t.kind) for t in proj.timeline]
    assert seq.index(("claim-a", "resolution")) == seq.index(("claim-a", "proposal")) + 1
    # render is a single page; no object_id anywhere.
    out = render_knowledge_object(proj)
    assert out.startswith("Knowledge Object — KO")
    # single story (status + human reason), signals subordinate.
    assert "status:  CONTESTED" in out
    assert "reason:  claims diverge" in out                     # the two vocabularies → one story
    assert "signals: coherence=divergent · governance=divergent" in out


# ── Object View v2 — five sections (decision navigation, O-001) ─────────────────────────────────
def test_object_view_v2_contested_shows_no_single_decision():
    out = render_knowledge_object(_q(_world()).project("KO"))
    # Current decision — a contested object NEVER fabricates a winner.
    assert "current decision:" in out
    assert "contested — no single governing decision" in out
    # Alternatives — both competing proposals appear, with governed state + raw answer.
    assert "alternatives:" in out
    assert "(accepted · claim-a" in out and "(rejected · claim-b" in out
    # the five section headers are present, in order.
    for header in ("current decision:", "alternatives:", "discussion:", "history:", "receipts:"):
        assert header in out
    assert out.index("current decision:") < out.index("alternatives:") < out.index("discussion:") \
        < out.index("history:") < out.index("receipts:")
    # History carries the honest ordering note; Receipts lists the certified acts.
    assert "ordered by consultation record" in out
    assert "v1:c0" in out and "v1:r0" in out


def test_object_view_v2_accepted_shows_current_decision():
    # single accepted proposal → the governing decision; no alternatives.
    out = render_knowledge_object(_q(_world()).project("CLEAN"))
    assert "✓ x   (claim-c" in out                              # accepted proposal = current decision
    # the accepted claim is NOT repeated as an alternative.
    assert out.split("alternatives:")[1].split("discussion:")[0].strip().startswith("(none)")


def test_object_view_v2_partitions_observations_into_discussion():
    # object M: one accepted PROPOSAL (p1) + one OBSERVATION (o1) — the observation is the discussion.
    world = [
        _item(_consult("M", "p1"), "c0"),
        _item(_obs("M", "o1", answer="prefer async here"), "c1"),
        _item(_res("p1", "accepted", "mohamed.azizi"), "r0"),
    ]
    proj = _q(world).project("M")
    # partition by mode: proposals → claims (decision space); observations → discussion.
    assert {c.claim_id for c in proj.claims} == {"p1"}
    assert {d.claim_id for d in proj.discussion} == {"o1"}
    assert proj.discussion[0].answer == "prefer async here"
    out = render_knowledge_object(proj)
    assert "“prefer async here”" in out                          # observation shown under Discussion
    # the observation is an act in History too, tagged observation.
    assert ("o1", "observation") in {(t.claim_id, t.kind) for t in proj.timeline}


def test_object_view_v2_no_observations_shows_empty_discussion():
    out = render_knowledge_object(_q(_world()).project("KO"))   # all proposals, no observations
    disc = out.split("discussion:")[1].split("history:")[0].strip()
    assert disc == "(none)"


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


# ── v1.1: reason narrative + recency uses AUTHORITATIVE record order ──────────────────────────
def test_object_reason_narrative():
    assert object_reason("contested", "divergent", False) == "claims diverge"
    assert object_reason("contested", "aligned", True) == "a constituent claim is contested"
    assert object_reason("accepted", "aligned", False) == "claims agree"
    assert object_reason("proposed", "unsettled", False) == "no governed claim yet"


class _ReorderNav(_MixedNav):
    """`navigate_action` keeps authoritative (ascending) record order; `resolve_entries` REVERSES it
    (as the real RR contract allows). A correct `discover_objects` must read recency from the records'
    order, never from the resolved order — the PR #77 trap."""

    def resolve_entries(self, records, limit=None):
        return list(reversed(super().resolve_entries(records)))


def test_discovery_recency_uses_record_order_not_resolve_order():
    # seed OLD first, RECENT last (record order); resolve_entries is reversed by the nav.
    items = [
        _item(_consult("old.demo", "o1"), "c0"),
        _item(_consult("recent.demo", "r1"), "c1"),
        _item(_res("o1", "accepted", "mohamed.azizi"), "r0"),
        _item(_res("r1", "accepted", "mohamed.azizi"), "r1r"),
    ]
    objs = KnowledgeObjectQuery(None, None, _navigator=_ReorderNav(items)).discover_objects()
    # recency-first must hold despite resolve_entries reversing — record order is authoritative.
    assert [o.subject_id for o in objs] == ["recent.demo", "old.demo"]
