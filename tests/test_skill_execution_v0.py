from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from eval.skill_execution_v0 import (
    MAX_SCORE,
    compose_skill_trace,
    score_skill_trace,
    score_trace_determinism,
)
from eval.skill_retrieval_v0 import load_records, retrieve_skill_context


REPO_ROOT = Path(__file__).resolve().parents[1]
RECORDS_PATH = REPO_ROOT / "datasets" / "dsm_reasoning_v0" / "records.jsonl"
EXECUTION_PATH = REPO_ROOT / "eval" / "skill_execution_v0" / "execution.py"
FORBIDDEN_OVERPROMISE = (
    "guaranteed",
    "proven",
    "final decision",
    "verified truth",
    "model learned",
    "trained",
)


def test_compose_skill_trace_golden_path():
    context = _retrieved_context()
    trace = compose_skill_trace(context, _query())

    assert trace["trace_type"] == "skill_execution_trace.v0"
    assert trace["user_id"] == "mohamed"
    assert trace["domain"] == "omari_ai"
    assert trace["skill_id"] == "omari_ai.lead_capture_reliability"
    assert trace["required_checks"]
    assert trace["applied_validated_rules"]
    assert trace["candidate_rules"]
    assert trace["supporting_cases"]
    assert trace["trust_model"]["mode"] == "deterministic_scaffold"
    assert trace["trust_model"]["decision_status"] == "not_produced"
    assert trace["decision_scaffold"]["status"] == "requires_reasoner"
    assert trace["missing_checks"] == ["external_evidence_limit_disclosed"]
    assert _warning_checks(trace) == {"external_evidence_limit_disclosed"}


def test_candidate_rules_are_separate_and_not_applied():
    trace = _trace()

    applied_ids = _ids(trace["applied_validated_rules"])
    candidate_ids = _ids(trace["candidate_rules"])

    assert candidate_ids
    assert candidate_ids.isdisjoint(applied_ids)
    assert all(rule["applied"] is False for rule in trace["candidate_rules"])
    assert all(
        rule["rule_status"] == "candidate_rule"
        for rule in trace["candidate_rules"]
    )


def test_missing_checks_are_surfaced_as_missing_and_warning():
    trace = _trace()
    required_by_name = {item["check"]: item for item in trace["required_checks"]}

    item = required_by_name["external_evidence_limit_disclosed"]

    assert item["status"] == "missing"
    assert "external_evidence_limit_disclosed" in trace["missing_checks"]
    assert "external_evidence_limit_disclosed" in _warning_checks(trace)


def test_trace_contains_no_overpromise_wording():
    serialized = json.dumps(_trace(), sort_keys=True).lower()

    for phrase in FORBIDDEN_OVERPROMISE:
        assert phrase not in serialized


def test_end_to_end_user_isolation():
    trace = _trace()
    entries = _trace_entries(trace)

    assert "skill-04-other-user-omari-lead-capture-rule" not in _ids(entries)
    assert all(entry["user_id"] == "mohamed" for entry in entries)


def test_end_to_end_domain_and_skill_isolation():
    trace = _trace()
    entries = _trace_entries(trace)

    assert "skill-06-billing-refund-case" not in _ids(entries)
    assert all(entry["domain"] == "omari_ai" for entry in entries)
    assert all(
        entry["skill_id"] == "omari_ai.lead_capture_reliability"
        for entry in entries
    )


def test_compose_skill_trace_is_deterministic():
    context = _retrieved_context()
    reversed_context = deepcopy(context)
    reversed_context["validated_rules"] = list(reversed(context["validated_rules"]))
    reversed_context["candidate_rules"] = list(reversed(context["candidate_rules"]))
    reversed_context["cases"] = list(reversed(context["cases"]))

    first = compose_skill_trace(context, _query())
    second = compose_skill_trace(reversed_context, _query())
    determinism = score_trace_determinism(first, second)

    assert first == second
    assert determinism["score"] == MAX_SCORE
    assert determinism["penalties"] == []


def test_score_skill_trace_golden_scores_cleanly():
    context = _retrieved_context()
    trace = compose_skill_trace(context, _query())

    result = score_skill_trace(trace, context)

    assert result["score"] == MAX_SCORE
    assert result["penalties"] == []


def test_score_penalizes_candidate_rule_moved_to_applied_rules():
    context = _retrieved_context()
    trace = _trace()
    trace["applied_validated_rules"].append(deepcopy(trace["candidate_rules"][0]))

    result = score_skill_trace(trace, context)

    assert "candidate_rule_auto_promoted" in _penalty_codes(result)
    assert result["score"] < MAX_SCORE


def test_score_penalizes_missing_check_not_surfaced():
    context = _retrieved_context()
    trace = _trace()
    trace["missing_checks"] = []
    trace["warnings"] = []

    result = score_skill_trace(trace, context)

    codes = _penalty_codes(result)
    assert "missing_check_not_listed" in codes
    assert "missing_check_without_warning" in codes
    assert result["score"] < MAX_SCORE


def test_score_penalizes_overpromise_wording():
    context = _retrieved_context()
    trace = _trace()
    trace["trust_model"]["limitations"].append(
        "This is a guaranteed final decision."
    )

    result = score_skill_trace(trace, context)

    assert "overpromise_wording" in _penalty_codes(result)
    assert result["score"] < MAX_SCORE


def test_score_penalizes_user_leak():
    context = _retrieved_context()
    trace = _trace()
    trace["supporting_cases"].append(
        {
            "id": "skill-04-other-user-omari-lead-capture-rule",
            "user_id": "other_user",
            "domain": "omari_ai",
            "skill_id": "omari_ai.lead_capture_reliability",
        }
    )

    result = score_skill_trace(trace, context)

    assert "user_scope_leak" in _penalty_codes(result)
    assert result["score"] < MAX_SCORE


def test_score_penalizes_wrong_domain_and_skill():
    context = _retrieved_context()
    trace = _trace()
    trace["supporting_cases"][0]["domain"] = "billing_ops"
    trace["supporting_cases"][0]["skill_id"] = "billing_ops.refund_triage"

    result = score_skill_trace(trace, context)

    codes = _penalty_codes(result)
    assert "domain_scope_leak" in codes
    assert "skill_scope_leak" in codes
    assert result["score"] < MAX_SCORE


def test_score_penalizes_missing_trust_model():
    context = _retrieved_context()
    trace = _trace()
    del trace["trust_model"]

    result = score_skill_trace(trace, context)

    assert "missing_trust_model" in _penalty_codes(result)
    assert result["score"] < MAX_SCORE


def test_score_penalizes_fabricated_business_decision():
    context = _retrieved_context()
    trace = _trace()
    trace["trust_model"]["decision_status"] = "produced"
    trace["decision_scaffold"]["status"] = "produced"

    result = score_skill_trace(trace, context)

    codes = _penalty_codes(result)
    assert "decision_status_not_produced" in codes
    assert "decision_scaffold_not_pending_reasoner" in codes
    assert result["score"] < MAX_SCORE


def test_execution_code_is_static_and_kernel_free():
    source = EXECUTION_PATH.read_text(encoding="utf-8")

    forbidden_fragments = (
        "from dsm." + "core",
        "import dsm." + "core",
        "Stor" + "age",
        "core." + "storage",
    )
    for fragment in forbidden_fragments:
        assert fragment not in source


def _retrieved_context() -> dict:
    return retrieve_skill_context(
        load_records(RECORDS_PATH),
        user_id="mohamed",
        domain="omari_ai",
        skill_id="omari_ai.lead_capture_reliability",
        task_type="prioritization_decision",
    )


def _query() -> dict:
    return {
        "user_id": "mohamed",
        "domain": "omari_ai",
        "skill_id": "omari_ai.lead_capture_reliability",
        "task_type": "prioritization_decision",
        "known_inputs": {
            "customer_name": "Before",
            "interruption_detected": True,
            "phone_number": None,
            "denial_reason": None,
        },
    }


def _trace() -> dict:
    return compose_skill_trace(_retrieved_context(), _query())


def _trace_entries(trace: dict) -> list[dict]:
    return [
        *trace["applied_validated_rules"],
        *trace["candidate_rules"],
        *trace["supporting_cases"],
    ]


def _ids(entries: list[dict]) -> set[str]:
    return {entry["id"] for entry in entries}


def _warning_checks(trace: dict) -> set[str]:
    return {
        warning["check"]
        for warning in trace["warnings"]
        if warning.get("code") == "missing_required_check"
    }


def _penalty_codes(result: dict) -> set[str]:
    return {penalty["code"] for penalty in result["penalties"]}
