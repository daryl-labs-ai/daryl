"""Concurrent resolutions (#2 v1) — conflict visibility, angle (b). Pure tests.

The frame (yours): #2 must not *resolve* the conflict first; it must first make a conflict
**impossible to be invisible**. So v1 = **detect + surface**, never govern:
- latest-wins stays the projection rule (`derive_standing`'s standing is unchanged);
- the history stays append-only;
- the system *derives* an orthogonal `conflict` signal (D3 + legacy D2 fallback), never stored.

Definition **D3** (confirmed): a claim is in conflict when **two distinct `agent_id`** issue
**substantively opposite** decisions (one `accepted`, one `rejected`). A single author changing
their mind is a **supersession, not a conflict**. **Legacy fallback (D2):** an unknown `agent_id`
(`""`) with opposite decisions is **surfaced**, never silently inferred as no-conflict.

The four proof-gate checks (functional, no credential — the measurement is the proof).
"""

from __future__ import annotations

from types import SimpleNamespace

from prl.collectors import make_resolution
from prl.query.standing_read import (
    ResolutionFact,
    StandingIndex,
    derive_standing,
    detect_conflict,
)
from prl.types import to_entry


def _fact(decision, agent_id="", receipt="r"):
    return ResolutionFact(decision=decision, resolver=agent_id or "(unknown)",
                          receipt=receipt, agent_id=agent_id)


# ── Gate 1 — two distinct authorities, opposite decisions ───────────────────────────────────
def test_two_authorities_opposite_decisions_conflict_standing_unchanged():
    # alice:accepted then bob:rejected (authoritative order). Latest is rejected.
    res = [_fact("accepted", "alice"), _fact("rejected", "bob")]

    view = derive_standing("c1", res)
    assert view.standing == "rejected"            # latest-wins UNCHANGED — conflict does not govern
    assert view.conflict is True                  # … but the disagreement is surfaced
    assert set(view.conflict_parties) == {"alice", "bob"}

    conflict, parties = detect_conflict(res)
    assert conflict is True and set(parties) == {"alice", "bob"}

    # Standing is byte-identical to the no-conflict-signal latest-wins (regression guard).
    assert view.standing == res[-1].decision
    assert view.decisions == ("accepted", "rejected")


# ── Gate 2 — one author superseding/flipping their own decision is NOT a conflict ────────────
def test_single_author_change_of_mind_is_supersession_not_conflict():
    # Same agent_id accepts, then rejects: an evolution, not an inter-authority conflict.
    res = [_fact("accepted", "alice"), _fact("rejected", "alice")]
    view = derive_standing("c2", res)
    assert view.standing == "rejected"            # latest-wins
    assert view.conflict is False                 # one authority → supersession, not conflict
    assert view.conflict_parties == ()

    # An explicit supersession transition is likewise no conflict.
    res2 = [_fact("accepted", "alice"), _fact("superseded", "bob")]
    assert detect_conflict(res2) == (False, ())   # superseded/withdrawn are transitions, not opposition


# ── Gate 3 — consistent → no conflict; legacy opposite → surfaced (never silently False) ─────
def test_consistent_no_conflict_and_legacy_opposite_is_surfaced():
    # Consistent: only accepted (by distinct authors) → no opposition → no conflict.
    assert derive_standing("c3", [_fact("accepted", "alice"), _fact("accepted", "bob")]).conflict is False
    # No resolutions at all → proposed, no conflict.
    assert derive_standing("c3b", []).conflict is False

    # Legacy fallback (D2): unknown agent_id on opposite decisions ⇒ cannot attribute authorship
    # ⇒ SURFACE rather than silently ignore.
    legacy = [_fact("accepted", ""), _fact("rejected", "")]
    view = derive_standing("c4", legacy)
    assert view.standing == "rejected"            # standing still latest-wins
    assert view.conflict is True                  # surfaced, never silently False
    assert "" in view.conflict_parties

    # Mixed: a known author accepts, an unknown rejects ⇒ still surfaced (can't rule out cross-author).
    mixed = [_fact("accepted", "alice"), _fact("rejected", "")]
    assert detect_conflict(mixed)[0] is True


# ── Gate 4 — conflict is DERIVED, never stored: drop/rebuild ⇒ identical ─────────────────────
def _res_item(node, eid):
    d = to_entry(node, shard="prl_consultations", session_id="r")
    return ({"entry_id": eid}, SimpleNamespace(id=eid, hash="v1:" + eid,
                                               content=d.content, metadata=dict(d.metadata)))


class _Nav:
    def __init__(self, items):
        self._items = items

    def navigate_action(self, action, limit=None):
        return [r for r, _e in self._items] if action == "prl.resolution" else []

    def resolve_entries(self, records, limit=None):
        ids = {r["entry_id"] for r in records}
        return [e for _r, e in self._items if e.id in ids]


def test_conflict_is_derived_drop_rebuild_identical_no_stored_field():
    # Two distinct human authorities disagree on the same claim (real ResolutionNodes).
    a = make_resolution(target_claim_id="claim-x", decision="accepted", agent_id="alice")
    b = make_resolution(target_claim_id="claim-x", decision="rejected", agent_id="bob")
    items = [_res_item(a, "r0"), _res_item(b, "r1")]

    idx = StandingIndex(None, None, _navigator=_Nav(items))
    v = idx.standing_of("claim-x")
    assert v.standing == "rejected" and v.conflict is True   # index inherits conflict via derive_standing

    # Drop the index; rebuild from the SAME acts ⇒ identical (the signal was never stored).
    idx2 = StandingIndex(None, None, _navigator=_Nav(items))
    assert idx2.standing_of("claim-x") == v

    # No stored conflict field anywhere on the node; the signal is recomputed from the facts.
    assert not hasattr(b, "conflict")
    assert derive_standing("claim-x", idx.resolutions_of("claim-x")) == v
