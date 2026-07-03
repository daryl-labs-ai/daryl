"""Linked Projections v1 — pure tests (the design proof gate).

Typed link annotations (`[go <type> <id>]`) make the web of projections visible; the stateless
`prl go` dispatcher makes it actionable. Zero entity, zero index, zero state — annotations are display,
`go` composes the existing queries. Typing is by declaration, never inference.
"""

from __future__ import annotations

from types import SimpleNamespace

from prl.collectors import ConsultationAdapter, make_resolution
from prl.query.agent_org_read import AgentOrgQuery, render_agent_view, render_org_view
from prl.query.cli import main
from prl.query.explain_read import ExplainQuery, render_explanation
from prl.query.knowledge_object import KnowledgeObjectQuery, render_knowledge_object
from prl.query.links import LINK_TYPES, LinkAnnotator
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


def _obj(items):
    return KnowledgeObjectQuery(None, None, _navigator=_MixedNav(items))


def _ao(items):
    return AgentOrgQuery(None, None, _navigator=_MixedNav(items))


def _ex(items):
    return ExplainQuery(None, None, _navigator=_MixedNav(items))


def _world():
    # database.choice (org.core): PostgreSQL accepted (mohamed) / SQLite rejected (alice) → CONTESTED.
    # search.engine  (org.acme): Elasticsearch accepted (alice). Proposer: agent.architect throughout.
    return [
        _item(_consult("database.choice", "db-a", org="org.core", answer="Use PostgreSQL"), "c0"),
        _item(_consult("database.choice", "db-b", org="org.core", answer="Use SQLite"), "c1"),
        _item(_consult("search.engine", "se-a", org="org.acme", answer="Elasticsearch"), "c2"),
        _item(_res("db-a", "accepted", "mohamed.azizi"), "r0"),
        _item(_res("db-b", "rejected", "alice"), "r1"),
        _item(_res("se-a", "accepted", "alice"), "r2"),
    ]


# ── the annotator (noise rule) ──────────────────────────────────────────────────────────────────
def test_annotator_first_occurrence_only():
    a = LinkAnnotator()
    assert a.tag("agent", "alice") == "   [go agent alice]"
    assert a.tag("agent", "alice") == ""              # second occurrence bare (noise rule)
    assert a.tag("object", "alice") == "   [go object alice]"   # distinct (type, id) is a new link
    assert a.tag("agent", "") == ""                   # empty id never annotated (no landing)


# 2/3. The two display fixes + the object page's outward links.
def test_object_page_shows_org_and_agent_links():
    proj = _obj(_world()).project("database.choice")
    assert proj.org_id == "org.core"                  # object → org (the added view field)
    out = render_knowledge_object(proj)
    assert "org:     org.core   [go org org.core]" in out       # object → org hop, annotated
    assert "[go agent agent.architect]" in out                  # object → agent (proposer)
    assert "[go claim db-a]" in out                             # object → claim


def test_explain_page_shows_subject_and_agents():
    out = render_explanation(_ex(_world()).explain("db-a"))
    assert "subject    database.choice   [go object database.choice]" in out   # claim → object (fix)
    assert "[go agent agent.architect]" in out and "[go agent mohamed.azizi]" in out
    # a claim with no proposal on the chain shows NO subject line (never inferred).
    bare = render_explanation(_ex(_world()).explain("no-such-claim"))
    assert "(none on chain)" in bare and "\n  subject" not in bare


# 2. The O-004 chain executes literally — each hop's target is printed on the previous page.
def test_o004_chain_executes():
    q_obj, q_ao = _obj(_world()), _ao(_world())
    # object database.choice → its page offers agent + org jumps
    dbc = render_knowledge_object(q_obj.project("database.choice"))
    assert "[go agent agent.architect]" in dbc and "[go org org.core]" in dbc
    # agent agent.architect → offers object jumps (to database.choice AND search.engine)
    arch = render_agent_view(q_ao.agent("agent.architect"))
    assert "[go object database.choice]" in arch and "[go object search.engine]" in arch
    # object search.engine → offers org.acme + the alice jump (alice resolved it → history)
    se = render_knowledge_object(q_obj.project("search.engine"))
    assert "[go org org.acme]" in se and "[go agent alice]" in se
    # org org.acme → offers the object jump; agent alice → offers object jumps (resolver-only)
    assert "[go object search.engine]" in render_org_view(q_ao.org("org.acme"))
    alice = render_agent_view(q_ao.agent("alice"))
    assert "[go object database.choice]" in alice and "[go object search.engine]" in alice


# 4. Typing by declaration — unknown type errors; a shared id lands per declared type only.
def test_typing_by_declaration():
    assert set(LINK_TYPES) == {"object", "agent", "org", "claim", "receipt"}
    assert main(["go", "bogus", "zzz"]) == 2          # unknown type → error (no storage touched)
    # "shared" exists as BOTH a subject and an agent_id; each type lands on its own renderer.
    shared = [
        _item(_consult("shared", "sc-a", org="org.x"), "c0"),              # subject "shared"
        _item(_consult("topic", "tc-a", org="org.x", agent="shared"), "c1"),  # agent "shared"
    ]
    assert render_knowledge_object(_obj(shared).project("shared")).startswith("Knowledge Object — shared")
    assert render_agent_view(_ao(shared).agent("shared")).startswith("Agent — shared")


# 5. Noise rule — each distinct id is annotated exactly once per page.
def test_noise_rule_one_annotation_per_id_per_page():
    out = render_knowledge_object(_obj(_world()).project("database.choice"))
    # agent.architect proposes both db-a and db-b and recurs across History — annotated once.
    assert out.count("[go agent agent.architect]") == 1
    assert out.count("[go org org.core]") == 1


# 6. Derived — drop/rebuild identical (annotations deterministic); no persistence.
def test_derived_drop_rebuild_identical():
    world = _world()
    assert render_knowledge_object(_obj(world).project("database.choice")) == \
        render_knowledge_object(_obj(world).project("database.choice"))
    assert render_agent_view(_ao(world).agent("alice")) == render_agent_view(_ao(world).agent("alice"))
