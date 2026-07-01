"""Governance layer probe (step (c) v0) — pure tests.

The experiment (yours, frame iv): keep **latest-wins** as the projection rule; add a
**governance layer above** it that **derives** a posture — `clear | contested | divergent` —
**without changing the standing and without blocking any write**. v0 governs nothing; it proves
the *seam*.

Rule **G-1** (confirmed, collapsed precedence `divergent > contested > clear`):
- claim: `contested` iff #2 conflict, else `clear`;
- subject: `divergent` iff #4b coherence divergent, else `contested` iff any claim contested,
  else `clear`.

The four checks: (1) claim state + standing unchanged, (2) subject precedence, (3) read-only /
above latest-wins (no write path, `MEF.contested` still unread), (4) derived (drop/rebuild).
"""

from __future__ import annotations

from types import SimpleNamespace

from prl.collectors import ConsultationAdapter, make_resolution
from prl.query.governance_read import (
    GovernanceQuery,
    derive_governance_state,
    derive_subject_governance_state,
)
from prl.types import Carrier, to_entry


# ── pure derivation (G-1) ────────────────────────────────────────────────────────────────────
def test_derive_states_rule_g1():
    assert derive_governance_state(False) == "clear"
    assert derive_governance_state(True) == "contested"
    # subject precedence: divergent > contested > clear
    assert derive_subject_governance_state("divergent", [False, False]) == "divergent"
    assert derive_subject_governance_state("divergent", [True]) == "divergent"      # divergent wins
    assert derive_subject_governance_state("aligned", [True, False]) == "contested"  # a contested claim
    assert derive_subject_governance_state("aligned", [False]) == "clear"
    assert derive_subject_governance_state("unsettled", [False]) == "clear"


# ── end-to-end via the query (shared nav: consultations + resolutions) ───────────────────────
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
    return GovernanceQuery(None, None, _navigator=_MixedNav(items))


# ── Gate 1 — claim governance + standing unchanged ───────────────────────────────────────────
def test_claim_governance_standing_unchanged():
    # clear: a single accepted resolution, no conflict.
    clear = [
        _item(_consult("S", "claim-a"), "c0"),
        _item(make_resolution(target_claim_id="claim-a", decision="accepted", agent_id="mohamed.azizi"), "r0"),
    ]
    gc = _query(clear).governance_of_claim("claim-a")
    assert gc.governance == "clear" and gc.standing == "accepted"   # standing latest-wins, unchanged

    # contested: two authorities opposed on the SAME claim (#2 conflict) → contested, standing = latest.
    contested = [
        _item(_consult("S", "claim-b"), "c0"),
        _item(make_resolution(target_claim_id="claim-b", decision="accepted", agent_id="alice"), "r0"),
        _item(make_resolution(target_claim_id="claim-b", decision="rejected", agent_id="bob"), "r1"),
    ]
    gc2 = _query(contested).governance_of_claim("claim-b")
    assert gc2.governance == "contested"
    assert gc2.standing == "rejected"                              # latest-wins UNCHANGED by governance


# ── Gate 2 — subject precedence (divergent > contested > clear) ──────────────────────────────
def test_subject_governance_precedence():
    # divergent: one accepted + one rejected claim → #4b divergent → governance divergent.
    divergent = [
        _item(_consult("D", "claim-a"), "c0"),
        _item(_consult("D", "claim-b"), "c1"),
        _item(make_resolution(target_claim_id="claim-a", decision="accepted", agent_id="mohamed.azizi"), "r0"),
        _item(make_resolution(target_claim_id="claim-b", decision="rejected", agent_id="mohamed.azizi"), "r1"),
    ]
    gd = _query(divergent).governance_of_subject("D")
    assert gd.governance == "divergent" and gd.coherence == "divergent"

    # contested (not divergent): claims agree at subject level, but one claim is itself #2-contested.
    contested = [
        _item(_consult("C", "claim-a"), "c0"),
        _item(make_resolution(target_claim_id="claim-a", decision="accepted", agent_id="alice"), "r0"),
        _item(make_resolution(target_claim_id="claim-a", decision="rejected", agent_id="bob"), "r1"),
    ]
    gc = _query(contested).governance_of_subject("C")
    # claim-a standing = rejected (single governed claim → aligned), but it is #2-contested.
    assert gc.coherence == "aligned" and gc.governance == "contested"
    assert gc.contested_claims == ("claim-a",)

    # clear: a single uncontested accepted claim.
    clear = [
        _item(_consult("K", "claim-a"), "c0"),
        _item(make_resolution(target_claim_id="claim-a", decision="accepted", agent_id="mohamed.azizi"), "r0"),
    ]
    assert _query(clear).governance_of_subject("K").governance == "clear"


# ── Gate 3 — read-only, above latest-wins (no write path; standing byte-identical) ────────────
def test_read_only_above_latest_wins():
    items = [
        _item(_consult("S", "claim-a"), "c0"),
        _item(make_resolution(target_claim_id="claim-a", decision="accepted", agent_id="alice"), "r0"),
        _item(make_resolution(target_claim_id="claim-a", decision="rejected", agent_id="bob"), "r1"),
    ]
    gq = _query(items)
    # the layer has NO write path.
    for attr in ("set_governance", "govern", "commit", "resolve", "store", "block"):
        assert not hasattr(gq, attr)
    # governance does NOT change the standing: the underlying StandingQuery is byte-identical.
    from prl.query.standing_read import StandingQuery
    sq = StandingQuery(None, None, _navigator=_MixedNav(items))
    assert sq.standing_of("claim-a").standing == gq.governance_of_claim("claim-a").standing == "rejected"


# ── Gate 4 — derived: drop/rebuild identical ─────────────────────────────────────────────────
def test_governance_is_derived_drop_rebuild_identical():
    items = [
        _item(_consult("S", "claim-a"), "c0"),
        _item(_consult("S", "claim-b"), "c1"),
        _item(make_resolution(target_claim_id="claim-a", decision="accepted", agent_id="mohamed.azizi"), "r0"),
        _item(make_resolution(target_claim_id="claim-b", decision="rejected", agent_id="mohamed.azizi"), "r1"),
    ]
    first_c = _query(items).governance_of_claim("claim-a")
    first_s = _query(items).governance_of_subject("S")
    assert _query(items).governance_of_claim("claim-a") == first_c     # rebuilt, identical
    assert _query(items).governance_of_subject("S") == first_s
