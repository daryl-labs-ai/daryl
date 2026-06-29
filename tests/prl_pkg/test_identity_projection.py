"""Identity across projections v1 — pure tests (Second epoch #3).

Proves the existing identity model survives a second **registry projection**: the unchanged
StandingQuery / ExplainQuery run on the SQLite projection and produce the **identical**
result as on an RR-shaped projection — same claim_id, decisions, standing, explanation,
receipts. The kernel e2e (real Storage/RR vs SQLite) lives in test_consultation_store.py.
"""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from prl.collectors import ConsultationAdapter, make_resolution
from prl.projections.sqlite_projection import _SCHEMA, SqliteProjection
from prl.query.explain_read import ExplainQuery
from prl.query.standing_read import StandingQuery
from prl.types import to_entry


def _content(node):
    return to_entry(node, shard="prl_consultations", session_id="r").content


def _insert(conn, node, action, eid, receipt):
    conn.execute("INSERT INTO acts (entry_id, action_name, content, receipt) VALUES (?,?,?,?)",
                 (eid, action, _content(node), receipt))


def _entry(node, action, eid, receipt):
    return SimpleNamespace(id=eid, hash=receipt, content=_content(node),
                           metadata={"action_name": action})


class _RRStub:
    """A faithful RR-shaped RegistryProjection: navigate_action ascending; resolve_entries
    reversed (the real kernel does not preserve order)."""

    def __init__(self, items):  # items: list[(action, record, entry)] in authoritative order
        self._items = items

    def navigate_action(self, action_name, limit=None):
        return [r for (a, r, _e) in self._items if a == action_name]

    def resolve_entries(self, records, limit=None):
        ids = {r["entry_id"] for r in records}
        return list(reversed([e for (_a, r, e) in self._items if r["entry_id"] in ids]))


def _build_both(tmp_path, proposal, resolutions):
    """Return (sqlite_projection, rr_stub) holding the same acts."""
    db = str(tmp_path / "p.sqlite")
    conn = sqlite3.connect(db)
    conn.executescript(_SCHEMA)
    items = []
    if proposal is not None:
        node, eid, rec = proposal
        _insert(conn, node, "prl.consultation", eid, rec)
        items.append(("prl.consultation", {"entry_id": eid}, _entry(node, "prl.consultation", eid, rec)))
    for node, eid, rec in resolutions:
        _insert(conn, node, "prl.resolution", eid, rec)
        items.append(("prl.resolution", {"entry_id": eid}, _entry(node, "prl.resolution", eid, rec)))
    conn.commit()
    conn.close()
    return SqliteProjection(db), _RRStub(items)


def test_same_query_code_two_projections_identical(tmp_path):
    prop = ConsultationAdapter().to_act(
        subject_id="KO-7", answer="X", producer="openai:gpt-4o (consult-adapter v1)",
        agent_id="agent.test", confidence=0.7, propose=True)
    claim = prop.mef.claim_id
    a = make_resolution(target_claim_id=claim, decision="accepted", agent_id="mohamed.azizi")
    s = make_resolution(target_claim_id=claim, decision="superseded", agent_id="alex.doe")
    sql, rr = _build_both(
        tmp_path, (prop, "cP", "v1:cP"),
        [(a, "rA", "v1:rA"), (s, "rS", "v1:rS")])  # ascending

    # the SAME StandingQuery / ExplainQuery code on two projections → identical results
    assert StandingQuery(None, None, _navigator=sql).standing_of(claim) == \
           StandingQuery(None, None, _navigator=rr).standing_of(claim)
    assert ExplainQuery(None, None, _navigator=sql).explain(claim) == \
           ExplainQuery(None, None, _navigator=rr).explain(claim)

    sv = StandingQuery(None, None, _navigator=sql).standing_of(claim)
    assert sv.standing == "superseded" and sv.decisions == ("accepted", "superseded")
    assert sv.last_receipt == "v1:rS"  # latest-wins survived the projection
    e = ExplainQuery(None, None, _navigator=sql).explain(claim)
    assert e.proposal.receipt == "v1:cP"
    assert [r.receipt for r in e.resolutions] == ["v1:rA", "v1:rS"]
    assert e.claim_id == claim  # claim_id carried verbatim


def test_sqlite_projection_navigate_and_resolve(tmp_path):
    prop = ConsultationAdapter().to_act(subject_id="KO-7", answer="X", producer="p",
                                        agent_id="agent.test", confidence=0.5, propose=True)
    a = make_resolution(target_claim_id=prop.mef.claim_id, decision="accepted",
                        agent_id="mohamed.azizi")
    sql, _ = _build_both(tmp_path, (prop, "cP", "v1:cP"), [(a, "rA", "v1:rA")])

    recs = sql.navigate_action("prl.resolution")
    assert [r["entry_id"] for r in recs] == ["rA"]
    entries = sql.resolve_entries(recs)
    assert entries[0].id == "rA" and entries[0].hash == "v1:rA"
    assert entries[0].metadata["action_name"] == "prl.resolution"


def test_no_resolution_is_proposed_and_no_fabrication(tmp_path):
    prop = ConsultationAdapter().to_act(subject_id="KO-7", answer="X", producer="p",
                                        agent_id="agent.test", confidence=0.5, propose=True)
    claim = prop.mef.claim_id
    sql, rr = _build_both(tmp_path, (prop, "cP", "v1:cP"), [])
    assert StandingQuery(None, None, _navigator=sql).standing_of(claim).standing == "proposed"
    e = ExplainQuery(None, None, _navigator=sql).explain(claim)
    assert e.proposal is not None and e.resolutions == ()
    # a claim with neither proposal nor resolution: nothing fabricated
    assert ExplainQuery(None, None, _navigator=sql).explain("claim-unknown").proposal is None
