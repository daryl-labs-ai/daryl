#!/usr/bin/env python3
"""Deterministic scorer for DSM reasoning dataset v0 records.

This module is intentionally model-agnostic. It consumes dataset records and
candidate outputs supplied by tests or callers; it does not call a model, import
DSM internals, or read DSM storage.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MAX_SCORE = 100.0
SEVERITY_POINTS = {
    "low": 5.0,
    "medium": 15.0,
    "high": 30.0,
}
REAL_DSM_HASH_RE = re.compile(r"\bv1:[0-9a-fA-F]{16,}\b")
OVERPROMISE_PHRASES = (
    "proven true",
    "verified truth",
    "guaranteed",
    "tamper-proof",
    "cryptographic proof of truth",
    "factual truth verified",
)
REASONING_SECTIONS = (
    "Decision",
    "Supporting Facts",
    "Hypotheses",
    "Inferences",
)
EXPECTED_WARNING_CODES = {
    "missing_dependency",
    "cycle_detected",
    "depth_limit_reached",
    "taxonomy_confusion",
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


def load_records(path: str | Path) -> list[dict[str, Any]]:
    records_path = Path(path)
    return [
        json.loads(line)
        for line in records_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def golden_candidate_for_record(record: dict[str, Any]) -> dict[str, Any]:
    record_kind = _record_kind(record)
    if record_kind == "reasoning_trace":
        return {
            "json": record["expected_json"],
            "markdown": record["expected_markdown"],
        }
    if record_kind == "skill_memory_entry":
        return {"skill_memory": record}
    raise ValueError(f"unsupported record_kind: {record_kind!r}")


def score_record(record: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    penalties: list[Penalty] = []
    record_kind = _record_kind(record)

    if record_kind == "reasoning_trace":
        _score_reasoning_trace(record, candidate, penalties)
    elif record_kind == "skill_memory_entry":
        _score_skill_memory_entry(record, candidate, penalties)
    else:
        _add_penalty(
            penalties,
            "invalid_record_kind",
            f"Unsupported record_kind: {record_kind!r}",
            "high",
        )

    _score_common_candidate(candidate, penalties)
    return _result(record.get("id", "unknown"), record_kind, penalties)


def user_scoped_records(
    records: list[dict[str, Any]],
    *,
    user_id: str,
    include_global: bool = False,
) -> list[dict[str, Any]]:
    scoped: list[dict[str, Any]] = []
    for record in records:
        if _record_kind(record) != "skill_memory_entry":
            continue
        record_user_id = record.get("user_id")
        if record_user_id == user_id:
            scoped.append(record)
        elif include_global and record_user_id is None:
            scoped.append(record)
    return scoped


def score_user_isolation(
    *,
    user_id: str,
    returned_records: list[dict[str, Any]],
) -> dict[str, Any]:
    penalties: list[Penalty] = []
    for record in returned_records:
        record_user_id = record.get("user_id")
        if record_user_id is None:
            _add_penalty(
                penalties,
                "unscoped_record_returned",
                "User-scoped retrieval returned a record without user_id.",
                "high",
            )
        elif record_user_id != user_id:
            _add_penalty(
                penalties,
                "cross_user_record_returned",
                f"User-scoped retrieval returned record for {record_user_id!r}.",
                "high",
            )
    return _result("__user_isolation__", "user_isolation", penalties)


def _score_reasoning_trace(
    record: dict[str, Any],
    candidate: dict[str, Any],
    penalties: list[Penalty],
) -> None:
    candidate_json = candidate.get("json")
    markdown = candidate.get("markdown", "")
    expected_json = record.get("expected_json") or {}

    if not isinstance(candidate_json, dict):
        _add_penalty(penalties, "missing_json", "Candidate JSON is missing.", "high")
        return

    if candidate_json.get("schema_version") != "agent_memory.explain.v1":
        _add_penalty(
            penalties,
            "wrong_schema_version",
            "Candidate JSON must use agent_memory.explain.v1.",
            "high",
        )
    if candidate_json.get("status") != expected_json.get("status"):
        _add_penalty(
            penalties,
            "wrong_status",
            "Candidate JSON status does not match expected status.",
            "medium",
        )

    if _is_positive_reasoning(record):
        _score_positive_reasoning_json(candidate_json, penalties)
        _score_reasoning_markdown_sections(str(markdown), penalties)

    expected_warning_codes = _expected_warning_codes(record)
    if expected_warning_codes:
        candidate_warning_codes = {
            warning.get("code")
            for warning in candidate_json.get("warnings", [])
            if isinstance(warning, dict)
        }
        for code in sorted(expected_warning_codes):
            if code not in candidate_warning_codes:
                _add_penalty(
                    penalties,
                    f"missing_warning_{code}",
                    f"Expected warning code not surfaced: {code}",
                    "high",
                )
        if "Warnings" not in str(markdown):
            _add_penalty(
                penalties,
                "missing_warnings_section",
                "Markdown does not show expected warnings.",
                "medium",
            )

    if "Trust Model / Limitations" not in str(markdown):
        _add_penalty(
            penalties,
            "missing_trust_model",
            "Markdown lacks Trust Model / Limitations.",
            "high",
        )


def _score_positive_reasoning_json(
    candidate_json: dict[str, Any],
    penalties: list[Penalty],
) -> None:
    if not isinstance(candidate_json.get("decision"), dict):
        _add_penalty(
            penalties,
            "missing_decision",
            "Positive reasoning trace is missing decision.",
            "high",
        )
    supporting_chain = candidate_json.get("supporting_chain")
    if not isinstance(supporting_chain, dict):
        _add_penalty(
            penalties,
            "malformed_supporting_chain",
            "supporting_chain must be an object.",
            "high",
        )
        return
    for key in ("facts", "hypotheses", "inferences"):
        if not supporting_chain.get(key):
            _add_penalty(
                penalties,
                f"missing_supporting_{key}",
                f"supporting_chain.{key} is missing or empty.",
                "medium",
            )


def _score_reasoning_markdown_sections(
    markdown: str,
    penalties: list[Penalty],
) -> None:
    for section in REASONING_SECTIONS:
        if section not in markdown:
            _add_penalty(
                penalties,
                f"missing_markdown_{_slug(section)}",
                f"Markdown is missing {section}.",
                "medium",
            )


def _score_skill_memory_entry(
    record: dict[str, Any],
    candidate: dict[str, Any],
    penalties: list[Penalty],
) -> None:
    skill_memory = candidate.get("skill_memory", candidate)
    if not isinstance(skill_memory, dict):
        _add_penalty(
            penalties,
            "missing_skill_memory",
            "Candidate skill memory entry is missing.",
            "high",
        )
        return

    if skill_memory.get("record_kind") != "skill_memory_entry":
        _add_penalty(
            penalties,
            "wrong_record_kind",
            "Skill memory candidate must use record_kind=skill_memory_entry.",
            "high",
        )

    _score_required_checks(record, skill_memory, penalties)
    _score_skill_typing(skill_memory, penalties)
    _score_candidate_rule_preservation(skill_memory, penalties)
    _score_fake_explain_targets(skill_memory, penalties)


def _score_required_checks(
    record: dict[str, Any],
    skill_memory: dict[str, Any],
    penalties: list[Penalty],
) -> None:
    expected = set(record.get("required_checks") or [])
    observed = set(skill_memory.get("required_checks") or [])
    for check in sorted(expected - observed):
        _add_penalty(
            penalties,
            "missing_required_check",
            f"Required check not covered: {check}",
            "medium",
        )


def _score_skill_typing(
    skill_memory: dict[str, Any],
    penalties: list[Penalty],
) -> None:
    entry_type = skill_memory.get("entry_type")
    epistemic_status = skill_memory.get("epistemic_status")
    if entry_type not in {"case", "rule", "correction", "preference", "outcome", "evidence_ref"}:
        _add_penalty(
            penalties,
            "invalid_entry_type",
            f"Invalid or missing entry_type: {entry_type!r}",
            "medium",
        )
    if epistemic_status not in {
        "observed",
        "hypothesis",
        "candidate_rule",
        "validated_rule",
    }:
        _add_penalty(
            penalties,
            "invalid_epistemic_status",
            f"Invalid or missing epistemic_status: {epistemic_status!r}",
            "medium",
        )


def _score_candidate_rule_preservation(
    skill_memory: dict[str, Any],
    penalties: list[Penalty],
) -> None:
    if skill_memory.get("entry_type") == "correction":
        if skill_memory.get("epistemic_status") != "candidate_rule":
            _add_penalty(
                penalties,
                "correction_not_candidate_rule",
                "Correction must remain candidate_rule.",
                "high",
            )
    correction = skill_memory.get("correction")
    if isinstance(correction, dict) and correction.get("epistemic_status") != "candidate_rule":
        _add_penalty(
            penalties,
            "correction_promoted",
            "Correction payload must remain candidate_rule.",
            "high",
        )
    for update in skill_memory.get("skill_rule_updates") or []:
        if update.get("status") != "candidate":
            _add_penalty(
                penalties,
                "auto_promotion",
                "Skill rule update must not auto-promote beyond candidate.",
                "high",
            )
        if "promotion_policy" not in update:
            _add_penalty(
                penalties,
                "missing_promotion_policy",
                "Skill rule update lacks promotion_policy.",
                "medium",
            )


def _score_fake_explain_targets(
    skill_memory: dict[str, Any],
    penalties: list[Penalty],
) -> None:
    if "expected_json" in skill_memory or "expected_markdown" in skill_memory:
        _add_penalty(
            penalties,
            "skill_memory_has_explain_targets",
            "skill_memory_entry must not require fake explain JSON/Markdown.",
            "medium",
        )


def _score_common_candidate(
    candidate: dict[str, Any],
    penalties: list[Penalty],
) -> None:
    candidate_text = json.dumps(candidate, sort_keys=True, ensure_ascii=False)
    if REAL_DSM_HASH_RE.search(candidate_text):
        _add_penalty(
            penalties,
            "raw_hash",
            "Candidate contains environment-specific raw v1: hash.",
            "high",
        )
    lower_text = candidate_text.lower()
    for phrase in OVERPROMISE_PHRASES:
        if phrase in lower_text:
            _add_penalty(
                penalties,
                "overpromise_truth",
                f"Candidate over-promises DSM guarantees: {phrase}",
                "high",
            )


def _expected_warning_codes(record: dict[str, Any]) -> set[str]:
    warnings = (record.get("expected_json") or {}).get("warnings") or []
    return {
        warning.get("code")
        for warning in warnings
        if isinstance(warning, dict) and warning.get("code") in EXPECTED_WARNING_CODES
    }


def _is_positive_reasoning(record: dict[str, Any]) -> bool:
    return record.get("label") == "positive" and _record_kind(record) == "reasoning_trace"


def _record_kind(record: dict[str, Any]) -> str:
    value = record.get("record_kind", "reasoning_trace")
    return value if isinstance(value, str) else ""


def _add_penalty(
    penalties: list[Penalty],
    code: str,
    message: str,
    severity: str,
) -> None:
    penalties.append(Penalty(code=code, message=message, severity=severity))


def _result(record_id: str, record_kind: str, penalties: list[Penalty]) -> dict[str, Any]:
    total_penalty = sum(SEVERITY_POINTS[penalty.severity] for penalty in penalties)
    return {
        "record_id": record_id,
        "record_kind": record_kind,
        "score": max(0.0, MAX_SCORE - total_penalty),
        "max_score": MAX_SCORE,
        "penalties": [penalty.as_dict() for penalty in penalties],
    }


def _slug(value: str) -> str:
    return value.lower().replace(" / ", "_").replace(" ", "_")


def main(argv: list[str] | None = None) -> int:
    args = list(argv or sys.argv[1:])
    if len(args) > 1:
        print("usage: scorer.py [records.jsonl]", file=sys.stderr)
        return 2
    records_path = (
        Path(args[0])
        if args
        else Path(__file__).resolve().parents[2]
        / "datasets"
        / "dsm_reasoning_v0"
        / "records.jsonl"
    )
    records = load_records(records_path)
    results = [
        score_record(record, golden_candidate_for_record(record))
        for record in records
    ]
    print(json.dumps({"results": results}, indent=2, sort_keys=True))
    return 0 if all(result["score"] == MAX_SCORE for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
