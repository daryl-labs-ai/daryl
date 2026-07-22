"""B4 — mechanical campaign: 12 cases × A/B′/B, validity gates, report.

Asserts the campaign's frozen properties: all 36 runs valid and eligible (no
confounded pair in the deterministic regime), zero false negatives AND zero
false positives for B's replay against the planted-fault oracle, the honest
symmetry result (A's rubric detects the same mechanical set in this regime),
c07's dissociation (valid run, zero diagnostics, failing outcome is an oracle
matter), overhead accounting (B pays grounding-block tokens, B′ pays zero),
per-case report rows never masked by aggregates, and byte-determinism of the
whole campaign report.
"""

from __future__ import annotations

import json

from benchmarks.swarm.harness.campaign import CONDITIONS, run_campaign
from benchmarks.swarm.harness.cases import load_cases

N_CASES = 12


def test_campaign_runs_all_cases_and_writes_report(tmp_path):
    report = run_campaign(tmp_path / "campaign")
    assert report.n_cases == N_CASES
    assert (tmp_path / "campaign" / "campaign_report.json").exists()
    md = (tmp_path / "campaign" / "REPORT.md").read_text()
    # per-case rows are the primary output — one row per case, none masked
    for case in load_cases():
        assert f"| {case.case_id} |" in md
    assert "Aggregates (descriptive only" in md
    assert "validity condition" in md  # verify==OK stated as validity, not score


def test_all_runs_valid_and_eligible(tmp_path):
    report = run_campaign(tmp_path / "c")
    for e in report.evaluations:
        assert all(v.valid for v in e.validity.values()), e.case_id
        assert e.stratum == {"Bprime": "eligible", "B": "eligible"}, e.case_id
        for parity in e.parity.values():
            assert parity.prompt_hash_verification is True
            assert parity.call_sequence_divergence == 0.0
            assert parity.retries_delta == 0
            assert parity.unmatched_steps == ()
    agg = report.aggregates
    assert agg["runs_valid"] == agg["runs_total"] == 3 * N_CASES
    assert agg["pairs_confounded"] == 0


def test_b_replay_matches_oracle_exactly(tmp_path):
    report = run_campaign(tmp_path / "c")
    for e in report.evaluations:
        assert e.false_negatives_b == (), e.case_id
        assert e.false_positives_b == (), e.case_id
        # B′ structures the same records — identical replay observation
        assert e.observed_bprime_replay == e.observed_b_replay, e.case_id
    assert report.aggregates["false_negatives_b"] == 0
    assert report.aggregates["false_positives_b"] == 0


def test_honest_symmetry_a_rubric_equals_b_replay_in_this_regime(tmp_path):
    """The deterministic regime's honest finding: same declared payloads in
    every condition ⇒ A's mechanical rubric detects the same set as B's
    replay. This validates measurement symmetry; it is NOT a live result."""
    report = run_campaign(tmp_path / "c")
    for e in report.evaluations:
        assert e.false_negatives_a == (), e.case_id
        assert e.false_positives_a == (), e.case_id
        assert set(e.detected_a_rubric) == set(e.expected_mechanical), e.case_id


def test_c07_dissociation_valid_run_zero_diagnostics(tmp_path):
    report = run_campaign(tmp_path / "c")
    e = next(x for x in report.evaluations if x.case_id == "c07-false-result-coherent-trace")
    assert all(v.valid for v in e.validity.values())
    assert e.observed_b_replay == () and e.detected_a_rubric == ()
    assert e.stratum["B"] == "eligible"


def test_overhead_accounting(tmp_path):
    report = run_campaign(tmp_path / "c")
    for e in report.evaluations:
        # B pays the grounding block on every agent step; B′ pays zero tokens
        assert e.overhead["B"].tokens_in_delta > 0, e.case_id
        assert e.overhead["Bprime"].tokens_in_delta == 0, e.case_id
        assert e.overhead["Bprime"].call_count_delta == 0
        assert e.overhead["B"].call_count_delta == 0
        # records and shard bytes are real and equal across B′/B
        assert e.overhead["B"].records_written == e.overhead["Bprime"].records_written > 0
        assert e.overhead["B"].shard_bytes > 0
    assert report.aggregates["total_tokens_in_delta_bprime"] == 0
    assert report.aggregates["total_tokens_in_delta_b"] > 0


def test_family_c_identical_across_conditions_same_declarations(tmp_path):
    """Family C reads DECLARED information (tier i/ii) — identical payloads in
    every condition ⇒ identical values; nothing here claims work happened."""
    report = run_campaign(tmp_path / "c")
    for e in report.evaluations:
        assert e.family_c["A"] == e.family_c["Bprime"] == e.family_c["B"], e.case_id
    c02 = next(e for e in report.evaluations if e.case_id == "c02-checks-uncovered")
    assert c02.family_c["A"].claimed_vs_observable_gap == 1.0  # claimed pytest, no actual
    c10 = next(e for e in report.evaluations if e.case_id == "c10-no-required-checks")
    assert c10.family_c["A"].coverage_ratios["work:1"] is None  # undefined, not 1.0
    c12 = next(e for e in report.evaluations if e.case_id == "c12-limitations-ignored")
    assert c12.family_c["A"].limitations_declared == 1


def test_campaign_report_byte_deterministic(tmp_path):
    run_campaign(tmp_path / "r1")
    run_campaign(tmp_path / "r2")
    j1 = (tmp_path / "r1" / "campaign_report.json").read_bytes()
    j2 = (tmp_path / "r2" / "campaign_report.json").read_bytes()
    assert j1 == j2
    assert (tmp_path / "r1" / "REPORT.md").read_bytes() == (tmp_path / "r2" / "REPORT.md").read_bytes()
    # sanity: the JSON parses and carries all 12 evaluations
    doc = json.loads(j1)
    assert len(doc["evaluations"]) == N_CASES
