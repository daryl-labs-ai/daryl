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
from tools.agent_proposal_gateway_v0 import gateway
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


# --- provider-output-normalization-v0 --------------------------------------
#
# The gateway must normalize fenced/raw JSON provider outputs into a structured
# proposal *before* validation. Normalization parses only; the existing
# validator still decides. Parsing JSON never implies accepted_for_audit.


METADATA = {
    "kind": "openai_compatible",
    "name": "lmstudio",
    "model": "meta/llama-3.3-70b",
    "base_url_label": "local-test",
}


def _conformant_structured(required_checks: list[str]) -> dict:
    return {
        "narrative": "Proposal scaffold accounts for each DSM-required check.",
        "model_proposed_action": "Send to audit; do not finalize a business outcome.",
        "claimed_checks": list(required_checks),
        "claimed_check_coverage": [
            {
                "check_id": check,
                "coverage": (
                    f"The proposal accounts for {check} without claiming truth."
                ),
            }
            for check in required_checks
        ],
        "limitations": [
            "Validated for form and honesty only, not factual truth.",
            "Candidate rules remain candidate unless DSM marks them validated.",
        ],
        "candidate_rule_handling": "Candidate rules remain candidate.",
        "truth_claim": False,
    }


def _fence(payload: dict) -> str:
    return "Here is my proposal:\n```json\n" + json.dumps(payload, indent=2) + "\n```\n"


def _wrap_and_validate(context: dict, raw_proposal: dict) -> tuple[dict, dict]:
    wrapped = wrap_agent_proposal(context, raw_proposal, METADATA)
    validation = validate_agent_proposal(wrapped, context)
    return wrapped, validation


def test_fenced_json_with_substantive_fields_is_normalized_and_validator_decides():
    context = _context()
    required = list(context["required_checks"])
    fenced = _fence(_conformant_structured(required))
    # The provider returned a markdown code fence; structured_output is the empty
    # narrative-only shape the OpenAI-compatible parser produces on a fence.
    raw_proposal = {
        "raw_output": fenced,
        "structured_output": {
            "narrative": fenced,
            "model_proposed_action": "",
            "claimed_checks": [],
            "limitations": [],
        },
    }

    wrapped, validation = _wrap_and_validate(context, raw_proposal)

    # Parsed in: claimed_checks now mirror required_checks rather than [].
    assert set(wrapped["structured_output"]["claimed_checks"]) == set(required)
    assert wrapped["structured_output"]["limitations"]
    # And the existing validator — not the normalization — accepts it.
    assert validation["status"] == ACCEPTED_FOR_AUDIT
    assert validation["rejections"] == []


def test_raw_json_string_is_normalized_into_structured_proposal():
    context = _context()
    required = list(context["required_checks"])
    raw_proposal = {
        "raw_output": json.dumps(_conformant_structured(required)),
        "structured_output": {},
    }

    wrapped, validation = _wrap_and_validate(context, raw_proposal)

    assert set(wrapped["structured_output"]["claimed_checks"]) == set(required)
    assert validation["status"] == ACCEPTED_FOR_AUDIT


def test_substantive_structured_output_wins_over_json_in_narrative():
    context = _context()
    required = list(context["required_checks"])
    real = _conformant_structured(required)
    # A different (decoy) JSON object is buried in raw_output/narrative; it must
    # NOT overwrite the genuine structured_output.
    decoy = _conformant_structured(required[:1])
    raw_proposal = {
        "raw_output": _fence(decoy),
        "structured_output": real,
    }

    wrapped, _ = _wrap_and_validate(context, raw_proposal)

    assert wrapped["structured_output"] is not decoy
    assert set(wrapped["structured_output"]["claimed_checks"]) == set(required)


def test_free_text_remains_fallback_and_is_not_accepted():
    context = _context()
    raw_proposal = {
        "raw_output": "I think this looks fine overall. No structured data here.",
        "structured_output": {},
    }

    wrapped, validation = _wrap_and_validate(context, raw_proposal)

    assert not wrapped["structured_output"].get("claimed_checks")
    assert validation["status"] != ACCEPTED_FOR_AUDIT
    assert validation["status"] == REJECTED_BY_VALIDATOR


def test_malformed_json_does_not_crash_and_is_not_accepted():
    context = _context()
    raw_proposal = {
        "raw_output": "```json\n{ claimed_checks: [unquoted, oops }\n```",
        "structured_output": {},
    }

    # Must not raise.
    wrapped, validation = _wrap_and_validate(context, raw_proposal)

    assert not wrapped["structured_output"].get("claimed_checks")
    assert validation["status"] in {REJECTED_BY_VALIDATOR, NEEDS_HUMAN_REVIEW}
    assert validation["status"] != ACCEPTED_FOR_AUDIT


def test_echo_only_fenced_json_is_parsed_but_still_not_accepted():
    context = _context()
    required = list(context["required_checks"])
    # Echo-only: required-check labels are echoed as dicts inside claimed_checks
    # with no substantive string claims and no surfacing in limitations.
    echo = {
        "proposal": "Echo-only proposal.",
        "claimed_checks": [{"check_id": check, "coverage": check} for check in required],
        "limitations": ["Labels were echoed without substantive coverage."],
        "candidate_rule_handling": "Candidate rules remain candidate.",
        "truth_claim": False,
    }
    raw_proposal = {"raw_output": _fence(echo), "structured_output": {}}

    wrapped, validation = _wrap_and_validate(context, raw_proposal)

    # Proof the JSON WAS parsed (normalization happened)...
    assert wrapped["structured_output"].get("proposal") == "Echo-only proposal."
    # ...yet normalization is not a disguised loosening: the validator rejects.
    assert validation["status"] != ACCEPTED_FOR_AUDIT
    assert validation["status"] == REJECTED_BY_VALIDATOR
    assert "required_check_not_covered_or_surfaced" in _codes(validation["rejections"])


def test_provider_self_status_in_fenced_json_cannot_assign_dsm_status():
    context = _context()
    required = list(context["required_checks"])
    # Conformant content, but the provider tries to self-assign a DSM status.
    payload = _conformant_structured(required)
    payload["validation_status"] = "rejected_by_validator"
    payload["status"] = "rejected_by_validator"
    payload["validation"] = {"status": "rejected_by_validator"}
    raw_proposal = {"raw_output": _fence(payload), "structured_output": {}}

    wrapped, validation = _wrap_and_validate(context, raw_proposal)

    # The provider's self-status is ignored: the validator independently accepts.
    assert validation["status"] == ACCEPTED_FOR_AUDIT
    # agent_supplied_status only tracks raw_proposal["validation"], not embedded JSON.
    assert wrapped["agent_supplied_status"] is None


def test_provider_self_accept_in_fenced_json_cannot_force_acceptance():
    context = _context()
    required = list(context["required_checks"])
    payload = _conformant_structured(required)
    # A hard violation plus a self-claimed acceptance must still be rejected.
    payload["narrative"] = "This proposal is guaranteed final truth for the business."
    payload["validation_status"] = "accepted_for_audit"
    raw_proposal = {"raw_output": _fence(payload), "structured_output": {}}

    _, validation = _wrap_and_validate(context, raw_proposal)

    assert validation["status"] == REJECTED_BY_VALIDATOR
    assert "overpromise_wording" in _codes(validation["rejections"])


def test_balanced_scanner_handles_nesting_arrays_and_strings():
    # Nested objects, arrays of dicts, braces inside strings, escaped quotes.
    text = (
        'prefix ```json {"a": {"b": [{"c": 1}], "s": "has { and } braces", '
        '"q": "escaped \\" quote"}} ``` trailing {"second": true}'
    )
    extracted = gateway._extract_json_object(text)

    assert extracted == {
        "a": {
            "b": [{"c": 1}],
            "s": "has { and } braces",
            "q": 'escaped " quote',
        }
    }


def test_extract_json_object_returns_none_for_free_text_and_malformed():
    assert gateway._extract_json_object("no json at all here") is None
    assert gateway._extract_json_object("```json { broken: ] ```") is None
    assert gateway._extract_json_object(None) is None
    # A bare JSON array (not an object) is not a structured proposal.
    assert gateway._extract_json_object("[1, 2, 3]") is None


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

