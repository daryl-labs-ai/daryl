#!/usr/bin/env python3
"""Pure-data skill retrieval over DSM reasoning dataset records."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def load_records(path: str | Path) -> list[dict[str, Any]]:
    records_path = Path(path)
    return [
        json.loads(line)
        for line in records_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def retrieve_skill_context(
    records: list[dict[str, Any]],
    *,
    user_id: str,
    domain: str,
    skill_id: str,
    task_type: str | None = None,
) -> dict[str, Any]:
    matched_records = sorted(
        (
            record
            for record in records
            if _is_skill_record(record)
            and record.get("user_id") == user_id
            and record.get("domain") == domain
            and record.get("skill_id") == skill_id
            and (task_type is None or record.get("task_type") == task_type)
        ),
        key=lambda record: str(record.get("id", "")),
    )

    return {
        "user_id": user_id,
        "domain": domain,
        "skill_id": skill_id,
        "task_type": task_type,
        "required_checks": _required_checks(matched_records),
        "validated_rules": [
            _record_summary(record)
            for record in matched_records
            if _is_validated_rule(record)
        ],
        "candidate_rules": [
            _record_summary(record)
            for record in matched_records
            if _is_candidate_rule(record)
        ],
        "cases": [
            _record_summary(record)
            for record in matched_records
            if record.get("entry_type") == "case"
        ],
        "warnings": [],
    }


def _is_skill_record(record: dict[str, Any]) -> bool:
    return record.get("record_kind") == "skill_memory_entry"


def _is_validated_rule(record: dict[str, Any]) -> bool:
    return (
        record.get("entry_type") == "rule"
        and record.get("epistemic_status") == "validated_rule"
    )


def _is_candidate_rule(record: dict[str, Any]) -> bool:
    if record.get("epistemic_status") == "candidate_rule":
        return True
    return any(
        update.get("status") == "candidate"
        for update in record.get("skill_rule_updates") or []
        if isinstance(update, dict)
    )


def _required_checks(records: list[dict[str, Any]]) -> list[str]:
    checks = {
        check
        for record in records
        for check in record.get("required_checks", [])
        if isinstance(check, str) and check
    }
    return sorted(checks)


def _record_summary(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record.get("id"),
        "user_id": record.get("user_id"),
        "domain": record.get("domain"),
        "skill_id": record.get("skill_id"),
        "task_type": record.get("task_type"),
        "entry_type": record.get("entry_type"),
        "epistemic_status": record.get("epistemic_status"),
        "rule_version": record.get("rule_version"),
        "required_checks": sorted(record.get("required_checks") or []),
        "statement": _statement(record),
    }


def _statement(record: dict[str, Any]) -> str | None:
    outcome = record.get("outcome")
    if isinstance(outcome, dict) and isinstance(outcome.get("statement"), str):
        return outcome["statement"]

    correction = record.get("correction")
    if isinstance(correction, dict) and isinstance(correction.get("statement"), str):
        return correction["statement"]

    for update in record.get("skill_rule_updates") or []:
        if not isinstance(update, dict):
            continue
        proposed_rule = update.get("proposed_rule")
        if isinstance(proposed_rule, str):
            return proposed_rule

    feedback = record.get("feedback")
    if isinstance(feedback, dict):
        for key in ("summary", "user_correction"):
            value = feedback.get(key)
            if isinstance(value, str):
                return value

    return None


def main(argv: list[str] | None = None) -> int:
    args = list(argv or sys.argv[1:])
    if len(args) not in {4, 5}:
        print(
            "usage: retrieval.py RECORDS_JSONL USER_ID DOMAIN SKILL_ID [TASK_TYPE]",
            file=sys.stderr,
        )
        return 2

    records_path, user_id, domain, skill_id, *rest = args
    task_type = rest[0] if rest else None
    result = retrieve_skill_context(
        load_records(records_path),
        user_id=user_id,
        domain=domain,
        skill_id=skill_id,
        task_type=task_type,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
