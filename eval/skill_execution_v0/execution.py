#!/usr/bin/env python3
"""Deterministic skill execution trace composition and scoring."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


MAX_SCORE = 100.0
SEVERITY_POINTS = {
    "low": 5.0,
    "medium": 15.0,
    "high": 30.0,
}
OVERPROMISE_PHRASES = (
    "guaranteed",
    "proven",
    "final decision",
    "verified truth",
    "model learned",
    "trained",
    "decided",
)
CHECK_INPUT_KEYS = {
    "known_context_not_reasked": ("customer_name", "known_context_not_reasked"),
    "persistence_failure_checked": (
        "interruption_detected",
        "persistence_failure_checked",
    ),
    "bug_before_feature": ("interruption_detected", "bug_before_feature"),
    "external_evidence_limit_disclosed": (
        "external_evidence_limit_disclosed",
        "evidence_limit_disclosed",
    ),
}


@dataclass(frozen=True)
class Penalty:
    code: str
    message: str
    severity: str

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
        }


def compose_skill_trace(
    retrieved_context: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    known_inputs = query.get("known_inputs") or {}
    if not isinstance(known_inputs, dict):
        known_inputs = {}

    required_checks = _compose_required_checks(
        list(retrieved_context.get("required_checks") or []),
        known_inputs,
    )
    missing_checks = [
        item["check"]
        for item in required_checks
        if item["status"] == "missing"
    ]
    warnings = [
        {
            "code": "missing_required_check",
            "check": check,
            "message": "Required check must be verified before reasoner use.",
        }
        for check in missing_checks
    ]

    applied_validated_rules = [
        _rule_item(rule, rule_status="validated_rule", applied=True)
        for rule in _sorted_entries(retrieved_context.get("validated_rules") or [])
    ]
    candidate_rules = [
        _rule_item(rule, rule_status="candidate_rule", applied=False)
        for rule in _sorted_entries(retrieved_context.get("candidate_rules") or [])
    ]
    supporting_cases = [
        _case_item(case)
        for case in _sorted_entries(retrieved_context.get("cases") or [])
    ]

    return {
        "trace_type": "skill_execution_trace.v0",
        "user_id": query.get("user_id", retrieved_context.get("user_id")),
        "domain": query.get("domain", retrieved_context.get("domain")),
        "skill_id": query.get("skill_id", retrieved_context.get("skill_id")),
        "task_type": query.get("task_type", retrieved_context.get("task_type")),
        "required_checks": required_checks,
        "missing_checks": missing_checks,
        "applied_validated_rules": applied_validated_rules,
        "candidate_rules": candidate_rules,
        "supporting_cases": supporting_cases,
        "warnings": [
            *warnings,
            *list(retrieved_context.get("warnings") or []),
        ],
        "trust_model": {
            "mode": "deterministic_scaffold",
            "decision_status": "not_produced",
            "limitations": [
                "does not produce a business decision",
                "does not prove factual truth",
                "does not prove reasoning validity",
                "candidate rules remain candidates",
                "missing checks require explicit verification",
            ],
        },
        "decision_scaffold": {
            "status": "requires_reasoner",
            "must_apply": [
                rule["id"]
                for rule in applied_validated_rules
                if isinstance(rule.get("id"), str)
            ],
            "must_verify": [item["check"] for item in required_checks],
            "must_not_assume": [
                "candidate_rules_are_validated",
                "missing_checks_are_satisfied",
                "retrieval_context_is_complete",
            ],
        },
    }


def score_skill_trace(
    trace: dict[str, Any],
    retrieved_context: dict[str, Any],
) -> dict[str, Any]:
    penalties: list[Penalty] = []

    if trace.get("trace_type") != "skill_execution_trace.v0":
        _add_penalty(
            penalties,
            "wrong_trace_type",
            "Trace must use skill_execution_trace.v0.",
            "high",
        )

    _score_scope(trace, retrieved_context, penalties)
    _score_required_checks(trace, retrieved_context, penalties)
    _score_rule_separation(trace, retrieved_context, penalties)
    _score_entry_scope(trace, penalties)
    _score_trust_model(trace, penalties)
    _score_no_overpromise(trace, penalties)

    return _result("__skill_execution_trace__", penalties)


def score_trace_determinism(
    first_trace: dict[str, Any],
    second_trace: dict[str, Any],
) -> dict[str, Any]:
    penalties: list[Penalty] = []
    if first_trace != second_trace:
        _add_penalty(
            penalties,
            "non_deterministic_trace",
            "Identical inputs must produce exactly the same trace.",
            "high",
        )
    return _result("__skill_execution_determinism__", penalties)


def _compose_required_checks(
    required_checks: list[str],
    known_inputs: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        {
            "check": check,
            "status": "covered" if _check_covered(check, known_inputs) else "missing",
            "input_keys": list(CHECK_INPUT_KEYS.get(check, (check,))),
        }
        for check in sorted(set(required_checks))
    ]


def _check_covered(check: str, known_inputs: dict[str, Any]) -> bool:
    for key in CHECK_INPUT_KEYS.get(check, (check,)):
        if key in known_inputs and known_inputs[key] is not None:
            return True
    return False


def _rule_item(
    entry: dict[str, Any],
    *,
    rule_status: str,
    applied: bool,
) -> dict[str, Any]:
    return {
        "id": entry.get("id"),
        "user_id": entry.get("user_id"),
        "domain": entry.get("domain"),
        "skill_id": entry.get("skill_id"),
        "task_type": entry.get("task_type"),
        "entry_type": entry.get("entry_type"),
        "epistemic_status": entry.get("epistemic_status"),
        "rule_version": entry.get("rule_version"),
        "required_checks": sorted(entry.get("required_checks") or []),
        "statement": entry.get("statement"),
        "rule_status": rule_status,
        "applied": applied,
    }


def _case_item(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entry.get("id"),
        "user_id": entry.get("user_id"),
        "domain": entry.get("domain"),
        "skill_id": entry.get("skill_id"),
        "task_type": entry.get("task_type"),
        "entry_type": entry.get("entry_type"),
        "epistemic_status": entry.get("epistemic_status"),
        "rule_version": entry.get("rule_version"),
        "required_checks": sorted(entry.get("required_checks") or []),
        "statement": entry.get("statement"),
    }


def _score_scope(
    trace: dict[str, Any],
    retrieved_context: dict[str, Any],
    penalties: list[Penalty],
) -> None:
    for key in ("user_id", "domain", "skill_id"):
        if trace.get(key) != retrieved_context.get(key):
            _add_penalty(
                penalties,
                f"wrong_{key}",
                f"Trace {key} does not match retrieved context.",
                "high",
            )


def _score_required_checks(
    trace: dict[str, Any],
    retrieved_context: dict[str, Any],
    penalties: list[Penalty],
) -> None:
    expected = set(retrieved_context.get("required_checks") or [])
    observed_items = trace.get("required_checks") or []
    observed = {
        item.get("check")
        for item in observed_items
        if isinstance(item, dict)
    }
    missing_checks = set(trace.get("missing_checks") or [])
    warning_checks = {
        warning.get("check")
        for warning in trace.get("warnings") or []
        if isinstance(warning, dict)
        and warning.get("code") == "missing_required_check"
    }

    for check in sorted(expected - observed):
        _add_penalty(
            penalties,
            "required_check_not_in_trace",
            f"Required check not represented in trace: {check}",
            "high",
        )

    for item in observed_items:
        if not isinstance(item, dict):
            _add_penalty(
                penalties,
                "malformed_required_check",
                "Required check items must be objects.",
                "medium",
            )
            continue
        check = item.get("check")
        status = item.get("status")
        if status not in {"covered", "missing"}:
            _add_penalty(
                penalties,
                "invalid_required_check_status",
                f"Invalid required check status for {check!r}.",
                "medium",
            )
        if status == "missing":
            if check not in missing_checks:
                _add_penalty(
                    penalties,
                    "missing_check_not_listed",
                    f"Missing check not listed: {check}",
                    "high",
                )
            if check not in warning_checks:
                _add_penalty(
                    penalties,
                    "missing_check_without_warning",
                    f"Missing check lacks warning: {check}",
                    "high",
                )


def _score_rule_separation(
    trace: dict[str, Any],
    retrieved_context: dict[str, Any],
    penalties: list[Penalty],
) -> None:
    expected_candidate_ids = {
        entry.get("id")
        for entry in retrieved_context.get("candidate_rules") or []
    }
    expected_validated_ids = {
        entry.get("id")
        for entry in retrieved_context.get("validated_rules") or []
    }
    applied_rules = trace.get("applied_validated_rules") or []
    candidate_rules = trace.get("candidate_rules") or []
    applied_ids = {
        entry.get("id")
        for entry in applied_rules
        if isinstance(entry, dict)
    }

    for candidate_id in sorted(expected_candidate_ids & applied_ids):
        _add_penalty(
            penalties,
            "candidate_rule_auto_promoted",
            f"Candidate rule was placed in applied rules: {candidate_id}",
            "high",
        )

    for rule in applied_rules:
        if not isinstance(rule, dict):
            _add_penalty(
                penalties,
                "malformed_applied_rule",
                "Applied rules must be objects.",
                "medium",
            )
            continue
        if rule.get("id") not in expected_validated_ids:
            _add_penalty(
                penalties,
                "unexpected_applied_rule",
                f"Applied rule is not from retrieved validated rules: {rule.get('id')}",
                "high",
            )
        if rule.get("rule_status") != "validated_rule" or rule.get("applied") is not True:
            _add_penalty(
                penalties,
                "invalid_applied_rule_status",
                "Applied rules must be marked validated_rule and applied=true.",
                "medium",
            )

    for rule in candidate_rules:
        if not isinstance(rule, dict):
            _add_penalty(
                penalties,
                "malformed_candidate_rule",
                "Candidate rules must be objects.",
                "medium",
            )
            continue
        if rule.get("id") not in expected_candidate_ids:
            _add_penalty(
                penalties,
                "unexpected_candidate_rule",
                f"Candidate rule is not from retrieved candidates: {rule.get('id')}",
                "medium",
            )
        if rule.get("rule_status") != "candidate_rule" or rule.get("applied") is not False:
            _add_penalty(
                penalties,
                "invalid_candidate_rule_status",
                "Candidate rules must remain candidate_rule and applied=false.",
                "high",
            )


def _score_entry_scope(trace: dict[str, Any], penalties: list[Penalty]) -> None:
    for entry in _trace_entries(trace):
        if not isinstance(entry, dict):
            continue
        entry_id = entry.get("id")
        if entry.get("user_id") != trace.get("user_id"):
            _add_penalty(
                penalties,
                "user_scope_leak",
                f"Trace includes entry outside user scope: {entry_id}",
                "high",
            )
        if entry.get("domain") != trace.get("domain"):
            _add_penalty(
                penalties,
                "domain_scope_leak",
                f"Trace includes entry outside domain scope: {entry_id}",
                "high",
            )
        if entry.get("skill_id") != trace.get("skill_id"):
            _add_penalty(
                penalties,
                "skill_scope_leak",
                f"Trace includes entry outside skill scope: {entry_id}",
                "high",
            )


def _score_trust_model(trace: dict[str, Any], penalties: list[Penalty]) -> None:
    trust_model = trace.get("trust_model")
    if not isinstance(trust_model, dict):
        _add_penalty(
            penalties,
            "missing_trust_model",
            "Trace must include trust_model.",
            "high",
        )
        return

    if trust_model.get("mode") != "deterministic_scaffold":
        _add_penalty(
            penalties,
            "wrong_trust_mode",
            "trust_model.mode must be deterministic_scaffold.",
            "medium",
        )
    if trust_model.get("decision_status") != "not_produced":
        _add_penalty(
            penalties,
            "decision_status_not_produced",
            "Trace must state that no decision was produced.",
            "high",
        )
    limitations = trust_model.get("limitations")
    if not isinstance(limitations, list) or not limitations:
        _add_penalty(
            penalties,
            "missing_limitations",
            "trust_model.limitations must be non-empty.",
            "medium",
        )

    decision_scaffold = trace.get("decision_scaffold")
    if not isinstance(decision_scaffold, dict):
        _add_penalty(
            penalties,
            "missing_decision_scaffold",
            "Trace must include decision_scaffold.",
            "high",
        )
    elif decision_scaffold.get("status") != "requires_reasoner":
        _add_penalty(
            penalties,
            "decision_scaffold_not_pending_reasoner",
            "decision_scaffold.status must be requires_reasoner.",
            "high",
        )


def _score_no_overpromise(trace: dict[str, Any], penalties: list[Penalty]) -> None:
    serialized = json.dumps(trace, sort_keys=True, ensure_ascii=False).lower()
    for phrase in OVERPROMISE_PHRASES:
        if phrase in serialized:
            _add_penalty(
                penalties,
                "overpromise_wording",
                f"Trace contains forbidden wording: {phrase}",
                "high",
            )


def _sorted_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(entries, key=lambda entry: str(entry.get("id", "")))


def _trace_entries(trace: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        *list(trace.get("applied_validated_rules") or []),
        *list(trace.get("candidate_rules") or []),
        *list(trace.get("supporting_cases") or []),
    ]


def _add_penalty(
    penalties: list[Penalty],
    code: str,
    message: str,
    severity: str,
) -> None:
    penalties.append(Penalty(code=code, message=message, severity=severity))


def _result(record_id: str, penalties: list[Penalty]) -> dict[str, Any]:
    total_penalty = sum(SEVERITY_POINTS[penalty.severity] for penalty in penalties)
    return {
        "record_id": record_id,
        "score": max(0.0, MAX_SCORE - total_penalty),
        "max_score": MAX_SCORE,
        "penalties": [penalty.as_dict() for penalty in penalties],
    }
