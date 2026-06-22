from __future__ import annotations

from pathlib import Path

from eval.skill_retrieval_v0 import load_records, retrieve_skill_context


REPO_ROOT = Path(__file__).resolve().parents[1]
RECORDS_PATH = REPO_ROOT / "datasets" / "dsm_reasoning_v0" / "records.jsonl"
RETRIEVAL_PATH = REPO_ROOT / "eval" / "skill_retrieval_v0" / "retrieval.py"


def test_retrieve_skill_context_returns_mohamed_omari_entries():
    context = _retrieve_mohamed_omari()

    assert context["user_id"] == "mohamed"
    assert context["domain"] == "omari_ai"
    assert context["skill_id"] == "omari_ai.lead_capture_reliability"
    assert context["task_type"] == "prioritization_decision"
    assert context["warnings"] == []

    assert {
        "bug_before_feature",
        "external_evidence_limit_disclosed",
        "known_context_not_reasked",
        "persistence_failure_checked",
    }.issubset(context["required_checks"])
    assert _ids(context["validated_rules"]) >= {
        "skill-02-omari-lead-capture-validated-rule",
    }
    assert _ids(context["candidate_rules"]) >= {
        "skill-01-omari-lead-capture-correction",
    }
    assert _ids(context["cases"]) >= {"skill-03-omari-lead-capture-case"}


def test_retrieve_skill_context_enforces_user_isolation():
    context = _retrieve_mohamed_omari()
    entries = _all_entries(context)

    assert "skill-04-other-user-omari-lead-capture-rule" not in _ids(entries)
    assert entries
    assert all(entry["user_id"] == "mohamed" for entry in entries)


def test_retrieve_skill_context_excludes_unscoped_records_by_default():
    context = _retrieve_mohamed_omari()
    entries = _all_entries(context)

    assert "skill-05-omari-lead-capture-global-template" not in _ids(entries)
    assert all(entry["user_id"] is not None for entry in entries)


def test_retrieve_skill_context_filters_domain_and_skill():
    context = _retrieve_mohamed_omari()
    entries = _all_entries(context)

    assert "skill-06-billing-refund-case" not in _ids(entries)
    assert all(entry["domain"] == "omari_ai" for entry in entries)
    assert all(
        entry["skill_id"] == "omari_ai.lead_capture_reliability"
        for entry in entries
    )


def test_retrieve_skill_context_is_deterministic():
    records = load_records(RECORDS_PATH)

    first = retrieve_skill_context(
        records,
        user_id="mohamed",
        domain="omari_ai",
        skill_id="omari_ai.lead_capture_reliability",
        task_type="prioritization_decision",
    )
    second = retrieve_skill_context(
        list(reversed(records)),
        user_id="mohamed",
        domain="omari_ai",
        skill_id="omari_ai.lead_capture_reliability",
        task_type="prioritization_decision",
    )

    assert first == second


def test_retrieve_skill_context_task_type_filter_can_return_empty_context():
    records = load_records(RECORDS_PATH)

    context = retrieve_skill_context(
        records,
        user_id="mohamed",
        domain="omari_ai",
        skill_id="omari_ai.lead_capture_reliability",
        task_type="support_triage",
    )

    assert context["required_checks"] == []
    assert context["validated_rules"] == []
    assert context["candidate_rules"] == []
    assert context["cases"] == []


def test_retrieval_code_is_static_and_kernel_free():
    source = RETRIEVAL_PATH.read_text(encoding="utf-8")

    forbidden_fragments = (
        "from dsm." + "core",
        "import dsm." + "core",
        "Stor" + "age",
        "core." + "storage",
    )
    for fragment in forbidden_fragments:
        assert fragment not in source


def _retrieve_mohamed_omari() -> dict:
    return retrieve_skill_context(
        load_records(RECORDS_PATH),
        user_id="mohamed",
        domain="omari_ai",
        skill_id="omari_ai.lead_capture_reliability",
        task_type="prioritization_decision",
    )


def _all_entries(context: dict) -> list[dict]:
    return [
        *context["validated_rules"],
        *context["candidate_rules"],
        *context["cases"],
    ]


def _ids(entries: list[dict]) -> set[str]:
    return {entry["id"] for entry in entries}
