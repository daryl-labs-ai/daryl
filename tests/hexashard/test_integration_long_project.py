"""One synthetic long-project integration test (spec section 32).

Architecture validation, not a benchmark.  No model inference is used: the
whole point is that context management is deterministic without it.

    large project store  +  small active state  +  pins preserved
    +  cold retrieval    +  authority semantics +  epoch rotation
"""

from __future__ import annotations

import json
import sys
import os
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hexashard_fixtures.synthetic_project import (  # noqa: E402
    PLANTED,
    QUERIES,
    assert_no_leakage,
    check_frozen,
    filler_sources,
)
from hexashard import (  # noqa: E402
    HexType,
    Project,
    RetrievalFilters,
    SourceStatus,
)

ACTIVE_BUDGET = 6000
RETRIEVAL_BUDGET = 1200
N_TURNS = 260
SUPERSESSION_TURN = 80
#: Measurements are written to a scratch location, never into the source
#: tree. The recorded v0.1 run is frozen in
#: docs/hexashard/evidence/core_integration_results.json.
import tempfile  # noqa: E402

ARTIFACTS = Path(
    os.environ.get("HEXASHARD_ARTIFACTS_DIR")
    or Path(tempfile.gettempdir()) / "hexashard-artifacts"
)
RESULTS = ARTIFACTS / "integration_results.json"

#: what the simulated conversation actually talks about
LOAD_KEYS = {"downlink_budget", "thermal_limit", "adr007", "raster_note", "apogee_note"}

#: hex grouping for the planted material
GROUPS = {
    "Brief and binding constraints": (HexType.CONSTRAINT, ["downlink_budget", "thermal_limit"]),
    "Ground station procedures": (HexType.SOURCE, ["handover_v1"]),
    "Site register": (HexType.REFERENCE, ["kell9_elevation"]),
    "Architecture decisions": (HexType.DECISION, ["adr002", "adr007"]),
    "Validation archive": (HexType.TEST, ["validation_v118"]),
    "Calibration references": (HexType.REFERENCE, ["raster_note", "apogee_note"]),
    "Unapproved material": (HexType.SOURCE, ["draft_downlink", "unverified_thermal"]),
}


def _build(root: Path) -> tuple[Project, dict[str, str]]:
    """Epoch 1: load the whole programme corpus and pin what is binding."""
    p = Project.create(
        root, name="MERIDIAN-9", mission="Deliver the MERIDIAN-9 ground segment.",
        active_context_budget_tokens=ACTIVE_BUDGET,
        retrieval_budget_tokens=RETRIEVAL_BUDGET,
    )
    planted = {x.key: x for x in PLANTED}
    ids: dict[str, str] = {}

    with p.bulk():
        for title, (htype, keys) in GROUPS.items():
            h = p.add_hex(title, htype, tags=[title.split()[0].lower()])
            for key in keys:
                x = planted[key]
                src = p.add_source(
                    x.source_type, x.title, x.content, hex_id=h.hex_id,
                    status=SourceStatus(x.status), tags=list(x.tags),
                    claim_key=x.claim_key, claim_value=x.claim_value,
                )
                ids[key] = src.source_id

        archive = p.add_hex("Facilities archive", HexType.ARTIFACT, tags=["archive"])
        filler = filler_sources()
        assert_no_leakage(filler)
        for title, body in filler:
            p.add_source("minutes", title, body, hex_id=archive.hex_id,
                         tags=["facilities"])

    # a decision that has already been revised, before the conversation starts
    p.supersede(ids["adr002"], ids["adr007"])
    p.relate("P1.E1.H004", "DECIDES", "P1.E1.H001")
    p.relate("P1.E1.H005", "TESTS", "P1.E1.H002")

    p.pin("downlink_budget", "4.7 Gb/pass", ids["downlink_budget"], critical=True)
    p.pin("thermal_cycling_limit", "180 cycles per annum", ids["thermal_limit"], critical=True)
    p.pin("handover_window", "90 seconds", ids["handover_v1"], critical=True)
    p.pin("primary_site", "KELL-9", ids["kell9_elevation"], critical=False)

    for h in p.hexmap.all():
        p.hexmap.recompute_size(h.hex_id, p.sources, p.pins, p.relations, p.counter)
    p.state.current_objective = "Confirm the binding telemetry constraints."
    p.save()
    return p, ids


def _turn_note(n: int, query: str, turn) -> str:
    """A realistic running-summary line: what was asked, and what grounded it."""
    frags = turn.retrieved_sources
    if not frags:
        return f"T{n}: asked {query!r}; nothing authoritative was found."
    top = frags[0]
    return (f"T{n}: asked {query!r}; grounded in {top['source_id']} "
            f"({top['source_title']}): {top['text'][:200]}")


@pytest.mark.integration
def test_long_project_keeps_a_small_working_set(tmp_path):
    check_frozen()
    root = tmp_path / "meridian9"

    # -- phase 1: build -------------------------------------------------
    p, ids = _build(root)
    project_total_tokens = p.sources.total_tokens(p.counter)
    assert 100_000 <= project_total_tokens <= 250_000

    # -- phase 2: 120 conversational turns ------------------------------
    # The conversation only ever asks about the live constraints and the
    # current decision.  KELL-9, V-118 and the handover history are never
    # discussed during these 260 turns, so at scoring time they are genuinely
    # cold: absent from the working set, reachable only by address or query.
    load_queries = [q for q in QUERIES if q.expect_key in LOAD_KEYS]
    active_series: list[int] = []
    pending_note: str | None = None
    for n in range(1, N_TURNS + 1):
        if n == SUPERSESSION_TURN:
            # a live revision mid-conversation: new source, explicit
            # supersession, automatic reconciliation of a *critical* pin
            x = {y.key: y for y in PLANTED}["handover_v2"]
            new = p.add_source(x.source_type, x.title, x.content,
                               hex_id="P1.E1.H002", tags=list(x.tags),
                               claim_key=x.claim_key, claim_value=x.claim_value)
            ids["handover_v2"] = new.source_id
            outcome = p.supersede(ids["handover_v1"], new.source_id)
            assert outcome["pin_reconciliations"], "critical pin was not reconciled"

        q = load_queries[(n - 1) % len(load_queries)]
        # the previous turn's note goes in through the API, so the recorded
        # active-state size includes the running summary it grows
        turn = p.handle_turn(q.text, summary_append=pending_note)
        pending_note = _turn_note(n, q.text, turn)
        active_series.append(turn.state_update["active_state_tokens"])
        if n % 10 == 0:
            p.state.add_open_question(f"Q{n}", f"Follow up on turn {n}: {q.text}")
            active_series.append(p.state.tokens(p.counter))
    p.close()

    # -- phase 3: restart from disk -------------------------------------
    q = Project.open(root)
    assert q.state.epoch >= 3, f"expected several rotations, got epoch {q.state.epoch}"

    # -- phase 4: scored queries, after rotation, on the reloaded project -
    key_of = {v: k for k, v in ids.items()}
    retrieval_hits = authority_hits = authority_total = 0
    detail = []
    for query in QUERIES:
        if query.kind == "historical":
            res = q.retrieve(query.text, RetrievalFilters(statuses=(SourceStatus.SUPERSEDED,)))
        else:
            res = q.retrieve(query.text)
        found = [key_of.get(s, s) for s in res.source_ids]
        ok_retrieval = query.expect_key in found
        retrieval_hits += ok_retrieval

        ok_authority = None
        if query.kind in ("authority", "historical"):
            authority_total += 1
            first_ok = bool(found) and found[0] == query.expect_key
            no_forbidden = not (set(query.forbid_keys) & set(found))
            status_ok = (
                res.fragments[0].source_status
                == ("SUPERSEDED" if query.kind == "historical" else "CURRENT")
            ) if res.fragments else False
            ok_authority = first_ok and no_forbidden and status_ok
            authority_hits += ok_authority
        detail.append({"query": query.text, "kind": query.kind,
                       "expected": query.expect_key, "returned": found[:3],
                       "retrieval_ok": ok_retrieval, "authority_ok": ok_authority})

    retrieval_accuracy = retrieval_hits / len(QUERIES)
    authority_accuracy = authority_hits / authority_total

    # -- phase 5: the properties this test exists to demonstrate ---------
    state_blob = json.dumps(q.state.to_dict())
    active_state_peak = max(active_series)

    # large store, small working set
    assert active_state_peak <= ACTIVE_BUDGET
    assert project_total_tokens / active_state_peak > 25

    # critical pins planted in epoch 1 survived every rotation, values intact
    live = {pin.key: pin for pin in q.pins.live()}
    assert live["downlink_budget"].value == "4.7 Gb/pass"
    assert live["thermal_cycling_limit"].value == "180 cycles per annum"
    assert all(p_.critical for p_ in (live["downlink_budget"], live["thermal_cycling_limit"]))
    assert q.resolve_pin("downlink_budget").grounded is True
    assert q.resolve_pin("downlink_budget").source.status is SourceStatus.CURRENT
    # the pin superseded mid-conversation was repointed and re-valued
    assert live["handover_window"].value == "45 seconds"
    assert live["handover_window"].source_ref == ids["handover_v2"]

    # cold retrieval: never loaded, still reachable
    assert "41 millisecond" not in state_blob
    assert ids["validation_v118"] in q.retrieve("validation run p99 frame latency").source_ids
    assert "2410 metres" not in state_blob
    assert q.by_address(ids["kell9_elevation"]).content.count("2410 metres") == 1

    # the early critical fact, asked long after the epoch it was created in
    early = q.retrieve("what is the telemetry downlink budget per pass")
    assert early.source_ids[0] == ids["downlink_budget"]
    assert q.hexmap.get("P1.E1.H001").epoch == 1 and q.state.epoch >= 3

    assert retrieval_accuracy == 1.0
    assert authority_accuracy == 1.0

    # -- measurements ----------------------------------------------------
    m = q.measurements()
    transitions = q.epoch_transitions()
    results = {
        "fixture": check_frozen(),
        "config": {"active_context_budget_tokens": ACTIVE_BUDGET,
                   "retrieval_budget_tokens": RETRIEVAL_BUDGET,
                   "turns": N_TURNS, "supersession_turn": SUPERSESSION_TURN},
        "project_total_tokens": project_total_tokens,
        "active_state_peak_tokens": active_state_peak,
        "active_state_final_tokens": q.state.tokens(q.counter),
        "active_state_mean_tokens": round(sum(active_series) / len(active_series), 1),
        "store_to_active_ratio": round(project_total_tokens / active_state_peak, 1),
        "retrieval_tokens": p.metrics.retrieval_tokens,
        "retrieval_count": p.metrics.retrieval_count,
        "retrieval_tokens_mean": round(p.metrics.retrieval_tokens / p.metrics.retrieval_count, 1),
        "epoch_count": q.state.epoch,
        "epoch_rotations": len(transitions),
        "turns_per_epoch": [t["turns_in_epoch"] for t in transitions],
        "handoff_tokens": [t["handoff_tokens"] for t in transitions],
        "active_state_before_rotation": [t["active_state_before"] for t in transitions],
        "active_state_after_rotation": [t["active_state_after"] for t in transitions],
        "pin_count": len(q.pins.live()),
        "critical_pin_count": len(q.pins.critical()),
        "hot_hex_count": m["hot_hex_count"],
        "warm_hex_count": m["warm_hex_count"],
        "cold_hex_count": m["cold_hex_count"],
        "hex_count": m["hex_count"],
        "source_count": m["source_count"],
        "fragment_count": m["fragment_count"],
        "hexmap_index_tokens": m["hexmap_index_tokens"],
        "model_calls": m["model_calls"],
        "model_input_tokens": m["model_input_tokens"],
        "model_output_tokens": m["model_output_tokens"],
        "retrieval_accuracy": retrieval_accuracy,
        "authority_accuracy": authority_accuracy,
        "query_detail": detail,
    }
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(results, indent=2) + "\n")

    # every rotation was genuinely bounded, not a copy
    for t in transitions:
        assert t["handoff_tokens"] < t["active_state_before"]
        assert t["critical_pins_preserved"] == 3
    assert m["model_calls"] == 0          # no inference was needed anywhere
