from __future__ import annotations

import json
from pathlib import Path

from tools.agent_proposal_gateway_v0 import (
    ACCEPTED_FOR_AUDIT,
    NEEDS_HUMAN_REVIEW,
    REJECTED_BY_VALIDATOR,
    MockProposalProvider,
    OpenAICompatibleProvider,
    accepted_proposals_for_retrieval,
    agent_proposal_to_memory_records,
    build_agent_proposal_context,
    persist_agent_proposal_to_memory,
    run_agent_proposal_gateway,
    validate_agent_proposal,
    wrap_agent_proposal,
)
from eval.skill_retrieval_v0 import load_records


REPO_ROOT = Path(__file__).resolve().parents[1]
RECORDS_PATH = REPO_ROOT / "datasets" / "dsm_reasoning_v0" / "records.jsonl"
GATEWAY_PATH = REPO_ROOT / "tools" / "agent_proposal_gateway_v0" / "gateway.py"
PROVIDERS_PATH = REPO_ROOT / "tools" / "agent_proposal_gateway_v0" / "providers.py"


def test_mock_golden_is_accepted_persisted_explainable_and_markdown_auditable(tmp_path):
    result = _run("golden", tmp_path)
    validation = result["validation"]
    persistence = result["persistence"]
    markdown = persistence["markdown"]

    assert validation["status"] == ACCEPTED_FOR_AUDIT
    assert validation["model_proposed"] is True
    assert persistence["decision_hash"].startswith("v1:")
    assert persistence["validation_status"] == ACCEPTED_FOR_AUDIT
    assert persistence["explain"]["status"] == "ok"
    assert "# Agent Memory Audit Report" in markdown
    assert "## Trust Model / Limitations" in markdown
    assert ACCEPTED_FOR_AUDIT in markdown
    assert "Provider metadata" in markdown
    assert "raw_output_hash" in markdown
    assert "validated for form/honesty" not in markdown


def test_over_promise_is_rejected_by_validator(tmp_path):
    result = _run("over_promise", tmp_path)

    assert result["validation"]["status"] == REJECTED_BY_VALIDATOR
    assert "overpromise_wording" in _codes(result["validation"]["rejections"])
    assert result["persistence"]["validation_status"] == REJECTED_BY_VALIDATOR


def test_candidate_promotion_is_rejected_by_validator(tmp_path):
    result = _run("candidate_promotion", tmp_path)

    assert result["validation"]["status"] == REJECTED_BY_VALIDATOR
    assert "candidate_rule_promotion" in _codes(result["validation"]["rejections"])
    assert "candidate" in result["persistence"]["markdown"]


def test_required_check_not_covered_or_surfaced_is_rejected(tmp_path):
    result = _run("missing_required_check", tmp_path)

    assert result["validation"]["status"] == REJECTED_BY_VALIDATOR
    assert "required_check_not_covered_or_surfaced" in _codes(
        result["validation"]["rejections"]
    )


def test_claimed_check_outside_required_needs_human_review(tmp_path):
    result = _run("unknown_claimed_check", tmp_path)

    assert result["validation"]["status"] == NEEDS_HUMAN_REVIEW
    assert "claimed_check_outside_required" in _codes(result["validation"]["warnings"])


def test_cross_user_or_wrong_scope_leak_is_rejected(tmp_path):
    result = _run("cross_user_leak", tmp_path)

    assert result["validation"]["status"] == REJECTED_BY_VALIDATOR
    assert "scope_leak" in _codes(result["validation"]["rejections"])


def test_low_coverage_or_missing_limitations_needs_human_review(tmp_path):
    result = _run("low_coverage", tmp_path)

    assert result["validation"]["status"] == NEEDS_HUMAN_REVIEW
    assert {"low_coverage", "missing_limitations"}.issubset(
        _codes(result["validation"]["warnings"])
    )


def test_agent_supplied_status_only_is_ignored_without_auto_rejection(tmp_path):
    result = _run("agent_status", tmp_path)

    assert result["proposal"]["agent_supplied_status"] == ACCEPTED_FOR_AUDIT
    assert result["validation"]["status"] == NEEDS_HUMAN_REVIEW
    assert "agent_supplied_status_ignored" in _codes(result["validation"]["warnings"])
    assert result["validation"]["rejections"] == []


def test_agent_supplied_status_plus_hard_violation_is_rejected(tmp_path):
    result = _run("agent_status_over_promise", tmp_path)

    assert result["validation"]["status"] == REJECTED_BY_VALIDATOR
    assert "agent_supplied_status_ignored" in _codes(result["validation"]["warnings"])
    assert "overpromise_wording" in _codes(result["validation"]["rejections"])


def test_rejected_proposals_are_persisted_for_audit(tmp_path):
    result = _run("over_promise", tmp_path)
    markdown = result["persistence"]["markdown"]

    assert result["persistence"]["decision_hash"].startswith("v1:")
    assert REJECTED_BY_VALIDATOR in markdown
    assert "rejected_proposal_audit" in markdown
    assert '"rejected":true' in markdown
    assert '"business_decision":"not_produced"' in markdown


def test_needs_human_review_proposals_are_persisted_for_audit(tmp_path):
    result = _run("unknown_claimed_check", tmp_path)
    markdown = result["persistence"]["markdown"]

    assert result["persistence"]["decision_hash"].startswith("v1:")
    assert NEEDS_HUMAN_REVIEW in markdown
    assert '"requires_human_review":true' in markdown
    assert '"model_proposed":true' in markdown


def test_retrieval_allowlist_excludes_rejected_and_needs_review():
    records = [
        {"id": "accepted", "validation_status": ACCEPTED_FOR_AUDIT},
        {"id": "needs", "validation_status": NEEDS_HUMAN_REVIEW},
        {"id": "rejected", "validation_status": REJECTED_BY_VALIDATOR},
        {"id": "missing"},
    ]

    accepted = accepted_proposals_for_retrieval(records)

    assert accepted == [{"id": "accepted", "validation_status": ACCEPTED_FOR_AUDIT}]


def test_openai_compatible_provider_parses_mocked_http_response():
    def fake_transport(payload, metadata):
        assert metadata["name"] == "lmstudio"
        assert payload["model"] == "local-model"
        content = {
            "raw_output": "ok",
            "structured_output": {
                "narrative": "Mocked response.",
                "model_proposed_action": "Review.",
                "claimed_checks": [],
                "limitations": ["mocked"],
            },
        }
        return {"choices": [{"message": {"content": json.dumps(content)}}]}

    provider = OpenAICompatibleProvider(
        base_url="http://127.0.0.1:1234/v1",
        model="local-model",
        name="lmstudio",
        base_url_label="local-test",
        transport=fake_transport,
    )

    proposal = provider.propose({"context_type": "agent_proposal_context.v0"})

    assert provider.metadata["kind"] == "openai_compatible"
    assert proposal["raw_output"] == "ok"
    assert proposal["structured_output"]["limitations"] == ["mocked"]


def test_gateway_and_providers_do_not_use_direct_storage():
    for path in (GATEWAY_PATH, PROVIDERS_PATH):
        source = path.read_text(encoding="utf-8")
        forbidden_fragments = (
            "from dsm." + "core",
            "import dsm." + "core",
            "Stor" + "age",
            "DSMReadRelay",
            "read_recent",
            "core." + "storage",
        )
        for fragment in forbidden_fragments:
            assert fragment not in source


def test_gateway_is_not_in_kernel_path():
    for path in (GATEWAY_PATH, PROVIDERS_PATH):
        assert "src/dsm/core" not in path.as_posix()


def test_dsm_validation_is_deterministic_for_same_context_and_proposal(tmp_path):
    context = _context()
    provider = MockProposalProvider("unknown_claimed_check")
    first_raw = provider.propose(context)
    second_raw = json.loads(json.dumps(first_raw, sort_keys=True))
    first_wrapped = wrap_agent_proposal(context, first_raw, provider.metadata)
    second_wrapped = wrap_agent_proposal(context, second_raw, provider.metadata)

    first_validation = validate_agent_proposal(first_wrapped, context)
    second_validation = validate_agent_proposal(second_wrapped, context)
    first_mapping = agent_proposal_to_memory_records(first_wrapped, first_validation)
    second_mapping = agent_proposal_to_memory_records(second_wrapped, second_validation)
    first_persisted = persist_agent_proposal_to_memory(
        first_wrapped,
        first_validation,
        data_dir=tmp_path / "first",
    )
    second_persisted = persist_agent_proposal_to_memory(
        second_wrapped,
        second_validation,
        data_dir=tmp_path / "second",
    )

    assert first_validation == second_validation
    assert first_mapping == second_mapping
    assert _normalized_persisted(first_persisted) == _normalized_persisted(second_persisted)


def _run(scenario: str, tmp_path: Path) -> dict:
    return run_agent_proposal_gateway(
        load_records(RECORDS_PATH),
        provider=MockProposalProvider(scenario),
        data_dir=tmp_path / scenario,
        user_id="mohamed",
        domain="omari_ai",
        skill_id="omari_ai.lead_capture_reliability",
        task_type="prioritization_decision",
        known_inputs={
            "customer_name": "Before",
            "interruption_detected": True,
        },
    )


def _context() -> dict:
    return build_agent_proposal_context(
        load_records(RECORDS_PATH),
        user_id="mohamed",
        domain="omari_ai",
        skill_id="omari_ai.lead_capture_reliability",
        task_type="prioritization_decision",
        known_inputs={
            "customer_name": "Before",
            "interruption_detected": True,
        },
    )


def _codes(issues: list[dict]) -> set[str]:
    return {issue["code"] for issue in issues}


def _normalized_persisted(result: dict) -> list[dict]:
    return [
        {
            "role": entry["role"],
            "kind": entry["kind"],
            "shard": entry["shard"],
            "metadata": entry["metadata"],
        }
        for entry in result["persisted_entries"]
    ]

