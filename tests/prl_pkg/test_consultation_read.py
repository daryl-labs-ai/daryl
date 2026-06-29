"""R-consult v2 (ADR-PRL-0008) — pure read/display tests.

Uses an injected stub navigator + fake Entry objects, so the read logic and the
display are tested with no DSM/RR/kernel. (The real RR + CLI e2e live in
test_consultation_store.py, run against the kernel.)
"""

from __future__ import annotations

from types import SimpleNamespace

from prl.collectors import ConsultationAdapter
from prl.query.consultation_read import (
    ConsultationQuery,
    ConsultationView,
    render_consultations,
    view_from_entry,
)
from prl.types import to_entry


def _entry(node, receipt: str):
    """A minimal Entry-like object: action_name + canonical content + a DSM receipt hash."""
    draft = to_entry(node, shard="prl_consultations", session_id="run-1")
    return SimpleNamespace(metadata=draft.metadata, content=draft.content, hash=receipt)


class _StubNav:
    def __init__(self, entries):
        self._entries = entries

    def navigate_action(self, action, limit=None):
        return self._entries if action == "prl.consultation" else []

    def resolve_entries(self, records, limit=None):
        return records  # records ARE the entries in this stub


def _acts():
    a = ConsultationAdapter()
    obs = a.to_act(subject_id="ko-1", answer="A", producer="claude via adapter v1",
                   agent_id="agent.test", confidence=0.6)
    prop = a.to_act(subject_id="ko-2", answer="B", producer="gpt via adapter v1",
                    agent_id="agent.test", confidence=0.8, propose=True)
    return obs, prop


# --- view_from_entry: receipt = the Entry hash -----------------------------

def test_view_carries_receipt_and_fields():
    obs, _ = _acts()
    v = view_from_entry(_entry(obs, "v1:abc123"))
    assert isinstance(v, ConsultationView)
    assert v.receipt == "v1:abc123"
    assert v.mode == "observation"
    assert v.producer == "claude via adapter v1"
    assert v.confidence == 0.6
    assert v.subject_id == "ko-1"


# --- ConsultationQuery via injected navigator (no kernel) ------------------

def test_list_returns_all_and_filters_by_subject():
    obs, prop = _acts()
    nav = _StubNav([_entry(obs, "v1:r1"), _entry(prop, "v1:r2")])
    q = ConsultationQuery(storage=None, index_dir=None, _navigator=nav)

    everything = q.list()
    assert {v.subject_id for v in everything} == {"ko-1", "ko-2"}
    assert {v.mode for v in everything} == {"observation", "proposal"}

    only_ko2 = q.list(subject_id="ko-2")
    assert [v.subject_id for v in only_ko2] == ["ko-2"]
    assert only_ko2[0].mode == "proposal"


# --- render: distinguishes Observation vs Proposal -------------------------

def test_render_distinguishes_mode_and_shows_receipt():
    obs, prop = _acts()
    out = render_consultations([
        view_from_entry(_entry(obs, "v1:r1")),
        view_from_entry(_entry(prop, "v1:r2")),
    ])
    assert "OBSERVATION on ko-1" in out
    assert "PROPOSAL on ko-2" in out
    assert "DSM receipt: v1:r1" in out
    assert "producer: gpt via adapter v1" in out


def test_render_empty():
    assert render_consultations([]) == "no consultations found"
