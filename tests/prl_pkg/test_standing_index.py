"""Derived standing at scale (#1) — pure tests.

`StandingIndex` memoizes the act *grouping*, never the standing: `standing_of` still derives
via `derive_standing` every call. The four checks (your frame): (1) bounded cost vs a full
scan, (2) a non-authoritative projection, (3) standing identical to `StandingQuery`, (4) the
source stays the acts (drop ⇒ recompute identical).
"""

from __future__ import annotations

from types import SimpleNamespace

from prl.collectors import make_resolution
from prl.query.standing_read import StandingIndex, StandingQuery, derive_standing
from prl.types import to_entry


def _res_item(node, eid):
    d = to_entry(node, shard="prl_consultations", session_id="r")
    return ({"entry_id": eid}, SimpleNamespace(id=eid, hash="v1:" + eid,
                                               content=d.content, metadata=dict(d.metadata)))


class _CountingNav:
    """Faithful RegistryProjection that COUNTS resolves; resolve_entries reorders (reversed),
    so the test also guards latest-wins under the index's record-order grouping."""

    def __init__(self, items):  # items: list[(record, entry)] in ascending record order
        self._items = items
        self.resolve_calls = 0

    def navigate_action(self, action, limit=None):
        return [r for r, _e in self._items] if action == "prl.resolution" else []

    def resolve_entries(self, records, limit=None):
        self.resolve_calls += 1
        ids = {r["entry_id"] for r in records}
        return list(reversed([e for _r, e in self._items if e.id in ids]))


def _dataset(m_claims, per_claim):
    items, claims = [], []
    k = 0
    for c in range(m_claims):
        claim = f"claim-{c}"
        claims.append(claim)
        for j in range(per_claim):
            node = make_resolution(
                target_claim_id=claim,
                decision="accepted" if j % 2 == 0 else "superseded",
                agent_id="mohamed.azizi")
            items.append(_res_item(node, f"r{k}"))
            k += 1
    return items, claims


def test_index_standing_equals_query_for_all_claims():
    items, claims = _dataset(5, 3)  # latest-wins per claim (accepted→superseded→accepted)
    sq = StandingQuery(None, None, _navigator=_CountingNav(items))
    idx = StandingIndex(None, None, _navigator=_CountingNav(items))
    for c in claims:
        assert idx.standing_of(c) == sq.standing_of(c)          # identical value
        assert idx.standing_of(c).standing == "accepted"        # latest-wins survived grouping
    assert idx.standing_of("absent").standing == "proposed" == sq.standing_of("absent").standing


def test_index_bounds_cost_vs_full_scan():
    items, claims = _dataset(6, 2)  # 12 resolutions, 6 claims

    nav_q = _CountingNav(items)
    sq = StandingQuery(None, None, _navigator=nav_q)
    for c in claims:
        sq.standing_of(c)
    assert nav_q.resolve_calls == len(claims)   # O(N) full-bucket scan PER query → M scans

    nav_i = _CountingNav(items)
    idx = StandingIndex(None, None, _navigator=nav_i)
    assert nav_i.resolve_calls == 1             # ONE scan at build …
    for c in claims:
        idx.standing_of(c)
    assert nav_i.resolve_calls == 1             # … and ZERO per query (O(1) lookup + O(k) derive)


def test_index_is_a_droppable_projection_whose_source_is_the_acts():
    items, claims = _dataset(3, 2)
    idx = StandingIndex(None, None, _navigator=_CountingNav(items))
    before = {c: idx.standing_of(c) for c in claims}

    # "Drop" the index; rebuild from the SAME acts → identical (the cache was disposable).
    idx2 = StandingIndex(None, None, _navigator=_CountingNav(items))
    assert {c: idx2.standing_of(c) for c in claims} == before

    # Non-authoritative: no write path; standing is derived, equal to derive_standing of the facts.
    assert not hasattr(idx, "set_standing") and not hasattr(idx, "store")
    for c in claims:
        assert idx.standing_of(c) == derive_standing(c, idx.resolutions_of(c))
