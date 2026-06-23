"""Known-answer decision replay v0 — DSM as a pre-chain preparation layer.

This replays a strategic decision whose correct answer is already known:

    Should DSM become an on-chain authorization / blockchain proof system now,
    or should DSM remain an off-chain preparation / pre-commit trust layer
    before agents interact with blockchain infrastructure?

Known answer: DSM should remain an off-chain preparation / pre-commit trust
layer that complements blockchain, not replaces it.

The replay is deterministic, no-network, and mock-only. It uses the existing
Agent Proposal Gateway machinery (gateway -> validation -> Agent Memory audit ->
explain -> markdown) without adding any new infrastructure.

Honesty note: DSM validates form and honesty, not truth. It therefore does not
semantically judge "DSM should become a blockchain" as wrong — that correctness
lives in the encoded known-answer oracle below. What DSM *does* enforce, and what
this test exercises, is that the provider is never the authority: a provider
self-declared status is ignored, and a provider that overclaims truth is
rejected, with an audit trail produced either way.
"""

# DSM validates form/honesty/audit/status boundaries only.
# The known correct strategic answer (DSM stays off-chain / pre-commit)
# is asserted by the TEST ORACLE, not computed or "known" by DSM.
# accepted_for_audit means auditable form, never strategic correctness or truth.

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


# --- Known-answer oracle ----------------------------------------------------
#
# The encoded expected answer for the strategic decision. This is the oracle the
# replay compares against; it is intentionally explicit, not model-generated.

EXPECTED_ANSWER = {
    "stance": "off_chain_preparation_pre_commit_trust_layer",
    "complements_blockchain_not_replaces": True,
    "provides": [
        "proof of grounding",
        "proof of reasoning trace",
        "replayability",
        "auditability",
        "evidence of what context was used",
        "evidence of what was proposed, accepted, rejected, or left for review",
    ],
    "blockchain_role": "authorization / external anchoring deferred to later",
    "anchoring_is_immediate_role": False,
}

REJECTED_WRONG_ANSWERS = (
    "build witness/MMR/STH/anchoring now",
    "turn DSM into a blockchain",
    "treat DSM as source of truth",
    "let the provider/agent self-declare status",
    "build registry/dashboard/API/MCP/Custom GPT as immediate next step",
    "modify kernel/validation/status assignment",
)


def _oracle_classify_stance(proposal_text: str) -> str:
    """Test-owned oracle: grade the strategic stance of a proposal.

    This is the known-answer grader. It is deliberately part of the TEST, not
    DSM. DSM never computes this — it only validates form/honesty/audit/status.
    """
    text = proposal_text.lower()
    endorses_offchain = (
        ("off-chain" in text or "pre-commit" in text or "preparation layer" in text)
        and "remain" in text
    )
    endorses_onchain_now = (
        "become a blockchain" in text or "on-chain authorization layer now" in text
    )
    if endorses_offchain and not endorses_onchain_now:
        return "correct"
    if endorses_onchain_now and not endorses_offchain:
        return "wrong"
    return "ambiguous"


def test_expected_answer_oracle_is_well_formed():
    # Includes: the off-chain preparation stance and its guarantees.
    assert EXPECTED_ANSWER["stance"].startswith("off_chain")
    assert "pre_commit_trust_layer" in EXPECTED_ANSWER["stance"]
    assert EXPECTED_ANSWER["complements_blockchain_not_replaces"] is True
    provides = " ".join(EXPECTED_ANSWER["provides"]).lower()
    assert "proof of grounding" in provides
    assert "reasoning trace" in provides
    assert "replayability" in provides
    assert "auditability" in provides

    # Excludes: blockchain authorization / anchoring is deferred, not immediate.
    assert EXPECTED_ANSWER["anchoring_is_immediate_role"] is False
    assert "deferred" in EXPECTED_ANSWER["blockchain_role"].lower()

    # The wrong answers are explicitly enumerated as rejected.
    rejected = " ".join(REJECTED_WRONG_ANSWERS).lower()
    assert "turn dsm into a blockchain" in rejected
    assert "source of truth" in rejected
    assert "self-declare status" in rejected
    assert "witness/mmr/sth/anchoring now" in rejected
    assert "api/mcp/custom gpt" in rejected
    assert "kernel/validation/status assignment" in rejected


# --- Providers (mock, in-process) -------------------------------------------


class _OffChainPreparationProvider:
    """Proposes the known-correct off-chain pre-commit trust-layer answer."""

    metadata = {
        "kind": "mock",
        "name": "known-answer-offchain",
        "model": "known-answer-no-network",
        "base_url_label": "local-test",
    }

    def propose(self, context: dict) -> dict:
        required = list(context["required_checks"])
        structured = {
            "proposal": (
                "Recommend that DSM remain an off-chain preparation and "
                "pre-commit trust layer that complements blockchain "
                "infrastructure rather than replacing it. DSM should provide "
                "proof of grounding, a replayable reasoning trace, auditability, "
                "and evidence of what context was used and what was proposed, "
                "accepted, rejected, or left for human review. On-chain "
                "authorization and external anchoring can come later; they are "
                "deferred and are not the immediate DSM role."
            ),
            "model_proposed_action": (
                "Prepare an auditable pre-commit record; defer on-chain "
                "authorization and external anchoring to a later, separate step."
            ),
            "claimed_checks": required,
            "claimed_check_coverage": [
                {
                    "check_id": check,
                    "coverage": (
                        f"The proposal accounts for {check} as a preparation-layer "
                        "concern without claiming truth or final authority."
                    ),
                }
                for check in required
            ],
            "limitations": [
                "DSM remains an off-chain preparation / pre-commit trust layer; "
                "it does not become a blockchain.",
                "External anchoring and on-chain authorization are deferred, not "
                "the immediate role.",
                "DSM validates form and honesty, not truth; it is not a source "
                "of authority over facts.",
                "Provider proposals are untrusted; DSM keeps authority over "
                "validation status.",
            ],
            "candidate_rule_handling": "Candidate rules remain candidate.",
            "truth_claim": False,
        }
        return {
            "raw_output": json.dumps(structured, sort_keys=True),
            "structured_output": structured,
        }


class _OnChainBlockchainProvider:
    """Wrong strategy, but WELL-FORMED: argues DSM should go on-chain now.

    No self-status, no truth overclaim, no candidate promotion, honest
    limitations. It is strategically wrong per the oracle, yet it satisfies the
    DSM form/honesty contract and is therefore accepted_for_audit — exactly the
    point: accepted_for_audit is not strategic correctness.
    """

    metadata = {
        "kind": "mock",
        "name": "known-answer-onchain",
        "model": "known-answer-no-network",
        "base_url_label": "local-test",
    }

    def propose(self, context: dict) -> dict:
        required = list(context["required_checks"])
        structured = {
            "proposal": (
                "Recommend that DSM become a blockchain and act as the on-chain "
                "authorization layer now, replacing the off-chain preparation "
                "role."
            ),
            "model_proposed_action": (
                "Move authorization on-chain as the immediate next step."
            ),
            "claimed_checks": required,
            "claimed_check_coverage": [
                {
                    "check_id": check,
                    "coverage": (
                        f"The proposal accounts for {check} without claiming "
                        "truth or final authority."
                    ),
                }
                for check in required
            ],
            "limitations": [
                "This is a proposal for audit only, not a business decision.",
                "It does not establish factual truth or reasoning validity.",
                "Candidate rules remain candidate unless DSM marks them validated.",
            ],
            "candidate_rule_handling": "Candidate rules remain candidate.",
            "truth_claim": False,
        }
        return {
            "raw_output": json.dumps(structured, sort_keys=True),
            "structured_output": structured,
        }


class _OverreachingProvider:
    """Wrong answer: self-declares DSM status and overclaims truth/authority."""

    metadata = {
        "kind": "mock",
        "name": "known-answer-overreach",
        "model": "known-answer-no-network",
        "base_url_label": "local-test",
    }

    def propose(self, context: dict) -> dict:
        required = list(context["required_checks"])
        structured = {
            "proposal": (
                "DSM should become the on-chain source of verified truth now and "
                "the final truth for authorization decisions."
            ),
            "model_proposed_action": "Treat this proposal as verified truth.",
            "claimed_checks": required,
            "limitations": ["No limitations; the result is final truth."],
            "truth_claim": True,
        }
        return {
            "raw_output": json.dumps(structured, sort_keys=True),
            # The provider also tries to self-assign a DSM status.
            "structured_output": structured,
            "validation": {"status": ACCEPTED_FOR_AUDIT},
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


def test_offchain_decision_is_audited_and_matches_known_answer(tmp_path):
    result = _run(_OffChainPreparationProvider(), tmp_path, "offchain")

    validation = result["validation"]
    proposal = result["proposal"]
    persistence = result["persistence"]
    markdown = persistence["markdown"].lower()

    # The existing pipeline ran end to end and produced an audit.
    assert validation["status"] == ACCEPTED_FOR_AUDIT
    assert validation["warnings"] == []
    assert validation["rejections"] == []
    assert persistence["decision_hash"].startswith("v1:")
    assert persistence["explain"]["status"] == "ok"
    assert "# agent memory audit report" in markdown

    # The recorded proposal carries the known-correct answer.
    assert "off-chain" in markdown
    assert "pre-commit trust layer" in markdown
    assert "proof of grounding" in markdown
    assert "replayable reasoning trace" in markdown
    assert "auditability" in markdown
    assert "deferred" in markdown  # anchoring deferred, not immediate
    assert proposal["structured_output"]["truth_claim"] is False

    # It does not endorse any of the wrong stances.
    assert "dsm should become a blockchain" not in markdown
    assert "source of verified truth" not in markdown
    assert "build witness" not in markdown
    assert "final truth" not in markdown
    assert "promoted_candidate_rules" not in proposal["structured_output"]

    # The provider is recorded as untrusted; it did not assign DSM status.
    assert proposal["agent_supplied_status"] is None
    assert proposal["provider"] == _OffChainPreparationProvider.metadata


def test_overreaching_truth_and_self_status_is_rejected_with_audit(tmp_path):
    result = _run(_OverreachingProvider(), tmp_path, "overreach")

    validation = result["validation"]
    proposal = result["proposal"]
    persistence = result["persistence"]

    # Provider-as-truth is rejected on form/honesty grounds.
    assert validation["status"] == REJECTED_BY_VALIDATOR
    assert "overpromise_wording" in _codes(validation["rejections"])

    # Provider self-declared status is captured but ignored, never authoritative.
    assert proposal["agent_supplied_status"] == ACCEPTED_FOR_AUDIT
    assert "agent_supplied_status_ignored" in _codes(validation["warnings"])

    # Rejection is still auditable and explainable.
    assert persistence["decision_hash"].startswith("v1:")
    assert persistence["validation_status"] == REJECTED_BY_VALIDATOR
    assert persistence["explain"]["status"] == "ok"
    assert "# Agent Memory Audit Report" in persistence["markdown"]


def test_accepted_for_audit_is_not_strategic_correctness(tmp_path):
    # Case A: the strategically correct off-chain stance, well-formed.
    case_a = _run(_OffChainPreparationProvider(), tmp_path, "case-a")
    # Case B: the strategically WRONG on-chain stance, equally well-formed.
    case_b = _run(_OnChainBlockchainProvider(), tmp_path, "case-b")

    a_text = case_a["proposal"]["structured_output"]["proposal"]
    b_text = case_b["proposal"]["structured_output"]["proposal"]

    # DSM gives BOTH the same accepted_for_audit form status, with no warnings
    # and no rejections. Form/honesty was satisfied in both cases.
    assert case_a["validation"]["status"] == ACCEPTED_FOR_AUDIT
    assert case_b["validation"]["status"] == ACCEPTED_FOR_AUDIT
    assert case_a["validation"]["status"] == case_b["validation"]["status"]
    assert case_a["validation"]["warnings"] == []
    assert case_a["validation"]["rejections"] == []
    assert case_b["validation"]["warnings"] == []
    assert case_b["validation"]["rejections"] == []

    # Both produced an auditable, explainable record.
    assert case_a["persistence"]["explain"]["status"] == "ok"
    assert case_b["persistence"]["explain"]["status"] == "ok"

    # Only the TEST ORACLE separates correct from wrong strategy — DSM does not.
    assert _oracle_classify_stance(a_text) == "correct"
    assert _oracle_classify_stance(b_text) == "wrong"
    assert _oracle_classify_stance(a_text) != _oracle_classify_stance(b_text)

    # Therefore: accepted_for_audit != semantic truth / strategic correctness.
    # Same DSM status, opposite oracle verdicts.
    assert (
        case_a["validation"]["status"] == case_b["validation"]["status"]
        and _oracle_classify_stance(a_text) != _oracle_classify_stance(b_text)
    )
