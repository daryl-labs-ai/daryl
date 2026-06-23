"""Deterministic, no-network functional smoke for the Agent Proposal Gateway.

This exercises the full existing pipeline end to end with an in-process mock
provider only:

    mock provider output
    -> Agent Proposal Gateway
    -> DSM validation
    -> Agent Memory audit write
    -> explain decision
    -> markdown audit

It asserts the pipeline *functions* (status, hashes, audit, explain, markdown).
It does not assert business truth, repeatability, or reliability. No live
provider, no network, no new API, and no change to validation behavior.
"""

from __future__ import annotations

import json
from pathlib import Path

from eval.skill_retrieval_v0 import load_records
from tools.agent_proposal_gateway_v0 import (
    ACCEPTED_FOR_AUDIT,
    REJECTED_BY_VALIDATOR,
    run_agent_proposal_gateway,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
RECORDS_PATH = REPO_ROOT / "datasets" / "dsm_reasoning_v0" / "records.jsonl"


class _ConformantMockProvider:
    """In-process provider returning a full-contract, honest structured proposal."""

    metadata = {
        "kind": "mock",
        "name": "functional-conformant",
        "model": "functional-no-network",
        "base_url_label": "local-test",
    }

    def propose(self, context: dict) -> dict:
        required = list(context["required_checks"])
        structured = {
            "proposal": "Audit-ready scaffold that accounts for each required check.",
            "model_proposed_action": (
                "Send to audit; do not finalize a business outcome."
            ),
            "claimed_checks": required,
            "claimed_check_coverage": [
                {
                    "check_id": check,
                    "coverage": (
                        f"The proposal accounts for {check} without claiming truth "
                        "or final business authority."
                    ),
                }
                for check in required
            ],
            "limitations": [
                "Validated for form and honesty only, not factual truth.",
                "Candidate rules remain candidate unless DSM marks them validated.",
            ],
            "candidate_rule_handling": "Candidate rules remain candidate.",
            "truth_claim": False,
        }
        return {
            "raw_output": json.dumps(structured, sort_keys=True),
            "structured_output": structured,
        }


class _EchoOnlyMockProvider:
    """In-process provider that echoes check labels without substantive coverage."""

    metadata = {
        "kind": "mock",
        "name": "functional-echo-only",
        "model": "functional-no-network",
        "base_url_label": "local-test",
    }

    def propose(self, context: dict) -> dict:
        structured = {
            "proposal": "Echo-only proposal.",
            "claimed_checks": [
                {"check_id": check, "coverage": check}
                for check in context["required_checks"]
            ],
            "limitations": ["Labels were echoed without substantive coverage."],
            "candidate_rule_handling": "Candidate rules remain candidate.",
            "truth_claim": False,
        }
        return {
            "raw_output": json.dumps(structured, sort_keys=True),
            "structured_output": structured,
        }


def _run(provider, tmp_path: Path, name: str) -> dict:
    return run_agent_proposal_gateway(
        load_records(RECORDS_PATH),
        provider=provider,
        data_dir=tmp_path / name,
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


def test_functional_accepted_path_runs_gateway_validation_audit_explain_markdown(
    tmp_path,
):
    result = _run(_ConformantMockProvider(), tmp_path, "accepted")

    context = result["context"]
    proposal = result["proposal"]
    validation = result["validation"]
    persistence = result["persistence"]
    markdown = persistence["markdown"]

    # Validation decided accept with no warnings or rejections.
    assert validation["status"] == ACCEPTED_FOR_AUDIT
    assert validation["warnings"] == []
    assert validation["rejections"] == []
    assert validation["model_proposed"] is True

    # Hashes are present across context and wrapped proposal.
    assert context["input_context_hash"].startswith("v1:")
    assert proposal["input_context_hash"] == context["input_context_hash"]
    assert proposal["raw_output_hash"].startswith("v1:")

    # Provider metadata is carried through, untrusted but recorded.
    assert proposal["provider"] == _ConformantMockProvider.metadata
    assert proposal["agent_supplied_status"] is None

    # Agent Memory audit was written and is explainable.
    assert persistence["decision_hash"].startswith("v1:")
    assert persistence["validation_status"] == ACCEPTED_FOR_AUDIT
    assert persistence["model_proposed"] is True
    assert persistence["explain"]["status"] == "ok"

    # Markdown audit was produced with the expected, honest framing.
    assert "# Agent Memory Audit Report" in markdown
    assert ACCEPTED_FOR_AUDIT in markdown
    assert "Provider metadata" in markdown
    assert "raw_output_hash" in markdown
    assert '"business_decision":"not_produced"' in markdown

    # Candidate content stays candidate; nothing was auto-promoted.
    assert "promoted_candidate_rules" not in proposal["structured_output"]
    assert "remains candidate" in markdown


def test_functional_rejected_path_still_produces_auditable_explainable_record(
    tmp_path,
):
    # A small negative case: echo-only output is rejected, yet the audit trail
    # and explanation are still produced (rejection is auditable, not silent).
    result = _run(_EchoOnlyMockProvider(), tmp_path, "rejected")

    validation = result["validation"]
    persistence = result["persistence"]

    assert validation["status"] == REJECTED_BY_VALIDATOR
    assert "required_check_not_covered_or_surfaced" in _codes(validation["rejections"])

    # Audit still produced and still explainable on rejection.
    assert persistence["decision_hash"].startswith("v1:")
    assert persistence["validation_status"] == REJECTED_BY_VALIDATOR
    assert persistence["explain"]["status"] == "ok"
    assert "# Agent Memory Audit Report" in persistence["markdown"]
