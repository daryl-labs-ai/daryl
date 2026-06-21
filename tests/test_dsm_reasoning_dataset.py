from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = REPO_ROOT / "datasets" / "dsm_reasoning_v0" / "validate_dataset.py"


def _load_validator():
    spec = importlib.util.spec_from_file_location(
        "dsm_reasoning_dataset_validator",
        VALIDATOR_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dsm_reasoning_dataset_v0_validates():
    validator = _load_validator()

    assert validator.main() == 0


def test_dsm_reasoning_dataset_validator_is_static_and_kernel_free():
    source = VALIDATOR_PATH.read_text(encoding="utf-8")

    forbidden_fragments = (
        "from dsm." + "core",
        "import dsm." + "core",
        "Stor" + "age",
        "core." + "storage",
    )
    for fragment in forbidden_fragments:
        assert fragment not in source


def test_user_scoped_skill_filter_excludes_other_and_unscoped_users():
    records = [
        {
            "id": "skill-mohamed",
            "record_kind": "skill_memory_entry",
            "user_id": "mohamed",
            "skill_id": "omari_ai.lead_capture_reliability",
        },
        {
            "id": "skill-other",
            "record_kind": "skill_memory_entry",
            "user_id": "other_user",
            "skill_id": "omari_ai.lead_capture_reliability",
        },
        {
            "id": "global-template",
            "record_kind": "skill_memory_entry",
            "skill_id": "omari_ai.lead_capture_reliability",
        },
    ]

    scoped = _filter_skill_memory_by_user(records, user_id="mohamed")

    assert [record["id"] for record in scoped] == ["skill-mohamed"]
    assert all(record.get("user_id") == "mohamed" for record in scoped)


def test_dataset_contains_skill_memory_entry_without_explain_targets():
    records = _load_dataset_records()
    skill_record = next(
        record
        for record in records
        if record["id"] == "skill-01-omari-lead-capture-correction"
    )

    assert skill_record["record_kind"] == "skill_memory_entry"
    assert skill_record["user_id"] == "mohamed"
    assert skill_record["epistemic_status"] == "candidate_rule"
    assert "expected_json" not in skill_record
    assert "expected_markdown" not in skill_record


def _filter_skill_memory_by_user(records: list[dict], *, user_id: str) -> list[dict]:
    return [
        record
        for record in records
        if record.get("record_kind") == "skill_memory_entry"
        and record.get("user_id") == user_id
    ]


def _load_dataset_records() -> list[dict]:
    records_path = REPO_ROOT / "datasets" / "dsm_reasoning_v0" / "records.jsonl"
    return [
        json.loads(line)
        for line in records_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
