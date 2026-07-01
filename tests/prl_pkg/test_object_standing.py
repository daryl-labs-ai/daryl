"""Object standing (ADR-PRL-0012, #4b-S) — pure tests.

The subject-scale analog of ADR-0011: `object_standing` is a read-only authoritative reading
**above** the #4a gather + #4b coherence — derived, never stored, no `object_id`, no content merge.

Rule (precedence **`claim contested` > `subject divergent` > `aligned` decision > `unsettled`**):
1. any constituent claim `contested` (its #2 conflict) → `contested`;
2. else coherence `divergent` → `contested`;
3. else coherence `aligned` → the shared decision;
4. else `unsettled` → `proposed`.

The five gates: (1) divergent → contested; (2) aligned + a contested claim → contested (precedence);
(3) aligned + none contested → shared decision; (4) unsettled → proposed; (5) derived (drop/rebuild).
"""

from __future__ import annotations

from types import SimpleNamespace

from prl.collectors import ConsultationAdapter, make_resolution
from prl.query.subject_read import (
    ClaimStanding,
    SubjectStandingsQuery,
    derive_object_standing,
)
from prl.types import Carrier, to_entry


def _cs(claim_id, standing, conflict=False):
    return ClaimStanding(claim_id=claim_id, mode="proposal", standing=standing, conflict=conflict)


# ── pure derivation (ADR-0012 precedence) ────────────────────────────────────────────────────
def test_derive_object_standing_precedence():
    # divergent → contested
    assert derive_object_standing([_cs("a", "accepted"), _cs("b", "rejected")], "divergent") == "contested"
    # aligned + a claim itself contested → contested (precedence: claim contested > aligned decision)
    assert derive_object_standing([_cs("a", "rejected", conflict=True)], "aligned") == "contested"
    # aligned, none contested → the shared decision
    assert derive_object_standing([_cs("a", "accepted"), _cs("b", "accepted")], "aligned") == "accepted"
    assert derive_object_standing([_cs("a", "rejected"), _cs("b", "rejected")], "aligned") == "rejected"
    # unsettled → proposed
    assert derive_object_standing([_cs("a", "proposed")], "unsettled") == "proposed"
    # the load-bearing guarantee: an object is NEVER accepted while a constituent claim is contested
    mixed = [_cs("a", "accepted"), _cs("b", "accepted", conflict=True)]
    assert derive_object_standing(mixed, "aligned") == "contested"


# ── end-to-end via the query ─────────────────────────────────────────────────────────────────
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


def _q(items):
    return SubjectStandingsQuery(None, None, _navigator=_MixedNav(items))


def _res(claim, decision, agent):
    return make_resolution(target_claim_id=claim, decision=decision, agent_id=agent)


# ── Gate 1 — divergent → contested ───────────────────────────────────────────────────────────
def test_divergent_object_contested():
    items = [
        _item(_consult("S", "claim-a"), "c0"), _item(_consult("S", "claim-b"), "c1"),
        _item(_res("claim-a", "accepted", "mohamed.azizi"), "r0"),
        _item(_res("claim-b", "rejected", "mohamed.azizi"), "r1"),
    ]
    v = _q(items).standings_of_subject("S")
    assert v.coherence == "divergent" and v.object_standing == "contested"


# ── Gate 2 — aligned + a contested claim → contested (PRECEDENCE) ─────────────────────────────
def test_aligned_with_contested_claim_object_contested():
    # both claims rejected (aligned), but claim-a is itself #2-contested (alice accept + bob reject).
    items = [
        _item(_consult("S", "claim-a"), "c0"), _item(_consult("S", "claim-b"), "c1"),
        _item(_res("claim-a", "accepted", "alice"), "r0"),
        _item(_res("claim-a", "rejected", "bob"), "r1"),      # claim-a: raw rejected, conflict=True
        _item(_res("claim-b", "rejected", "mohamed.azizi"), "r2"),
    ]
    v = _q(items).standings_of_subject("S")
    assert v.coherence == "aligned"                 # both raw standings are 'rejected' → aligned
    assert any(c.conflict for c in v.claims)        # claim-a is itself contested
    assert v.object_standing == "contested"         # precedence: contested claim wins over aligned


# ── Gate 3 — aligned, none contested → the shared decision ───────────────────────────────────
def test_aligned_none_contested_shared_decision():
    items = [
        _item(_consult("A", "claim-a"), "c0"), _item(_consult("A", "claim-b"), "c1"),
        _item(_res("claim-a", "accepted", "mohamed.azizi"), "r0"),
        _item(_res("claim-b", "accepted", "mohamed.azizi"), "r1"),
    ]
    v = _q(items).standings_of_subject("A")
    assert v.coherence == "aligned" and v.object_standing == "accepted"


# ── Gate 4 — unsettled → proposed ────────────────────────────────────────────────────────────
def test_unsettled_object_proposed():
    items = [_item(_consult("U", "claim-a"), "c0"), _item(_consult("U", "claim-b"), "c1")]
    v = _q(items).standings_of_subject("U")
    assert v.coherence == "unsettled" and v.object_standing == "proposed"


# ── Gate 5 — derived: drop/rebuild identical; no object_id / no stored field ──────────────────
def test_object_standing_is_derived_drop_rebuild_identical():
    items = [
        _item(_consult("S", "claim-a"), "c0"), _item(_consult("S", "claim-b"), "c1"),
        _item(_res("claim-a", "accepted", "mohamed.azizi"), "r0"),
        _item(_res("claim-b", "rejected", "mohamed.azizi"), "r1"),
    ]
    first = _q(items).standings_of_subject("S")
    assert _q(items).standings_of_subject("S") == first          # derived, never stored
    # no object_id / no stored field: object_standing lives only on the view, derived from claims+coherence.
    assert first.object_standing == derive_object_standing(first.claims, first.coherence)
    assert not any(hasattr(c, "object_standing") for c in first.claims)   # not on the claims
    # raw per-claim standings unchanged (governance reads above, never into the gather).
    assert {c.standing for c in first.claims} == {"accepted", "rejected"}
