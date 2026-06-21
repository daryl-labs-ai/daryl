#!/usr/bin/env python3
"""Validate the DSM reasoning dataset v0 JSONL file.

The validator is intentionally self-contained. It does not import DSM modules
or kernel internals; the dataset is static test/evaluation data.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


DATASET_DIR = Path(__file__).resolve().parent
RECORDS_PATH = DATASET_DIR / "records.jsonl"
SCHEMA_PATH = DATASET_DIR / "schema.json"
ALLOWED_LABELS = {"positive", "negative"}
ALLOWED_RECORD_KINDS = {"reasoning_trace", "skill_memory_entry"}
ALLOWED_ENTRY_TYPES = {
    "case",
    "rule",
    "correction",
    "preference",
    "outcome",
    "evidence_ref",
}
ALLOWED_EPISTEMIC_STATUSES = {
    "observed",
    "hypothesis",
    "candidate_rule",
    "validated_rule",
}
BASE_REQUIRED_FIELDS = {
    "id",
    "label",
    "question",
    "context",
    "known_limits",
    "notes",
}
REASONING_TRACE_REQUIRED_FIELDS = {
    "facts",
    "hypotheses",
    "inferences",
    "decision",
    "expected_json",
    "expected_markdown",
}
SKILL_MEMORY_REQUIRED_FIELDS = {
    "entry_type",
    "epistemic_status",
}
HASH_PLACEHOLDER_RE = re.compile(r"^<HASH_[A-Z0-9_]+>$")
ANY_HASH_PLACEHOLDER_RE = re.compile(r"<HASH_[A-Z0-9_]+>")
REAL_DSM_HASH_RE = re.compile(r"\bv1:[0-9a-fA-F]{16,}\b")
FORBIDDEN_DATASET_KEYS = {"external_ref"}
FORBIDDEN_SOURCE_FRAGMENTS = (
    "from dsm." + "core",
    "import dsm." + "core",
    "Stor" + "age",
    "core." + "storage",
)


def main() -> int:
    errors: list[str] = []
    if not SCHEMA_PATH.exists():
        errors.append(f"missing schema: {SCHEMA_PATH}")
    if not RECORDS_PATH.exists():
        errors.append(f"missing records: {RECORDS_PATH}")
    if errors:
        return _report(errors)

    _validate_self_containment(errors)
    records = _load_records(errors)
    seen_ids: set[str] = set()
    positive_trace_count = 0
    negative_trace_count = 0
    skill_memory_count = 0

    for line_no, record in records:
        record_id = record.get("id", f"line-{line_no}")
        _validate_required_fields(record, line_no, errors)
        _validate_label(record, line_no, errors)
        record_kind = _validate_record_kind(record, line_no, errors)
        _validate_skill_metadata(record, record_kind, line_no, errors)
        _validate_known_limits(record, line_no, errors)
        if record_kind == "reasoning_trace":
            _validate_expected_markdown(record, line_no, errors)
            _validate_expected_targets(record, line_no, errors)
        elif "expected_markdown" in record:
            _validate_expected_markdown(record, line_no, errors)
        if record_kind != "reasoning_trace" and "expected_json" in record:
            _validate_expected_targets(record, line_no, errors)
        _validate_hash_placeholders(record, line_no, errors)
        _validate_no_forbidden_keys(record, line_no, errors)

        if record_id in seen_ids:
            errors.append(f"line {line_no}: duplicate id {record_id!r}")
        seen_ids.add(str(record_id))
        if record_kind == "reasoning_trace" and record.get("label") == "positive":
            positive_trace_count += 1
        if record_kind == "reasoning_trace" and record.get("label") == "negative":
            negative_trace_count += 1
        if record_kind == "skill_memory_entry":
            skill_memory_count += 1

    if positive_trace_count != 3:
        errors.append(f"expected 3 positive reasoning_trace records, found {positive_trace_count}")
    if negative_trace_count not in {2, 3}:
        errors.append(
            f"expected 2 or 3 negative reasoning_trace records, found {negative_trace_count}"
        )
    if skill_memory_count < 1:
        errors.append("expected at least one skill_memory_entry record")
    _validate_dogfood_03(records, errors)
    _validate_skill_01(records, errors)

    if errors:
        return _report(errors)

    print(f"OK: {len(records)} records validated")
    return 0


def _load_records(errors: list[str]) -> list[tuple[int, dict[str, Any]]]:
    records: list[tuple[int, dict[str, Any]]] = []
    for line_no, line in enumerate(
        RECORDS_PATH.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_no}: invalid JSON: {exc}")
            continue
        if not isinstance(parsed, dict):
            errors.append(f"line {line_no}: record must be a JSON object")
            continue
        records.append((line_no, parsed))
    return records


def _validate_required_fields(
    record: dict[str, Any],
    line_no: int,
    errors: list[str],
) -> None:
    record_kind = _record_kind(record)
    required = set(BASE_REQUIRED_FIELDS)
    if record_kind == "reasoning_trace":
        required.update(REASONING_TRACE_REQUIRED_FIELDS)
    if record_kind == "skill_memory_entry":
        required.update(SKILL_MEMORY_REQUIRED_FIELDS)
    missing = sorted(required - set(record))
    if missing:
        errors.append(f"line {line_no}: missing fields: {', '.join(missing)}")


def _record_kind(record: dict[str, Any]) -> str:
    value = record.get("record_kind", "reasoning_trace")
    return value if isinstance(value, str) else ""


def _validate_record_kind(
    record: dict[str, Any],
    line_no: int,
    errors: list[str],
) -> str:
    record_kind = _record_kind(record)
    if record_kind not in ALLOWED_RECORD_KINDS:
        errors.append(f"line {line_no}: invalid record_kind {record_kind!r}")
    return record_kind


def _validate_skill_metadata(
    record: dict[str, Any],
    record_kind: str,
    line_no: int,
    errors: list[str],
) -> None:
    entry_type = record.get("entry_type")
    if entry_type is not None and entry_type not in ALLOWED_ENTRY_TYPES:
        errors.append(f"line {line_no}: invalid entry_type {entry_type!r}")
    epistemic_status = record.get("epistemic_status")
    if (
        epistemic_status is not None
        and epistemic_status not in ALLOWED_EPISTEMIC_STATUSES
    ):
        errors.append(f"line {line_no}: invalid epistemic_status {epistemic_status!r}")
    required_checks = record.get("required_checks")
    if required_checks is not None:
        if not isinstance(required_checks, list) or not all(
            isinstance(item, str) and item.strip() for item in required_checks
        ):
            errors.append(f"line {line_no}: required_checks must be a list of strings")
    if record_kind == "skill_memory_entry":
        if "expected_json" in record or "expected_markdown" in record:
            errors.append(
                f"line {line_no}: skill_memory_entry must not force expected_json/expected_markdown"
            )


def _validate_label(
    record: dict[str, Any],
    line_no: int,
    errors: list[str],
) -> None:
    label = record.get("label")
    if label not in ALLOWED_LABELS:
        errors.append(f"line {line_no}: invalid label {label!r}")


def _validate_known_limits(
    record: dict[str, Any],
    line_no: int,
    errors: list[str],
) -> None:
    known_limits = record.get("known_limits")
    if not isinstance(known_limits, list) or not known_limits:
        errors.append(f"line {line_no}: known_limits must be a non-empty list")
        return
    if not all(isinstance(item, str) and item.strip() for item in known_limits):
        errors.append(f"line {line_no}: known_limits entries must be non-empty strings")


def _validate_expected_markdown(
    record: dict[str, Any],
    line_no: int,
    errors: list[str],
) -> None:
    markdown = record.get("expected_markdown")
    if not isinstance(markdown, str) or not markdown.strip():
        errors.append(f"line {line_no}: expected_markdown must be a non-empty string")
        return
    if "Trust Model / Limitations" not in markdown:
        errors.append(
            f"line {line_no}: expected_markdown must contain Trust Model / Limitations"
        )


def _validate_expected_targets(
    record: dict[str, Any],
    line_no: int,
    errors: list[str],
) -> None:
    expected_json = record.get("expected_json")
    if not isinstance(expected_json, dict):
        errors.append(f"line {line_no}: expected_json must be an object")
        return
    if expected_json.get("schema_version") != "agent_memory.explain.v1":
        errors.append(f"line {line_no}: expected_json schema_version must be v1")
    if expected_json.get("status") not in {"ok", "error"}:
        errors.append(f"line {line_no}: expected_json status must be ok or error")

    target_text = json.dumps(expected_json, sort_keys=True) + "\n" + str(
        record.get("expected_markdown", "")
    )
    if REAL_DSM_HASH_RE.search(target_text):
        errors.append(f"line {line_no}: expected outputs contain a real DSM v1 hash")


def _validate_hash_placeholders(
    record: dict[str, Any],
    line_no: int,
    errors: list[str],
) -> None:
    for path, value in _walk(record):
        if isinstance(value, str):
            if "v1:" in value and REAL_DSM_HASH_RE.search(value):
                errors.append(f"line {line_no}: {path} contains a real DSM hash")
            for placeholder in re.findall(r"<HASH_[^>]+>", value):
                if not HASH_PLACEHOLDER_RE.fullmatch(placeholder):
                    errors.append(
                        f"line {line_no}: {path} has invalid hash placeholder {placeholder!r}"
                    )
        if path.endswith("depends_on[]") and isinstance(value, str):
            if not HASH_PLACEHOLDER_RE.fullmatch(value):
                errors.append(f"line {line_no}: {path} must use <HASH_...>")
        if path.endswith("entry_hash") and isinstance(value, str):
            if not HASH_PLACEHOLDER_RE.fullmatch(value):
                errors.append(f"line {line_no}: {path} must use <HASH_...>")

    serialized = json.dumps(record, sort_keys=True, ensure_ascii=False)
    if "<HASH" in serialized and not ANY_HASH_PLACEHOLDER_RE.search(serialized):
        errors.append(f"line {line_no}: malformed hash placeholder")


def _validate_no_forbidden_keys(
    record: dict[str, Any],
    line_no: int,
    errors: list[str],
) -> None:
    for path, _value in _walk(record):
        key = path.rsplit(".", 1)[-1].replace("[]", "")
        if key in FORBIDDEN_DATASET_KEYS:
            errors.append(f"line {line_no}: forbidden key {key!r} at {path}")


def _validate_dogfood_03(
    records: list[tuple[int, dict[str, Any]]],
    errors: list[str],
) -> None:
    dogfood_03 = [record for _line_no, record in records if record.get("id") == "dogfood-03-log-ticket"]
    if len(dogfood_03) != 1:
        errors.append("expected exactly one dogfood-03-log-ticket record")
        return
    record = dogfood_03[0]
    evidence_types = {fact.get("evidence_type") for fact in record.get("facts", [])}
    if not {"log", "ticket"}.issubset(evidence_types):
        errors.append("dogfood-03-log-ticket must include log + ticket evidence types")
    notes = record.get("notes", "")
    limits = " ".join(record.get("known_limits", []))
    if "V2" not in notes or "not implemented" not in notes:
        errors.append("dogfood-03-log-ticket notes must state V2 evidence is not implemented")
    if "first-class DSM evidence" not in limits:
        errors.append("dogfood-03-log-ticket known_limits must mention first-class DSM evidence")


def _validate_skill_01(
    records: list[tuple[int, dict[str, Any]]],
    errors: list[str],
) -> None:
    matches = [
        record
        for _line_no, record in records
        if record.get("id") == "skill-01-omari-lead-capture-correction"
    ]
    if len(matches) != 1:
        errors.append("expected exactly one skill-01-omari-lead-capture-correction record")
        return
    record = matches[0]
    if record.get("record_kind") != "skill_memory_entry":
        errors.append("skill-01 must be record_kind=skill_memory_entry")
    if record.get("user_id") != "mohamed":
        errors.append("skill-01 must be scoped to user_id=mohamed")
    if record.get("entry_type") != "correction":
        errors.append("skill-01 must use entry_type=correction")
    if record.get("epistemic_status") != "candidate_rule":
        errors.append("skill-01 correction must remain candidate_rule")
    limits = " ".join(record.get("known_limits", []))
    for expected_limit in (
        "local tamper-evident only",
        "does not prove factual truth",
        "does not prove reasoning validity",
        "candidate rule",
        "metadata-first sharding only",
    ):
        if expected_limit not in limits:
            errors.append(f"skill-01 known_limits must mention {expected_limit!r}")
    for update in record.get("skill_rule_updates", []):
        if update.get("status") == "validated":
            errors.append("skill-01 must not auto-promote corrections to validated rules")


def _validate_self_containment(errors: list[str]) -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    for fragment in FORBIDDEN_SOURCE_FRAGMENTS:
        if fragment in source:
            errors.append(f"validator must not reference {fragment!r}")


def _walk(value: Any, path: str = "$"):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _walk(item, f"{path}.{key}")
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item, f"{path}[]")
    else:
        yield path, value


def _report(errors: list[str]) -> int:
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
