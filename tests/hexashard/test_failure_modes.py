"""Adversarial / failure tests F1-F4.

These are context-management failure modes, not model-intelligence tests.
"""

from hexashard import PinStatus, Project, RetrievalFilters, SourceStatus


# F1 -----------------------------------------------------------------------
def test_f1_stale_pin_is_detected_and_reconciled(loaded):
    """A pin left pointing at a legitimately superseded source."""
    p, spec, s1, _ = loaded
    s3 = p.add_source(
        "spec", "Mission brief rev 2",
        "The capex ceiling for the programme is 5.1 million euro.",
        hex_id=spec.hex_id, claim_key="capex_ceiling", claim_value="5.1M EUR",
    )
    p.supersede(s1.source_id, s3.source_id, reconcile_pins=False)

    stale = p.resolve_pin("capex_ceiling")
    assert stale.status is PinStatus.STALE
    assert stale.grounded is True                 # it still resolves...
    assert "superseded by" in stale.detail        # ...but is flagged, not trusted

    [rec] = p.reconcile_pins()
    assert (rec.before, rec.after) == (PinStatus.STALE, PinStatus.ACTIVE)
    assert rec.old_source_ref == s1.source_id and rec.new_source_ref == s3.source_id
    assert rec.value_changed is True
    assert p.pins.by_key("capex_ceiling").value == "5.1M EUR"
    assert p.resolve_pin("capex_ceiling").status is PinStatus.ACTIVE


def test_f1_reconcile_never_invents_a_value(loaded):
    """When the successor declares no value for the key, the pin is flagged."""
    p, spec, s1, _ = loaded
    s3 = p.add_source(
        "spec", "Mission brief rev 2",
        "The programme budget was revised at the 2032 review.",
        hex_id=spec.hex_id,                      # no claim_key / claim_value
    )
    p.supersede(s1.source_id, s3.source_id, reconcile_pins=False)

    [rec] = p.reconcile_pins()
    assert rec.after is PinStatus.NEEDS_REVIEW
    assert rec.value_changed is False
    assert "human review" in rec.detail
    pin = p.pins.by_key("capex_ceiling")
    assert pin.value == "4.2M EUR"               # old value kept, not guessed
    assert pin.source_ref == s3.source_id        # but repointed for checking


def test_f1_turn_surfaces_stale_pins_as_warnings(loaded):
    p, spec, s1, _ = loaded
    s3 = p.add_source("spec", "rev 2", "Revised ceiling text.", hex_id=spec.hex_id)
    p.sources.supersede(s1.source_id, s3.source_id)   # bypass pin reconciliation
    p.retriever.reindex()
    turn = p.handle_turn("capex ceiling")
    warnings = turn.response_context["pin_warnings"]
    assert [w["status"] for w in warnings] == ["STALE"]
    assert warnings[0]["key"] == "capex_ceiling"


# F2 -----------------------------------------------------------------------
def test_f2_ambiguous_authority_is_exposed_not_resolved(tmp_path):
    """Two CURRENT sources claiming the same thing: report, do not pick."""
    p = Project.create(tmp_path / "p", name="t")
    a = p.add_source("note", "Onboarding note A",
                     "The retention sweeper was upgraded; residual risk moderate.",
                     claim_key="aldret.retention_sweeper")
    b = p.add_source("note", "Onboarding note B",
                     "The retention sweeper was benchmarked; residual risk low.",
                     claim_key="aldret.retention_sweeper")

    res = p.retrieve("retention sweeper residual risk")
    assert len(res.ambiguities) == 1
    amb = res.ambiguities[0]
    assert amb.claim_key == "aldret.retention_sweeper"
    assert amb.source_ids == sorted([a.source_id, b.source_id])
    assert "cannot be resolved automatically" in amb.reason
    # both candidates are returned; neither is silently preferred
    assert set(res.source_ids) == {a.source_id, b.source_id}

    # an explicit supersession is how a human resolves it
    p.supersede(a.source_id, b.source_id)
    after = p.retrieve("retention sweeper residual risk")
    assert after.ambiguities == []
    assert after.source_ids == [b.source_id]


def test_f2_ambiguity_reaches_the_turn_context(tmp_path):
    p = Project.create(tmp_path / "p", name="t")
    p.add_source("note", "A", "The ledger writer was upgraded.", claim_key="ledger_writer")
    p.add_source("note", "B", "The ledger writer was decommissioned.", claim_key="ledger_writer")
    turn = p.handle_turn("what is the status of the ledger writer")
    assert turn.response_context["ambiguities"][0]["claim_key"] == "ledger_writer"


# F3 -----------------------------------------------------------------------
def test_f3_missing_source_is_reported_not_fabricated(loaded):
    p, _spec, s1, _ = loaded
    root = p.root
    p.close()

    (root / "sources" / f"{s1.source_id}.json").unlink()
    (root / "sources" / f"{s1.source_id}.txt").unlink()

    q = Project.open(root)
    res = q.resolve_pin("capex_ceiling")
    assert res.status is PinStatus.BROKEN
    assert res.grounded is False
    assert res.source is None
    assert res.detail == f"source {s1.source_id} is not present in the store"
    assert q.by_address(s1.source_id) is None
    # the pin still holds its last known value, clearly marked as ungrounded
    assert res.pin.value == "4.2M EUR"

    [rec] = [r for r in q.reconcile_pins() if r.key == "capex_ceiling"]
    assert rec.after is PinStatus.BROKEN
    turn = q.handle_turn("capex ceiling")
    assert turn.response_context["pin_warnings"][0]["status"] == "BROKEN"


def test_f3_pin_without_a_source_ref_is_ungrounded(proj):
    proj.pin("informal", "someone said so", None, critical=True)
    res = proj.resolve_pin("informal")
    assert res.grounded is False and res.status is PinStatus.BROKEN
    assert "cannot be grounded" in res.detail


# F4 -----------------------------------------------------------------------
def test_f4_historical_query_returns_history_marked_as_history(loaded):
    p, spec, s1, _ = loaded
    s3 = p.add_source(
        "spec", "Mission brief rev 2",
        "The capex ceiling for the programme is 5.1 million euro.",
        hex_id=spec.hex_id, claim_key="capex_ceiling", claim_value="5.1M EUR",
    )
    p.supersede(s1.source_id, s3.source_id)

    hist = p.retrieve("capex ceiling", RetrievalFilters(include_superseded=True))
    statuses = {f.source_id: f.source_status for f in hist.fragments}
    assert statuses[s1.source_id] == "SUPERSEDED"
    assert statuses[s3.source_id] == "CURRENT"
    # ranked below the current source, never presented as equal
    assert hist.fragments[0].source_id == s3.source_id
    assert hist.filters["effective_statuses"] == ["CURRENT", "SUPERSEDED"]

    only_old = p.retrieve("capex ceiling",
                          RetrievalFilters(statuses=(SourceStatus.SUPERSEDED,)))
    assert only_old.source_ids == [s1.source_id]
    assert "4.2 million euro" in only_old.fragments[0].text
    assert only_old.fragments[0].source_status == "SUPERSEDED"
