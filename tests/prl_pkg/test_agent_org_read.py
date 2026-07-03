"""Agent / Org navigation views (v1) — pure tests (the 8-point design proof gate).

An ``AgentView`` / ``OrgView`` is a **derived projection** over the two decision-act streams
(``prl.consultation`` + ``prl.resolution``), never stored, keyed by an opaque ``agent_id`` / ``org_id``
string — no Agent/Org entity, no new field, no persisted index. The world below is the search-v1 world
extended with a **pre-0009 act** (no ``agent_id``) and a **cross-org resolution**.
"""

from __future__ import annotations

from types import SimpleNamespace

from prl.collectors import ConsultationAdapter, make_resolution
from prl.query.agent_org_read import (
    AgentOrgQuery,
    render_agent_view,
    render_org_view,
)
from prl.types import to_entry


def _consult(subject, claim_id, *, org=None, propose=True, answer="x", agent="agent.architect"):
    return ConsultationAdapter().to_act(
        subject_id=subject, answer=answer, producer="seed", agent_id=agent,
        confidence=1.0, propose=propose, claim_id=claim_id, org_id=org)


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
    return AgentOrgQuery(None, None, _navigator=_MixedNav(items))


def _world():
    # database.choice (org.core): PostgreSQL accepted (mohamed) / SQLite rejected (alice, resolver-only)
    #   + a cross-org supersession by carol (org.acme) → org.acme TOUCHES a org.core-owned object.
    # auth.method (org.acme): OAuth2 proposed by bob (bob is a proposer).
    # cache.strategy (org.core): Redis accepted (alice) / rejected (bob) → #2 contested claim.
    # legacy.thing (org.core): a pre-0009 proposal (agent_id None) → the 'unknown' bucket.
    return [
        _item(_consult("database.choice", "db-a", org="org.core", answer="Use PostgreSQL"), "c0"),
        _item(_consult("database.choice", "db-b", org="org.core", answer="Use SQLite"), "c1"),
        _item(_consult("auth.method", "au-a", org="org.acme", answer="OAuth2 with PKCE", agent="bob"), "c2"),
        _item(_consult("cache.strategy", "cc", org="org.core", answer="Use Redis"), "c3"),
        _item(_consult("legacy.thing", "lg", org="org.core", answer="Legacy decision", agent=None), "c4"),
        _item(_res("db-a", "accepted", "mohamed.azizi", org="org.core"), "r0"),
        _item(_res("db-b", "rejected", "alice", org="org.core"), "r1"),
        _item(_res("cc", "accepted", "alice", org="org.core"), "r2"),
        _item(_res("cc", "rejected", "bob", org="org.core"), "r3"),
        _item(_res("db-a", "superseded", "carol", org="org.acme"), "r4"),
    ]


# 1. Role split — roles never merged.
def test_role_split_contributed_vs_resolved():
    q = _q(_world())
    alice = q.agent("alice")                       # alice only resolves
    assert alice.proposed == () and alice.observed == ()          # empty Contributed
    assert {d for d, _ in alice.resolved} == {"accepted", "rejected"}   # populated Resolved
    bob = q.agent("bob")                           # bob proposed au-a AND resolved cc
    assert {r.subject_id for r in bob.proposed} == {"auth.method"}       # the converse
    assert {d for d, _ in bob.resolved} == {"rejected"}


# 2. 2-hop join — a resolution (no subject_id on it) surfaces the right object via claim→subject.
def test_two_hop_join_resolution_to_object():
    alice = _q(_world()).agent("alice")
    resolved = {d: {r.subject_id for r in rows} for d, rows in alice.resolved}
    assert resolved["rejected"] == {"database.choice"}   # db-b → database.choice (a multi-claim subject)
    assert resolved["accepted"] == {"cache.strategy"}    # cc → cache.strategy


# 3. Decision sub-buckets + contested flag (no invented decision value).
def test_decision_subbuckets_and_contested_flag():
    alice = _q(_world()).agent("alice")
    rows = {d: rows for d, rows in alice.resolved}
    cache_row = next(r for r in rows["accepted"] if r.subject_id == "cache.strategy")
    assert cache_row.contested is True                   # cc is #2-contested (alice acc vs bob rej)
    db_row = next(r for r in rows["rejected"] if r.subject_id == "database.choice")
    assert db_row.contested is False                     # db-b is not contested
    assert "⚠ contested" in render_agent_view(alice)


# 4. Owning vs touching — disjoint; the resolution org_id (dead until now) is used.
def test_org_owned_vs_touched_disjoint():
    q = _q(_world())
    acme = q.org("org.acme")
    owned = {r.subject_id for r in acme.owned}
    touched = {r.subject_id for r in acme.touched}
    assert owned == {"auth.method"}                      # org.acme owns auth.method
    assert touched == {"database.choice"}                # carol's org.acme resolution touches it
    assert owned.isdisjoint(touched)                     # disjoint by construction
    core = q.org("org.core")
    assert {r.subject_id for r in core.owned} == {"database.choice", "cache.strategy", "legacy.thing"}


# 5. Unknown bucket — a pre-0009 act appears under 'unknown', under no real agent.
def test_unknown_agent_bucket():
    q = _q(_world())
    unknown = q.agent("unknown")
    assert {r.subject_id for r in unknown.proposed} == {"legacy.thing"}
    assert unknown.is_unknown and "unknown / legacy agent" in render_agent_view(unknown)
    # the legacy act is never merged into a real agent
    assert all(r.subject_id != "legacy.thing" for r in q.agent("agent.architect").proposed)


# 6. Ordering — recency per stream inside a section; no global interleave claimed.
def test_recency_per_stream_ordering():
    arch = _q(_world()).agent("agent.architect")         # proposed db-a(0), db-b(1), cc(3)
    order = [r.subject_id for r in arch.proposed]
    assert order == ["cache.strategy", "database.choice"]   # cc (ord 3) before database.choice (ord 1)


# 7. Derived — drop/rebuild identical; no entity, no persisted state.
def test_derived_drop_rebuild_identical():
    world = _world()
    a1 = render_agent_view(_q(world).agent("alice"))
    a2 = render_agent_view(_q(world).agent("alice"))
    assert a1 == a2                                       # recomputed per call, identical
    assert render_org_view(_q(world).org("org.acme")) == render_org_view(_q(world).org("org.acme"))


# ── Agent→Org links (v1.1) — one derived edge from O-005 friction A ──────────────────────────────
def test_agent_org_edge_both_streams():
    q = _q(_world())
    # carol's ONLY org'd act is a resolution (resolution-only) → the edge still shows org.acme.
    assert q.agent("carol").orgs == ("org.acme",)
    # bob contributes in org.acme (consultation) AND resolves in org.core → both streams feed the edge.
    assert set(q.agent("bob").orgs) == {"org.acme", "org.core"}
    out = render_agent_view(q.agent("bob"))
    assert "orgs touched:" in out and "[go org org.acme]" in out and "[go org org.core]" in out


def test_agent_org_edge_empty_and_unknown():
    q = _q(_world())
    # an agent with no org'd acts → honest (none), never inferred.
    nobody = q.agent("nobody")
    assert nobody.orgs == () and "orgs touched:\n    (none)" in render_agent_view(nobody)
    # the unknown / legacy page gets the same section, same rules.
    assert "orgs touched:" in render_agent_view(q.agent("unknown"))


def test_agent_org_edge_noise_rule():
    out = render_agent_view(_q(_world()).agent("bob"))
    assert out.count("[go org org.acme]") == 1 and out.count("[go org org.core]") == 1
