"""Core acceptance tests T1-T12 from the Core v0.1 specification."""

import json

import pytest

from hexashard import (
    HexType,
    MockModelProvider,
    NullTrustBackend,
    PinStatus,
    Project,
    RetrievalFilters,
    SourceStatus,
    enforce_budget,
)
from hexashard.context import ActiveState
from hexashard.ids import machine_uuid, parse_hex_address


# T1 -----------------------------------------------------------------------
def test_t1_create_project_starts_empty(proj):
    assert len(proj.hexmap) == 0
    assert len(proj.pins) == 0
    assert proj.sources.all() == []
    assert proj.state.epoch == 1
    assert proj.state.active_pins == []
    assert (proj.root / "project.json").exists()
    assert (proj.root / "active_state.json").exists()


# T2 -----------------------------------------------------------------------
def test_t2_source_is_addressable(proj):
    src = proj.add_source("spec", "Brief", "Kell-9 tolerance is 0.4 millimetres.")
    assert src.source_id == "P1.S0001"
    assert proj.by_address("P1.S0001").title == "Brief"
    assert (proj.root / "sources" / "P1.S0001.json").exists()
    # content is plain text on disk, not embedded JSON
    assert (proj.root / "sources" / "P1.S0001.txt").read_text().startswith("Kell-9")
    hits = proj.retrieve("Kell-9 tolerance")
    assert hits.source_ids == ["P1.S0001"]


# T3 -----------------------------------------------------------------------
def test_t3_hex_gets_deterministic_address(proj):
    a = proj.add_hex("First", HexType.SOURCE)
    b = proj.add_hex("Second", HexType.DECISION)
    assert (a.hex_id, b.hex_id) == ("P1.E1.H001", "P1.E1.H002")
    assert parse_hex_address(b.hex_id) == ("P1", 1, 2)
    # the machine uuid is derived, not random
    assert a.uuid == machine_uuid("P1.E1.H001")


def test_t3_addresses_survive_reopen(tmp_path):
    p = Project.create(tmp_path / "p", name="t")
    p.add_hex("First", HexType.SOURCE)
    p.close()
    q = Project.open(tmp_path / "p")
    assert q.add_hex("Second", HexType.TASK).hex_id == "P1.E1.H002"


# T4 -----------------------------------------------------------------------
def test_t4_pin_points_at_authoritative_source(loaded):
    p, _spec, s1, _s2 = loaded
    res = p.resolve_pin("capex_ceiling")
    assert res.source.source_id == s1.source_id
    assert res.source.status is SourceStatus.CURRENT
    assert res.status is PinStatus.ACTIVE
    assert res.grounded is True
    # the pin carries enough to reach the primary source, and the value it
    # carries is a copy -- the source is what grounds it
    assert res.pin.source_ref == s1.source_id
    assert "4.2 million euro" in res.source.content


# T5 -----------------------------------------------------------------------
def test_t5_supersession_default_and_historical(loaded):
    p, spec, s1, _ = loaded
    s3 = p.add_source(
        "spec", "Mission brief rev 2",
        "The capex ceiling for the programme is 5.1 million euro after the 2032 uplift.",
        hex_id=spec.hex_id, claim_key="capex_ceiling", claim_value="5.1M EUR",
    )
    p.supersede(s1.source_id, s3.source_id)

    default = p.retrieve("capex ceiling")
    assert default.source_ids == [s3.source_id]
    assert all(f.source_status == "CURRENT" for f in default.fragments)

    historical = p.retrieve(
        "capex ceiling", RetrievalFilters(statuses=(SourceStatus.SUPERSEDED,))
    )
    assert historical.source_ids == [s1.source_id]
    assert p.sources.get(s1.source_id).superseded_by == s3.source_id
    assert p.sources.get(s3.source_id).version == 2


# T6 -----------------------------------------------------------------------
def _fat_state() -> ActiveState:
    s = ActiveState(epoch=1, mission="M" * 40, current_objective="Decide the fabric.")
    s.current_summary = "long running summary. " * 400
    s.active_pins = [
        {"pin_id": "P1.K001", "key": "capex", "value": "4.2M EUR",
         "source_ref": "P1.S0001", "critical": True, "status": "ACTIVE"},
        {"pin_id": "P1.K002", "key": "palette", "value": "blue",
         "source_ref": "P1.S0002", "critical": False, "status": "ACTIVE"},
    ]
    s.open_questions = [
        {"id": "Q1", "text": "What is the base period for the mean?", "resolved": False},
        {"id": "Q2", "text": "Which vendor?", "resolved": True},
    ]
    s.active_hex_refs = [f"P1.E1.H{i:03d}" for i in range(1, 40)]
    s.recent_decisions = [{"hex_id": f"P1.E1.H{i:03d}", "title": "decision " * 20,
                           "source_ref": f"P1.S{i:04d}"} for i in range(1, 12)]
    s.retrieval_hints = [f"hint number {i} " * 10 for i in range(30)]
    return s


def test_t6_budget_unloads_low_priority_material_first():
    """Cheap material goes first; addresses survive everything that goes."""
    s = _fat_state()
    report = enforce_budget(s, budget=400, summary_pointer="P1.E1.H900")

    assert report.tokens_after <= 400 and report.over_budget is False
    assert s.current_objective == "Decide the fabric."
    assert s.retrieval_hints == []
    assert s.active_hex_refs == [] and len(s.unloaded("hex")) == 39
    assert s.recent_decisions == [] and len(s.unloaded("decision")) == 11
    assert s.current_summary == "" and s.unloaded("summary") == ["P1.E1.H900"]
    # nothing binding was touched at this pressure
    assert [p["key"] for p in s.active_pins] == ["capex", "palette"]
    assert [q["id"] for q in s.open_questions] == ["Q1", "Q2"]


def test_t6_budget_compacts_but_keeps_critical_material(tmp_path):
    """Under real pressure: criticals survive intact, addresses are spilled."""
    s = _fat_state()
    spill = tmp_path / "unloaded_refs.json"
    report = enforce_budget(s, budget=250, summary_pointer="P1.E1.H900",
                            spill_path=spill)

    assert report.tokens_after <= 250 and report.over_budget is False
    # critical pin survives with its value AND its pointer intact
    assert [p["key"] for p in s.active_pins] == ["capex"]
    assert s.active_pins[0]["value"] == "4.2M EUR"
    assert s.active_pins[0]["source_ref"] == "P1.S0001"
    # the unresolved question survives; the resolved one was unloaded
    assert [q["id"] for q in s.unresolved_questions()] == ["Q1"]
    # every address is still reachable -- now from the spilled ledger
    assert s.dropped_refs == {} and s.unloaded_ledger == "unloaded_refs.json"
    ledger = json.loads(spill.read_text())
    assert ledger["pin"] == ["P1.K002"]
    assert ledger["question"] == ["Q2"]
    assert len(ledger["hex"]) == 39
    assert report.steps[-1].startswith("spilled address ledger")


def test_t6_budget_never_deletes_a_critical_pin_to_fit():
    s = ActiveState(mission="m", current_objective="o")
    s.active_pins = [
        {"pin_id": f"P1.K{i:03d}", "key": f"k{i}", "value": "v" * 200,
         "source_ref": f"P1.S{i:04d}", "critical": True, "status": "ACTIVE"}
        for i in range(1, 20)
    ]
    report = enforce_budget(s, budget=50)
    assert report.over_budget is True          # reported, not hidden
    assert len(s.active_pins) == 19            # nothing required was deleted
    assert s.over_budget is True


# T7 -----------------------------------------------------------------------
def test_t7_cold_fact_recovered_by_address_and_by_query(loaded):
    p, spec, _s1, s2 = loaded
    p.handle_turn("what is the capex ceiling?")

    serialised = json.dumps(p.state.to_dict())
    assert "16 requests per second" not in serialised      # cold: not loaded

    by_address = p.by_address(s2.source_id)
    assert "16 requests per second" in by_address.content

    by_query = p.retrieve("peak throughput morning window")
    assert s2.source_id in by_query.source_ids
    assert p.hexmap.get(spec.hex_id).source_refs.count(s2.source_id) == 1


# T8 -----------------------------------------------------------------------
def test_t8_rotation_is_bounded_and_preserves_authority(loaded):
    p, spec, s1, _ = loaded
    p.state.current_objective = "Choose the exchange fabric."
    p.state.current_summary = "a long running narrative. " * 300
    p.state.add_open_question("Q1", "What is the base period for the mean?")
    p.state.add_open_question("Q2", "Which vendor?")
    p.state.resolve_question("Q2")
    p.state.note_decision(spec.hex_id, "Chose federated replication", s1.source_id)
    p.state.sync_pins(p.pins)
    p.state.touch_hex(spec.hex_id)
    p.retemper()

    before = p.state.tokens()
    t = p.rotate_epoch()

    assert (t.from_epoch, t.to_epoch) == (1, 2)
    assert p.state.epoch == 2
    assert t.handoff_tokens < t.active_state_before      # not a copy
    assert t.active_state_after < before
    assert t.critical_pins_preserved == 1
    assert [pp["key"] for pp in p.state.active_pins] == ["capex_ceiling"]
    assert t.open_questions_preserved == 1
    assert [q["id"] for q in p.state.unresolved_questions()] == ["Q1"]
    # the closing epoch remains addressable
    assert (p.root / t.checkpoint_path).exists()
    assert p.hexmap.get(t.summary_hex).type is HexType.SUMMARY
    assert "a long running narrative" in p.hexmap.get(t.summary_hex).summary
    assert p.state.current_summary == ""                 # not carried forward


def test_t8_rotation_triggers_from_the_ratio_only(tmp_path):
    p = Project.create(tmp_path / "p", name="t", mission="m",
                       active_context_budget_tokens=300)
    p.add_source("spec", "s", "irrelevant filler about widgets and gaskets.")
    p.state.current_summary = "x" * 4000
    turn = p.handle_turn("widgets")
    assert turn.state_update["signal"] == "rotate"
    assert turn.state_update["epoch_transition"]["to_epoch"] == 2


# T9 -----------------------------------------------------------------------
def test_t9_decision_from_an_old_epoch_survives_two_rotations(loaded):
    p, _spec, _s1, _ = loaded
    dec_hex = p.add_hex("Fabric decision", HexType.DECISION, tags=["decision"])
    dec = p.add_source(
        "decision", "ADR-004 exchange fabric",
        "Decision: adopt federated hub-and-spoke replication. "
        "Architecture B (centralised system of record) was rejected.",
        hex_id=dec_hex.hex_id,
    )
    p.state.current_summary = "narrative " * 200
    p.rotate_epoch()
    p.state.current_summary = "more narrative " * 200
    p.rotate_epoch()

    assert p.state.epoch == 3
    hits = p.retrieve("which exchange fabric did we adopt")
    assert dec.source_id in hits.source_ids
    assert p.by_address(dec_hex.hex_id).type is HexType.DECISION
    assert "rejected" in p.by_address(dec.source_id).content


# T10 ----------------------------------------------------------------------
def test_t10_everything_works_with_null_trust_backend(loaded):
    p, spec, s1, _ = loaded
    assert isinstance(p.trust, NullTrustBackend)
    assert p.trust.record("anything", {"a": 1}) is None
    assert p.trust.verify("R0001") is False
    turn = p.handle_turn("capex ceiling")
    assert turn.retrieved_sources
    assert p.rotate_epoch().to_epoch == 2
    assert p.resolve_pin("capex_ceiling").grounded is True


def test_t10_trust_backend_is_a_seam_not_a_dependency(tmp_path):
    from hexashard import InMemoryTrustBackend

    backend = InMemoryTrustBackend()
    Project.create(tmp_path / "p", name="t")
    p2 = Project.open(tmp_path / "p", trust=backend)
    p2.add_source("spec", "s", "content about gaskets")
    assert [e["event"] for e in backend.events] == ["source_added"]
    assert backend.verify("R0001") is True


# T11 ----------------------------------------------------------------------
def test_t11_turn_flow_is_provider_independent(tmp_path, loaded):
    p, _spec, _s1, _ = loaded

    # the core path never touches a provider
    assert p.provider is None
    assert p.handle_turn("capex ceiling").retrieved_sources
    assert p.metrics.model_calls == 0

    mock = MockModelProvider()
    q = Project.open(p.root, provider=mock)
    turn, result = q.generate_reply("what is the capex ceiling?")
    assert result.provider == "mock"
    assert "capex_ceiling" in result.text
    assert q.metrics.model_calls == 1
    assert q.metrics.model_input_tokens > 0
    # deterministic: same context in, same digest out
    _, again = Project.open(p.root, provider=MockModelProvider()).generate_reply(
        "what is the capex ceiling?"
    )
    assert result.text.split()[0] != ""  # digest present
    assert turn.response_context["active_pins"][0]["key"] == "capex_ceiling"


def test_t11_no_vendor_sdk_is_imported(tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    import hexashard

    root = Path(hexashard.__file__).resolve().parents[1]
    out = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, %r); import hexashard; "
         "print(','.join(sorted(m for m in sys.modules "
         "if m.split('.')[0] in ('anthropic','openai','google','ollama','httpx','requests'))))"
         % str(root)],
        capture_output=True, text=True, check=True,
    )
    assert out.stdout.strip() == ""


# T12 ----------------------------------------------------------------------
@pytest.mark.parametrize("weak", [SourceStatus.DRAFT, SourceStatus.UNVERIFIED,
                                  SourceStatus.SUPERSEDED])
def test_t12_weak_authority_never_outranks_current(tmp_path, weak):
    p = Project.create(tmp_path / f"p-{weak.value}", name="t")
    current = p.add_source(
        "spec", "Rev 3 (current)",
        "The dispensing continuity requirement is 72 hours.",
        claim_key="continuity",
    )
    # the weak source is a much better lexical match on purpose
    p.add_source(
        "draft", f"{weak.value} candidate",
        "dispensing continuity requirement continuity dispensing requirement "
        "continuity hours dispensing continuity requirement 96 hours.",
        status=weak,
    )
    res = p.retrieve(
        "dispensing continuity requirement",
        RetrievalFilters(statuses=(SourceStatus.CURRENT, weak)),
    )
    assert res.fragments[0].source_id == current.source_id
    assert res.fragments[0].authority > res.fragments[-1].authority
    # and by default the weak source is not returned at all
    default = p.retrieve("dispensing continuity requirement")
    assert default.source_ids == [current.source_id]
