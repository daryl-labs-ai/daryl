"""Object coherence visibility (#4b v1) — pure tests.

The experiment (yours, reading d): make a subject's **agreement/disagreement across its
claims** visible — *without merging them and without deciding*. v1 = detect + surface, like #2:
- the #4a **gather is unchanged** (claims side by side, each with its own standing);
- a derived **`coherence` descriptor** (`aligned`/`divergent`/`unsettled`) is read alongside —
  **never a subject standing**, never a merge, never a verdict.

Rule **C-d** (confirmed): over the subject's **live governed** claims (standing ∈
{accepted, rejected}); `superseded`/`withdrawn` are closed transitions, excluded. The four
checks: (1) divergent surfaced, (2) aligned, (3) unsettled (closed transitions don't count),
(4) #2 per-claim conflict orthogonal + derived.
"""

from __future__ import annotations

from types import SimpleNamespace

from prl.collectors import ConsultationAdapter, make_resolution
from prl.query.subject_read import (
    ClaimStanding,
    SubjectStandingsQuery,
    detect_coherence,
)
from prl.types import Carrier, to_entry


def _cs(claim_id, standing, conflict=False):
    return ClaimStanding(claim_id=claim_id, mode="proposal", standing=standing, conflict=conflict)


# ── detect_coherence (pure, C-d) ─────────────────────────────────────────────────────────────
def test_detect_coherence_rule_cd():
    # divergent: one live accepted + one live rejected
    c, parties = detect_coherence([_cs("a", "accepted"), _cs("b", "rejected")])
    assert c == "divergent" and set(parties) == {"a", "b"}
    # aligned: all live governed share one decision
    assert detect_coherence([_cs("a", "accepted"), _cs("b", "accepted")]) == ("aligned", ())
    # unsettled: no live governed claim
    assert detect_coherence([_cs("a", "proposed"), _cs("b", "proposed")]) == ("unsettled", ())
    # closed transitions excluded: superseded/withdrawn don't count as live decisions
    assert detect_coherence([_cs("a", "superseded"), _cs("b", "withdrawn")]) == ("unsettled", ())
    # an accepted beside a superseded → aligned (superseded excluded, one live accepted remains)
    assert detect_coherence([_cs("a", "accepted"), _cs("b", "superseded")]) == ("aligned", ())


# ── end-to-end via the query (shared nav serving consultations + resolutions) ────────────────
def _consult(subject, claim_id, *, carrier="gpt-4o"):
    return ConsultationAdapter().to_act(
        subject_id=subject, answer="x", producer=f"openai:{carrier}", agent_id="agent.architect",
        confidence=1.0, carrier=Carrier(provider="openai", model=carrier), propose=True,
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


def _query(items):
    return SubjectStandingsQuery(None, None, _navigator=_MixedNav(items))


# ── Gate 1 — divergent surfaced, no subject standing, claims side by side ─────────────────────
def test_divergent_surfaced_no_subject_standing():
    items = [
        _item(_consult("S", "claim-a"), "c0"),
        _item(_consult("S", "claim-b"), "c1"),
        _item(make_resolution(target_claim_id="claim-a", decision="accepted", agent_id="mohamed.azizi"), "r0"),
        _item(make_resolution(target_claim_id="claim-b", decision="rejected", agent_id="mohamed.azizi"), "r1"),
    ]
    view = _query(items).standings_of_subject("S")
    assert view.coherence == "divergent"
    assert set(view.divergent_claims) == {"claim-a", "claim-b"}
    assert len(view.claims) == 2                         # claims still side by side (gather intact)
    assert not hasattr(view, "standing")                 # the subject has NO standing (no verdict)
    assert {c.standing for c in view.claims} == {"accepted", "rejected"}  # not merged


# ── Gate 2 — aligned ─────────────────────────────────────────────────────────────────────────
def test_aligned_when_governed_claims_agree():
    items = [
        _item(_consult("A", "claim-a"), "c0"),
        _item(_consult("A", "claim-b"), "c1"),
        _item(make_resolution(target_claim_id="claim-a", decision="accepted", agent_id="mohamed.azizi"), "r0"),
        _item(make_resolution(target_claim_id="claim-b", decision="accepted", agent_id="mohamed.azizi"), "r1"),
    ]
    view = _query(items).standings_of_subject("A")
    assert view.coherence == "aligned" and view.divergent_claims == ()


# ── Gate 3 — unsettled; closed transitions don't count ───────────────────────────────────────
def test_unsettled_proposed_only_and_closed_transitions_excluded():
    proposed_only = [_item(_consult("U", "claim-a"), "c0"), _item(_consult("U", "claim-b"), "c1")]
    assert _query(proposed_only).standings_of_subject("U").coherence == "unsettled"

    # claim-a superseded, claim-b withdrawn → both closed transitions → unsettled (excluded).
    closed = [
        _item(_consult("U2", "claim-a"), "c0"),
        _item(_consult("U2", "claim-b"), "c1"),
        _item(make_resolution(target_claim_id="claim-a", decision="superseded", agent_id="mohamed.azizi"), "r0"),
        _item(make_resolution(target_claim_id="claim-b", decision="withdrawn", agent_id="mohamed.azizi"), "r1"),
    ]
    v = _query(closed).standings_of_subject("U2")
    assert v.coherence == "unsettled"
    assert {c.standing for c in v.claims} == {"superseded", "withdrawn"}  # gather still shows them


# ── Gate 4 — #2 per-claim conflict orthogonal; coherence derived (drop/rebuild identical) ─────
def test_per_claim_conflict_orthogonal_and_derived():
    # One claim, itself in #2 conflict (alice accept + bob reject) → standing latest (rejected),
    # claim conflict=True. The subject has a single live governed claim ⇒ coherence = aligned
    # (one decision). The per-claim conflict does NOT make the subject divergent.
    items = [
        _item(_consult("X", "claim-x"), "c0"),
        _item(make_resolution(target_claim_id="claim-x", decision="accepted", agent_id="alice"), "r0"),
        _item(make_resolution(target_claim_id="claim-x", decision="rejected", agent_id="bob"), "r1"),
    ]
    first = _query(items).standings_of_subject("X")
    assert first.claims[0].conflict is True and first.claims[0].standing == "rejected"
    assert first.coherence == "aligned"                  # cross-claim coherence ≠ per-claim conflict

    # Derived: drop/rebuild ⇒ identical; the gather is byte-identical to the #4a tuple.
    second = _query(items).standings_of_subject("X")
    assert first == second
    assert first.claims == second.claims
