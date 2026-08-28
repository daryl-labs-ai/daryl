"""Regressions for defects found by an adversarial review of this build.

Each test names the claim that was falsified and pins the corrected behaviour,
so the defect cannot return quietly.
"""

import json
import os

import pytest

from hexashard import (
    HexType, PinStatus, Project, RetrievalFilters, SourceStatus, enforce_budget,
)
from hexashard.context import ActiveState, build_handoff, trim_handoff
from hexashard.store import address_sort_key


# R1 — "everything removed leaves an address behind" -----------------------
def test_r1_summary_is_addressable_before_it_is_compacted(tmp_path):
    p = Project.create(tmp_path / "p", name="t", mission="m",
                       active_context_budget_tokens=300, rotation_threshold=9.9)
    p.add_source("spec", "s", "gasket tolerance is 0.4 mm")
    p.state.current_summary = "UNIQUE-TAIL-MARKER " + ("narrative " * 400)
    turn = p.handle_turn("gasket tolerance")

    pointer = p.state.summary_hex
    assert pointer, "compaction ran with no addressable copy of the summary"
    assert "UNIQUE-TAIL-MARKER" in p.hexmap.get(pointer).summary
    assert pointer in p.state.unloaded("summary") or p.state.unloaded_ledger
    assert len(p.state.current_summary) < 800
    assert any("summary" in s for s in turn.state_update["budget"]["steps"])
    # and it survives a restart
    assert "UNIQUE-TAIL-MARKER" in Project.open(p.root).hexmap.get(pointer).summary


def test_r1_standalone_ladder_refuses_to_destroy_an_unaddressed_summary():
    s = ActiveState(mission="m", current_objective="o")
    s.current_summary = "IRREPLACEABLE " * 400
    report = enforce_budget(s, budget=100)          # no summary_pointer given
    assert "IRREPLACEABLE" in s.current_summary
    assert report.over_budget is True
    assert any("no addressable copy" in step for step in report.steps)


# R2 — "the handoff is strictly smaller than the state it replaces" --------
def test_r2_handoff_never_injects_material_the_state_did_not_have(tmp_path):
    """It used to seed hexmap_refs from the project's HOT/WARM set, which could
    make a handoff *larger* than the state it replaced."""
    p = Project.create(tmp_path / "p", name="t", mission="m")
    for i in range(30):
        h = p.add_hex(f"Area {i}", HexType.SOURCE)
        p.state.touch_hex(h.hex_id)
    p.retemper()
    loaded = list(p.state.active_hex_refs)
    p.state.active_hex_refs = loaded[:2]            # only two are really loaded
    t = p.rotate_epoch()

    handoff = json.loads((p.root / "epochs" / "E1.handoff.json").read_text())
    assert set(handoff["hexmap_refs"]) <= set(loaded[:2])
    assert t.handoff_tokens <= t.active_state_before + 40   # no injection

    # and on a state with something to shed, it is dramatically smaller
    p.state.current_summary = "narrative " * 400
    p.state.active_hex_refs = loaded
    before = p.state.tokens(p.counter)
    t2 = p.rotate_epoch()
    assert t2.handoff_tokens < before / 2


def test_r2_trim_handoff_sheds_only_recoverable_material():
    h = build_handoff(
        ActiveState(mission="m", current_objective="o",
                    active_pins=[{"pin_id": "P1.K001", "key": "k", "value": "v",
                                  "source_ref": "P1.S0001", "critical": True}],
                    open_questions=[{"id": "Q1", "text": "why", "resolved": False}],
                    active_hex_refs=[f"P1.E1.H{i:03d}" for i in range(1, 20)]),
        [], summary_hex=None,
    )
    trimmed = trim_handoff(dict(h), 60)
    assert trimmed["critical_pins"] and trimmed["open_questions"]
    assert trimmed["hexmap_refs_omitted"] > h["hexmap_refs_omitted"]


# R3 — an oversized irreducible core must not cause an epoch storm --------
def test_r3_no_rotation_storm_when_rotation_cannot_help(tmp_path):
    p = Project.create(tmp_path / "p", name="t", mission="m",
                       active_context_budget_tokens=300)
    s = p.add_source("spec", "s", "content about gaskets")
    for i in range(12):
        p.pin(f"binding_{i}", "v" * 200, s.source_id, critical=True)

    signals = []
    for _ in range(5):
        signals.append(p.handle_turn("gaskets").state_update["signal"])

    assert signals == ["saturated"] * 5
    assert p.state.epoch == 1
    assert p.state.over_budget is True             # reported, not hidden
    assert list((p.root / "epochs").glob("*.json")) == []
    assert len(p.pins.critical()) == 12            # nothing was quietly dropped


# R4 — reconciliation must not adopt a value from a non-CURRENT source ----
@pytest.mark.parametrize("weak", [SourceStatus.DRAFT, SourceStatus.UNVERIFIED])
def test_r4_reconcile_refuses_a_non_current_successor(tmp_path, weak):
    p = Project.create(tmp_path / f"p-{weak.value}", name="t")
    old = p.add_source("spec", "rev 1", "The ceiling is 4.2M.",
                       claim_key="capex", claim_value="4.2M")
    p.pin("capex", "4.2M", old.source_id, critical=True)
    new = p.add_source("draft", "rev 2", "The ceiling is 999M.", status=weak,
                       claim_key="capex", claim_value="999M")
    p.sources.supersede(old.source_id, new.source_id)
    p.sources.set_status(new.source_id, weak)      # successor is not authoritative

    [rec] = p.reconcile_pins()
    assert rec.after is PinStatus.NEEDS_REVIEW
    assert rec.value_changed is False
    assert "is not CURRENT" in rec.detail
    assert p.pins.by_key("capex").value == "4.2M"


# R5 — ambiguity detection must be structural, not score-gated ------------
def test_r5_ambiguity_found_even_when_the_rival_shares_no_vocabulary(tmp_path):
    p = Project.create(tmp_path / "p", name="t")
    a = p.add_source("note", "A", "The retention sweeper residual risk is moderate.",
                     claim_key="sweeper_risk")
    b = p.add_source("note", "B", "Nothing here matches the question at all.",
                     claim_key="sweeper_risk")
    res = p.retrieve("retention sweeper residual risk")
    assert res.source_ids == [a.source_id]         # b never scored...
    assert [x.claim_key for x in res.ambiguities] == ["sweeper_risk"]
    assert res.ambiguities[0].source_ids == sorted([a.source_id, b.source_id])


# R6 / R7 — durability without an explicit close --------------------------
def test_r6_authoring_is_durable_without_close(tmp_path):
    root = tmp_path / "p"
    p = Project.create(root, name="t", mission="m")
    h = p.add_hex("Specs", HexType.SOURCE)
    s = p.add_source("spec", "brief", "The limit is 90 seconds.", hex_id=h.hex_id)
    p.pin("limit", "90 seconds", s.source_id, critical=True)
    p.relate(h.hex_id, "REFERENCES", h.hex_id)
    del p                                           # no close(), no save()

    q = Project.open(root)
    assert len(q.hexmap) == 1 and len(q.pins) == 1 and len(q.relations) == 1
    assert q.pins.by_key("limit").value == "90 seconds"
    assert q.hexmap.get(h.hex_id).source_refs == [s.source_id]


def test_r7_rotation_is_durable(tmp_path):
    root = tmp_path / "p"
    p = Project.create(root, name="t", mission="m")
    p.state.current_summary = "narrative " * 200
    t = p.rotate_epoch()
    del p

    q = Project.open(root)
    assert q.state.epoch == 2 and q.config.epoch == 2
    assert q.hexmap.get(t.summary_hex).summary.startswith("narrative")
    assert (root / "epochs" / "E1.checkpoint.json").exists()


# R8 — the address ledger must survive an epoch boundary ------------------
def test_r8_ledger_pointer_survives_rotation(tmp_path):
    p = Project.create(tmp_path / "p", name="t", mission="m",
                       active_context_budget_tokens=150, rotation_threshold=9.9)
    src = p.add_source("spec", "s", "gaskets and tolerances")
    for i in range(20):
        p.pin(f"k{i}", "v" * 40, src.source_id)
    for i in range(30):
        p.state.touch_hex(f"P1.E1.H{i:03d}")
    p.state.current_summary = "x" * 3000
    p.handle_turn("gaskets")
    assert p.state.unloaded_ledger == "unloaded_refs.json"

    p.config.rotation_threshold = 0.9
    p.rotate_epoch()
    assert p.state.unloaded_ledger == "unloaded_refs.json"
    ledger = json.loads((p.root / "unloaded_refs.json").read_text())
    assert sum(len(v) for v in ledger.values()) > 20


# R9 / R10 — the ladder must not grow the state, or overstate its work ----
def test_r9_compaction_never_increases_the_state():
    s = ActiveState(mission="m" * 400, current_objective="o")
    s.active_hex_refs = [f"P1.E1.H{i:03d}" for i in range(1, 40)]
    before = s.tokens()
    report = enforce_budget(s, budget=10)
    assert report.tokens_after <= before
    assert s.tokens() <= before


def test_r10_steps_only_report_rungs_that_did_something():
    s = ActiveState(mission="m" * 4000, current_objective="o")
    report = enforce_budget(s, budget=10)
    assert report.steps == [] or all("hint" not in x and "question" not in x
                                     for x in report.steps)
    assert report.over_budget is True


# R11 — supersession cycles -----------------------------------------------
def test_r11_supersession_cycle_is_rejected(tmp_path):
    p = Project.create(tmp_path / "p", name="t")
    a = p.add_source("spec", "A", "one")
    b = p.add_source("spec", "B", "two")
    c = p.add_source("spec", "C", "three")
    p.supersede(a.source_id, b.source_id)
    p.supersede(b.source_id, c.source_id)
    with pytest.raises(ValueError, match="cycle"):
        p.supersede(c.source_id, a.source_id)
    assert p.sources.get(c.source_id).status is SourceStatus.CURRENT


def test_r11_a_revert_is_a_new_source_not_a_backwards_edge(tmp_path):
    """Pointing the chain backwards would leave authority genuinely undefined,
    so it is refused; restoring an old position means issuing a new source."""
    p = Project.create(tmp_path / "p", name="t")
    a = p.add_source("spec", "A", "the limit is 90 seconds", claim_key="limit",
                     claim_value="90 seconds")
    b = p.add_source("spec", "B", "the limit is 45 seconds", claim_key="limit",
                     claim_value="45 seconds")
    p.pin("limit", "90 seconds", a.source_id, critical=True)
    p.supersede(a.source_id, b.source_id)
    with pytest.raises(ValueError, match="cycle"):
        p.supersede(b.source_id, a.source_id)

    c = p.add_source("spec", "C (restores A)", "the limit is 90 seconds again",
                     claim_key="limit", claim_value="90 seconds")
    p.supersede(b.source_id, c.source_id)
    head = p.sources.get(c.source_id)
    assert head.status is SourceStatus.CURRENT and head.superseded_by is None
    assert p.sources.current_chain_head(a.source_id).source_id == c.source_id
    assert p.pins.by_key("limit").value == "90 seconds"
    assert p.pins.by_key("limit").source_ref == c.source_id


# R12 — retrieval must report its own overrun -----------------------------
def test_r12_retrieval_reports_going_over_budget(tmp_path):
    p = Project.create(tmp_path / "p", name="t", chunk_chars=100_000)
    p.add_source("spec", "big", "gasket " * 20_000)
    res = p.retrieve("gasket", budget=50)
    assert res.tokens > 50
    assert res.over_budget is True
    turn = p.handle_turn("gasket")
    assert turn.state_update["retrieval_over_budget"] is True
    assert turn.state_update["response_context_tokens"] > 1000


# R13 — addresses must order numerically, not lexically -------------------
def test_r13_addresses_sort_by_epoch_number(tmp_path):
    ids = ["P1.E1.H001", "P1.E10.H001", "P1.E2.H001", "P1.E9.H002", "P1.E9.H001"]
    assert sorted(ids, key=address_sort_key) == [
        "P1.E1.H001", "P1.E2.H001", "P1.E9.H001", "P1.E9.H002", "P1.E10.H001"]

    p = Project.create(tmp_path / "p", name="t", mission="m")
    for _ in range(11):
        p.add_hex("h", HexType.SOURCE)
        p.state.current_summary = "narrative " * 200
        p.rotate_epoch()
    assert p.state.epoch == 12
    order = [h.hex_id for h in p.hexmap.all()]
    assert order == sorted(order, key=address_sort_key)
    assert order[-1].startswith("P1.E11.")


# R16 / R18 — small correctness ------------------------------------------
def test_r16_filters_record_epoch_zero():
    assert RetrievalFilters(epoch=0).to_dict()["epoch"] == 0
    assert RetrievalFilters(statuses=()).effective_statuses() == set()


def test_r18_source_refs_are_not_duplicated(tmp_path):
    p = Project.create(tmp_path / "p", name="t")
    h = p.add_hex("Specs", HexType.SOURCE)
    s = p.add_source("spec", "b", "text", hex_id=h.hex_id)
    p.assign_source(s.source_id, h.hex_id)
    p.assign_source(s.source_id, h.hex_id)
    assert p.hexmap.get(h.hex_id).source_refs == [s.source_id]


# R17 — atomic writes must not tighten permissions -------------------------
def test_r17_atomic_write_preserves_file_mode(tmp_path):
    p = Project.create(tmp_path / "p", name="t")
    p.add_hex("Specs", HexType.SOURCE)
    path = p.root / "hexmap.jsonl"
    os.chmod(path, 0o664)
    p.add_hex("More", HexType.SOURCE)
    assert path.stat().st_mode & 0o777 == 0o664
