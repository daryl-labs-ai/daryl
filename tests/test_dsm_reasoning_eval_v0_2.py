from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from eval.dsm_reasoning_eval_v0_2 import scorer


REPO_ROOT = Path(__file__).resolve().parents[1]
RECORDS_PATH = REPO_ROOT / "datasets" / "dsm_reasoning_v0" / "records.jsonl"
SCORER_PATH = REPO_ROOT / "eval" / "dsm_reasoning_eval_v0_2" / "scorer.py"


def test_golden_dataset_records_score_perfectly():
    records = scorer.load_records(RECORDS_PATH)

    results = [
        scorer.score_record(record, scorer.golden_candidate_for_record(record))
        for record in records
    ]

    assert len(results) == 7
    assert all(result["score"] == scorer.MAX_SCORE for result in results)
    assert all(result["penalties"] == [] for result in results)


def test_corrupted_reasoning_trace_penalizes_missing_trust_and_overpromise():
    record = _record_by_id("dogfood-01-used-board")
    candidate = deepcopy(scorer.golden_candidate_for_record(record))
    candidate["markdown"] = (
        "# Agent Memory Audit Report\n"
        "DSM is a cryptographic proof of truth and the facts are proven true."
    )

    result = scorer.score_record(record, candidate)

    codes = _penalty_codes(result)
    assert "missing_trust_model" in codes
    assert "overpromise_truth" in codes
    assert result["score"] < scorer.MAX_SCORE


def test_corrupted_missing_dependency_penalizes_missing_warning():
    record = _record_by_id("negative-missing-dependency")
    candidate = deepcopy(scorer.golden_candidate_for_record(record))
    candidate["json"]["warnings"] = []

    result = scorer.score_record(record, candidate)

    assert "missing_warning_missing_dependency" in _penalty_codes(result)
    assert result["score"] < scorer.MAX_SCORE


def test_corrupted_cycle_penalizes_missing_warning():
    record = _record_by_id("negative-cycle")
    candidate = deepcopy(scorer.golden_candidate_for_record(record))
    candidate["json"]["warnings"] = []

    result = scorer.score_record(record, candidate)

    assert "missing_warning_cycle_detected" in _penalty_codes(result)
    assert result["score"] < scorer.MAX_SCORE


def test_skill_memory_missing_required_check_and_auto_promotion_are_penalized():
    record = _record_by_id("skill-01-omari-lead-capture-correction")
    candidate = deepcopy(scorer.golden_candidate_for_record(record))
    skill_memory = candidate["skill_memory"]
    skill_memory["required_checks"] = [
        check
        for check in skill_memory["required_checks"]
        if check != "bug_before_feature"
    ]
    skill_memory["epistemic_status"] = "validated_rule"
    skill_memory["correction"]["epistemic_status"] = "validated_rule"
    skill_memory["skill_rule_updates"][0]["status"] = "validated"

    result = scorer.score_record(record, candidate)

    codes = _penalty_codes(result)
    assert "missing_required_check" in codes
    assert "correction_not_candidate_rule" in codes
    assert "correction_promoted" in codes
    assert "auto_promotion" in codes
    assert result["score"] < scorer.MAX_SCORE


def test_user_scoped_records_excludes_other_and_unscoped_users_by_default():
    records = [
        {
            "id": "skill-mohamed",
            "record_kind": "skill_memory_entry",
            "user_id": "mohamed",
        },
        {
            "id": "skill-other",
            "record_kind": "skill_memory_entry",
            "user_id": "other_user",
        },
        {
            "id": "global-template",
            "record_kind": "skill_memory_entry",
        },
    ]

    scoped = scorer.user_scoped_records(records, user_id="mohamed")
    isolation_result = scorer.score_user_isolation(
        user_id="mohamed",
        returned_records=[records[1], records[2]],
    )

    assert [record["id"] for record in scoped] == ["skill-mohamed"]
    codes = _penalty_codes(isolation_result)
    assert "cross_user_record_returned" in codes
    assert "unscoped_record_returned" in codes


def test_raw_runtime_hash_is_penalized():
    record = _record_by_id("dogfood-02-omari-lead-capture")
    candidate = deepcopy(scorer.golden_candidate_for_record(record))
    candidate["json"]["decision"]["entry_hash"] = "v1:" + "a" * 64

    result = scorer.score_record(record, candidate)

    assert "raw_hash" in _penalty_codes(result)
    assert result["score"] < scorer.MAX_SCORE


def test_eval_harness_is_static_and_kernel_free():
    source = SCORER_PATH.read_text(encoding="utf-8")

    forbidden_fragments = (
        "from dsm." + "core",
        "import dsm." + "core",
        "Stor" + "age",
        "core." + "storage",
    )
    for fragment in forbidden_fragments:
        assert fragment not in source


def test_eval_harness_cli_scores_golden_records_successfully(capsys):
    assert scorer.main([str(RECORDS_PATH)]) == 0

    output = capsys.readouterr().out
    assert '"record_id": "skill-01-omari-lead-capture-correction"' in output
    assert '"score": 100.0' in output


def _record_by_id(record_id: str) -> dict:
    records = scorer.load_records(RECORDS_PATH)
    return next(record for record in records if record["id"] == record_id)


def _penalty_codes(result: dict) -> set[str]:
    return {penalty["code"] for penalty in result["penalties"]}
