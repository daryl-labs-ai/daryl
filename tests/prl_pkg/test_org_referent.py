"""Organization referent v1 (ADR-PRL-0010) — pure tests.

`org_id` is the owning organization: declared at the project (source of truth), carried on
owner-scoped acts (thin ownership context, **beside** the MEF), carrier-independent, optional
and never inferred. The candidate third leg of "identity is never defined by its carrier".
"""

from __future__ import annotations

from types import SimpleNamespace

from prl.collectors import ConsultationAdapter, make_resolution
from prl.types import MEF, ProjectNode, from_entry, to_entry


class _FakeClient:
    provider = "openai"

    def complete(self, prompt, *, model):
        return "native answer"


def _consult(org_id=None):
    return ConsultationAdapter().consult(
        _FakeClient(), subject_id="KO", prompt="p", model="gpt-4o",
        agent_id="agent.architect", org_id=org_id)


# --- the project declares its owner; org_id ∉ carrier ----------------------

def test_project_declares_org_not_derived_from_path():
    p1 = ProjectNode.from_root("/a/proj1", org_id="org.acme")
    p2 = ProjectNode.from_root("/b/proj2", org_id="org.acme")
    assert p1.org_id == p2.org_id == "org.acme"     # one owner …
    assert p1.project_id != p2.project_id           # … two carriers (path-derived project ids)
    assert p1.org_id not in (p1.project_id, p1.root_path)  # not equal to / derived from the carrier


def test_same_org_across_two_carriers():
    a = ConsultationAdapter()
    n1 = a.consult(_FakeClient(), subject_id="KO", prompt="p", model="gpt-4o",
                   agent_id="agent.architect", org_id="org.acme")
    n2 = a.consult(_FakeClient(), subject_id="KO", prompt="p", model="gpt-5",
                   agent_id="agent.architect", org_id="org.acme")
    assert n1.org_id == n2.org_id == "org.acme"     # owner identical across model/carrier change
    assert n1.mef.carrier != n2.mef.carrier         # carrier differs


# --- optional, not inferred; not in the MEF --------------------------------

def test_org_id_optional_and_never_inferred():
    assert _consult(org_id="org.acme").org_id == "org.acme"
    assert _consult().org_id is None                # absent → None, never fabricated
    assert make_resolution(target_claim_id="c", decision="accepted",
                           agent_id="mohamed.azizi", org_id="org.acme").org_id == "org.acme"
    assert make_resolution(target_claim_id="c", decision="accepted",
                           agent_id="mohamed.azizi").org_id is None


def test_org_id_is_beside_the_mef_not_in_it():
    node = _consult(org_id="org.acme")
    assert node.org_id == "org.acme"
    assert "org_id" not in MEF.model_fields           # ownership ≠ epistemic: not in the frame


# --- backward compatibility: byte-identity + round-trip --------------------

def test_org_less_node_is_byte_identical_and_round_trips():
    node0 = _consult()  # no org_id
    content0 = to_entry(node0, shard="s", session_id="r").content
    assert "org_id" not in content0                   # exclude_none → pre-0010 shape preserved
    assert from_entry(to_entry(node0, shard="s", session_id="r")).org_id is None

    node1 = _consult(org_id="org.acme")
    assert from_entry(to_entry(node1, shard="s", session_id="r")).org_id == "org.acme"


# --- owner-scoped query: the thing project_id alone cannot express ----------

class _Nav:
    def __init__(self, nodes):
        self._e = []
        for n in nodes:
            d = to_entry(n, shard="prl_consultations", session_id="r")
            self._e.append(SimpleNamespace(id=n.consultation_id, metadata=d.metadata,
                                           content=d.content, hash="v1:" + n.consultation_id))

    def navigate_action(self, action, limit=None):
        return [{"entry_id": e.id} for e in self._e] if action == "prl.consultation" else []

    def resolve_entries(self, records, limit=None):
        ids = {r["entry_id"] for r in records}
        return [e for e in self._e if e.id in ids]


def test_owner_scope_filter_returns_only_that_org():
    from prl.query.consultation_read import ConsultationQuery

    nx = _consult(org_id="org.acme")
    ny = _consult(org_id="org.other")
    nz = _consult()  # no org
    q = ConsultationQuery(None, None, _navigator=_Nav([nx, ny, nz]))
    acme = q.list(org_id="org.acme")
    assert [v.org_id for v in acme] == ["org.acme"]   # only org.acme, not org.other, not unknown
