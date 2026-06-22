#!/usr/bin/env python3
"""Provider-agnostic trust boundary for external agent proposals."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from dsm.memory import (
    DEFAULT_MEMORY_SHARD,
    explain_decision,
    record_decision,
    record_fact,
    record_hypothesis,
    record_inference,
    render_explain_markdown,
)
from dsm_primitives import hash_canonical
from eval.skill_execution_v0 import compose_skill_trace, score_skill_trace
from eval.skill_retrieval_v0 import load_records, retrieve_skill_context

from .providers import MockProposalProvider, ProposalProvider


AGENT_PROPOSAL_SCHEMA_VERSION = "agent_proposal.v0"
AGENT_PROPOSAL_CONTEXT_VERSION = "agent_proposal_context.v0"
AGENT_PROPOSAL_PROVIDER_CONTRACT_VERSION = "agent_proposal_provider_contract.v0"
ACCEPTED_FOR_AUDIT = "accepted_for_audit"
NEEDS_HUMAN_REVIEW = "needs_human_review"
REJECTED_BY_VALIDATOR = "rejected_by_validator"
ALLOWED_STATUSES = {
    ACCEPTED_FOR_AUDIT,
    NEEDS_HUMAN_REVIEW,
    REJECTED_BY_VALIDATOR,
}
_PROPOSAL_SOURCE = "agent_proposal_gateway_v0"
_EXPLAIN_SCOPE = "local tamper-evident; not external anchoring"
_OVERPROMISE_PHRASES = (
    "proven true",
    "verified truth",
    "guaranteed",
    "final truth",
    "truth verified",
    "business decision is final",
)


def build_agent_proposal_context(
    records: list[dict[str, Any]],
    *,
    user_id: str,
    domain: str,
    skill_id: str,
    task_type: str | None = None,
    known_inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    retrieved = retrieve_skill_context(
        records,
        user_id=user_id,
        domain=domain,
        skill_id=skill_id,
        task_type=task_type,
    )
    query = {
        "user_id": user_id,
        "domain": domain,
        "skill_id": skill_id,
        "task_type": task_type,
        "known_inputs": dict(known_inputs or {}),
    }
    skill_trace = compose_skill_trace(retrieved, query)
    trace_score = score_skill_trace(skill_trace, retrieved)
    required_checks = [item["check"] for item in skill_trace["required_checks"]]
    context_without_hash = {
        "context_type": AGENT_PROPOSAL_CONTEXT_VERSION,
        "scope": {
            "user_id": user_id,
            "domain": domain,
            "skill_id": skill_id,
        },
        "task_type": task_type,
        "required_checks": required_checks,
        "validated_rules": skill_trace["applied_validated_rules"],
        "candidate_rules": skill_trace["candidate_rules"],
        "supporting_cases": skill_trace["supporting_cases"],
        "trust_model": skill_trace["trust_model"],
        "skill_trace": skill_trace,
        "skill_trace_score": trace_score,
        "provider_contract": _provider_contract(required_checks),
        "instructions": {
            "role": "untrusted_proposer",
            "must_surface_each_required_check": True,
            "must_fill_claimed_checks_for_substantive_coverage": True,
            "must_include_coverage_written_by_model": True,
            "must_include_limitations": True,
            "must_not_claim_truth": True,
            "must_not_promote_candidate_rules": True,
            "must_not_assign_validation_status": True,
            "dsm_validates_form_and_honesty_not_truth": True,
            "proposal_not_decision": True,
        },
    }
    return {
        **context_without_hash,
        "input_context_hash": hash_canonical(context_without_hash),
    }


def _provider_contract(required_checks: list[str]) -> dict[str, Any]:
    return {
        "contract_version": AGENT_PROPOSAL_PROVIDER_CONTRACT_VERSION,
        "provider_role": "untrusted_proposer",
        "trust_boundary": {
            "provider_never_assigns_status": True,
            "claimed_checks_are_not_trusted_as_truth": True,
            "dsm_validates": "form/honesty, not truth",
        },
        "must": [
            "You must surface each required_check.",
            "Fill claimed_checks with each required_check you substantively covered.",
            "Each claimed_check must have model-written coverage in claimed_check_coverage.",
            "Include limitations.",
        ],
        "must_not": [
            "Do not assign status.",
            "Do not claim truth.",
            "Do not auto-promote candidate rules.",
        ],
        "required_checks": list(required_checks),
        "expected_structured_output": {
            "proposal": "string written by the model",
            "claimed_checks": list(required_checks),
            "claimed_check_coverage": [
                {
                    "check_id": check,
                    "coverage": "substantive explanation written by the model",
                }
                for check in required_checks
            ],
            "limitations": ["limitation written by the model"],
            "candidate_rule_handling": "string written by the model",
            "truth_claim": False,
        },
        "notes": [
            "Do not copy coverage text from this contract; write your own coverage.",
            "Do not inject or infer validation_status.",
            "DSM validates form/honesty, not truth.",
            "Provider output is a proposal, not a business decision.",
        ],
    }


def wrap_agent_proposal(
    context: dict[str, Any],
    raw_proposal: dict[str, Any],
    provider_metadata: dict[str, str],
) -> dict[str, Any]:
    raw_output = raw_proposal.get("raw_output", "")
    structured = raw_proposal.get("structured_output") or {}
    if not isinstance(structured, dict):
        structured = {"narrative": str(structured)}
    raw_hash_payload = {
        "raw_output": raw_output,
        "structured_output": structured,
        "provider": provider_metadata,
    }
    return {
        "schema_version": AGENT_PROPOSAL_SCHEMA_VERSION,
        "proposal_type": AGENT_PROPOSAL_SCHEMA_VERSION,
        "provider": dict(provider_metadata),
        "scope": dict(context["scope"]),
        "input_context_hash": context["input_context_hash"],
        "raw_output_hash": hash_canonical(raw_hash_payload),
        "raw_output": raw_output,
        "structured_output": structured,
        "agent_supplied_status": _agent_supplied_status(raw_proposal),
        "model_proposed": True,
    }


def validate_agent_proposal(
    wrapped_proposal: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    hard: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    structured = wrapped_proposal.get("structured_output") or {}
    text = _proposal_text(wrapped_proposal)

    if wrapped_proposal.get("agent_supplied_status") is not None:
        warnings.append(
            _issue(
                "agent_supplied_status_ignored",
                "Agent-supplied validation status was ignored.",
                value=wrapped_proposal.get("agent_supplied_status"),
            )
        )

    for phrase in _OVERPROMISE_PHRASES:
        if phrase in text:
            hard.append(
                _issue(
                    "overpromise_wording",
                    "Proposal over-promises truth or finality.",
                    phrase=phrase,
                )
            )

    if _promoted_candidate_rules(structured):
        hard.append(
            _issue(
                "candidate_rule_promotion",
                "Proposal attempts to promote candidate rules.",
                candidate_rules=_promoted_candidate_rules(structured),
            )
        )

    scope_violation = _scope_violation(wrapped_proposal, context)
    if scope_violation:
        hard.append(scope_violation)

    check_result = _validate_claimed_checks(structured, context)
    hard.extend(check_result["hard"])
    warnings.extend(check_result["warnings"])

    if not structured.get("limitations"):
        warnings.append(
            _issue(
                "missing_limitations",
                "Proposal does not surface limitations.",
            )
        )
    if structured.get("coverage_level") == "low":
        warnings.append(
            _issue(
                "low_coverage",
                "Proposal declares low coverage.",
            )
        )

    if hard:
        status = REJECTED_BY_VALIDATOR
    elif warnings:
        status = NEEDS_HUMAN_REVIEW
    else:
        status = ACCEPTED_FOR_AUDIT

    return {
        "schema_version": AGENT_PROPOSAL_SCHEMA_VERSION,
        "status": status,
        "allowed_statuses": sorted(ALLOWED_STATUSES),
        "model_proposed": True,
        "warnings": warnings,
        "rejections": hard,
        "metadata": _proposal_metadata(wrapped_proposal, status),
    }


def run_agent_proposal_gateway(
    records: list[dict[str, Any]],
    *,
    provider: ProposalProvider,
    data_dir: Path | str,
    user_id: str,
    domain: str,
    skill_id: str,
    task_type: str | None = None,
    known_inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = build_agent_proposal_context(
        records,
        user_id=user_id,
        domain=domain,
        skill_id=skill_id,
        task_type=task_type,
        known_inputs=known_inputs,
    )
    raw_proposal = provider.propose(context)
    wrapped = wrap_agent_proposal(context, raw_proposal, provider.metadata)
    validation = validate_agent_proposal(wrapped, context)
    persistence = persist_agent_proposal_to_memory(
        wrapped,
        validation,
        data_dir=data_dir,
    )
    return {
        "context": context,
        "proposal": wrapped,
        "validation": validation,
        "persistence": persistence,
    }


def agent_proposal_to_memory_records(
    wrapped_proposal: dict[str, Any],
    validation: dict[str, Any],
) -> list[dict[str, Any]]:
    metadata = validation["metadata"]
    structured = wrapped_proposal.get("structured_output") or {}
    status = validation["status"]
    decision_kind = (
        "rejected_proposal_audit"
        if status == REJECTED_BY_VALIDATOR
        else "proposal_scaffold"
    )
    decision_flags = {
        "decision_kind": decision_kind,
        "business_decision": "not_produced",
        "validation_status": status,
        "model_proposed": True,
    }
    if status == NEEDS_HUMAN_REVIEW:
        decision_flags["requires_human_review"] = True
    if status == REJECTED_BY_VALIDATOR:
        decision_flags["rejected"] = True

    return [
        _record_spec(
            role="proposal_metadata",
            kind="fact",
            statement="Agent proposal metadata: " + _stable_json(metadata),
            metadata=metadata,
        ),
        _record_spec(
            role="provider",
            kind="fact",
            statement="Provider metadata: " + _stable_json(wrapped_proposal["provider"]),
            metadata=metadata,
            depends_on_roles=["proposal_metadata"],
        ),
        _record_spec(
            role="proposal_scope",
            kind="fact",
            statement="Proposal scope: " + _stable_json(wrapped_proposal["scope"]),
            metadata=metadata,
            depends_on_roles=["proposal_metadata"],
        ),
        _record_spec(
            role="raw_output",
            kind="fact",
            statement="Raw provider output hash: " + wrapped_proposal["raw_output_hash"],
            metadata=metadata,
            depends_on_roles=["provider", "proposal_scope"],
        ),
        _record_spec(
            role="structured_output",
            kind="inference",
            statement="Structured provider proposal: " + _stable_json(structured),
            metadata=metadata,
            depends_on_roles=["raw_output"],
        ),
        _record_spec(
            role="candidate_content",
            kind="hypothesis",
            statement="Candidate-related content remains candidate: "
            + _stable_json(structured.get("promoted_candidate_rules") or []),
            metadata=metadata,
            depends_on_roles=["structured_output"],
        ),
        _record_spec(
            role="validation",
            kind="inference",
            statement="DSM validation result: " + _stable_json(validation),
            metadata=metadata,
            depends_on_roles=[
                "proposal_metadata",
                "provider",
                "structured_output",
                "candidate_content",
            ],
        ),
        _record_spec(
            role="decision_anchor",
            kind="decision",
            statement="Agent proposal audit anchor: " + _stable_json(decision_flags),
            metadata=metadata,
            depends_on_roles=["validation"],
        ),
    ]


def persist_agent_proposal_to_memory(
    wrapped_proposal: dict[str, Any],
    validation: dict[str, Any],
    *,
    data_dir: Path | str,
    shard: str = DEFAULT_MEMORY_SHARD,
    max_depth: int = 3,
) -> dict[str, Any]:
    logical_mapping = agent_proposal_to_memory_records(wrapped_proposal, validation)
    entries_by_role: dict[str, Any] = {}
    persisted_entries: list[dict[str, Any]] = []
    data_dir_text = str(data_dir)

    for spec in logical_mapping:
        depends_on = [
            entries_by_role[role].hash
            for role in spec.get("depends_on_roles", [])
        ]
        entry = _write_spec(
            spec,
            data_dir=data_dir_text,
            shard=shard,
            depends_on=depends_on,
        )
        entries_by_role[spec["role"]] = entry
        persisted_entries.append(
            {
                "role": spec["role"],
                "kind": spec["kind"],
                "shard": entry.shard,
                "entry_hash": entry.hash,
                "depends_on": depends_on,
                "metadata": spec["metadata"],
            }
        )

    decision = entries_by_role["decision_anchor"]
    explanation = explain_decision(
        decision.hash,
        data_dir=data_dir_text,
        shard=shard,
        max_depth=max_depth,
    )
    query = {
        "decision_hash": decision.hash,
        "shard": shard,
        "depth": max_depth,
    }
    explain_contract = _memory_explain_contract(
        explanation,
        query,
        local_status="not_verified_by_gateway",
    )
    return {
        "schema_version": AGENT_PROPOSAL_SCHEMA_VERSION,
        "decision_hash": decision.hash,
        "validation_status": validation["status"],
        "model_proposed": True,
        "logical_mapping": logical_mapping,
        "persisted_entries": persisted_entries,
        "explain": explain_contract,
        "markdown": render_explain_markdown(explain_contract),
    }


def accepted_proposals_for_retrieval(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        record
        for record in records
        if record.get("validation_status") == ACCEPTED_FOR_AUDIT
    ]


def _write_spec(
    spec: dict[str, Any],
    *,
    data_dir: str,
    shard: str,
    depends_on: list[str],
) -> Any:
    kwargs = {
        "data_dir": data_dir,
        "shard": shard,
        "source": _PROPOSAL_SOURCE,
        "depends_on": depends_on,
    }
    statement = spec["statement"]
    kind = spec["kind"]
    if kind == "fact":
        return record_fact(statement, **kwargs)
    if kind == "hypothesis":
        return record_hypothesis(statement, **kwargs)
    if kind == "inference":
        return record_inference(statement, **kwargs)
    if kind == "decision":
        return record_decision(statement, **kwargs)
    raise ValueError(f"unsupported memory kind: {kind}")


def _validate_claimed_checks(
    structured: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    hard: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    required = set(context.get("required_checks") or [])
    claimed = {
        item
        for item in structured.get("claimed_checks") or []
        if isinstance(item, str)
    }
    surfaced = _surfaced_checks(structured)

    for check in sorted(required - claimed - surfaced):
        hard.append(
            _issue(
                "required_check_not_covered_or_surfaced",
                "Required check is neither claimed nor surfaced as a limitation.",
                check=check,
            )
        )
    for check in sorted(claimed - required):
        warnings.append(
            _issue(
                "claimed_check_outside_required",
                "Claimed check is outside required_checks.",
                check=check,
            )
        )
    return {"hard": hard, "warnings": warnings}


def _surfaced_checks(structured: dict[str, Any]) -> set[str]:
    items = [
        *list(structured.get("limitations") or []),
        *list(structured.get("warnings") or []),
        *list(structured.get("surfaced_missing_checks") or []),
    ]
    text = " ".join(str(item) for item in items)
    surfaced = set()
    for token in text.replace(",", " ").replace(";", " ").split():
        cleaned = token.strip(" .:`'\"")
        if cleaned:
            surfaced.add(cleaned)
    return surfaced


def _promoted_candidate_rules(structured: dict[str, Any]) -> list[Any]:
    explicit = list(structured.get("promoted_candidate_rules") or [])
    rules = [
        rule
        for rule in structured.get("candidate_rules") or []
        if isinstance(rule, dict)
        and (
            rule.get("rule_status") == "validated_rule"
            or rule.get("applied") is True
        )
    ]
    text = _stable_json(structured).lower()
    if "candidate rules are validated" in text:
        explicit.append("textual_candidate_promotion")
    return [*explicit, *rules]


def _scope_violation(
    wrapped_proposal: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any] | None:
    expected = context["scope"]
    structured = wrapped_proposal.get("structured_output") or {}
    candidate_scopes = [
        structured.get("scope"),
        structured.get("referenced_scope"),
    ]
    for scope in candidate_scopes:
        if not isinstance(scope, dict):
            continue
        for key in ("user_id", "domain", "skill_id"):
            if scope.get(key) is not None and scope.get(key) != expected.get(key):
                return _issue(
                    "scope_leak",
                    "Proposal references scope outside DSM context.",
                    expected=expected,
                    observed=scope,
                )
    text = _proposal_text(wrapped_proposal)
    if "other_user" in text or "billing_ops" in text:
        return _issue(
            "scope_leak",
            "Proposal text contains a known out-of-scope marker.",
        )
    return None


def _agent_supplied_status(raw_proposal: dict[str, Any]) -> str | None:
    validation = raw_proposal.get("validation")
    if not isinstance(validation, dict):
        return None
    status = validation.get("status")
    return status if isinstance(status, str) else None


def _proposal_metadata(wrapped_proposal: dict[str, Any], status: str) -> dict[str, Any]:
    return {
        "proposal_type": AGENT_PROPOSAL_SCHEMA_VERSION,
        "provider": wrapped_proposal["provider"],
        "input_context_hash": wrapped_proposal["input_context_hash"],
        "raw_output_hash": wrapped_proposal["raw_output_hash"],
        "validation_status": status,
        "model_proposed": True,
        "schema_version": AGENT_PROPOSAL_SCHEMA_VERSION,
    }


def _memory_explain_contract(
    explanation: dict[str, Any],
    query: dict[str, Any],
    *,
    local_status: str,
) -> dict[str, Any]:
    decision = explanation["decision"]
    supporting = explanation.get("supporting_entries", [])
    verification = explanation.get("verification", {})
    hint = verification.get("hint", f"dsm verify --shard {query['shard']}")
    return {
        "schema_version": "agent_memory.explain.v1",
        "query": query,
        "status": "ok",
        "decision": _memory_contract_record(decision),
        "supporting_chain": {
            "facts": [
                _memory_contract_record(record)
                for record in supporting
                if record.get("kind") == "fact"
            ],
            "hypotheses": [
                _memory_contract_record(record)
                for record in supporting
                if record.get("kind") == "hypothesis"
            ],
            "inferences": [
                _memory_contract_record(record)
                for record in supporting
                if record.get("kind") == "inference"
            ],
        },
        "source_refs": [],
        "verification": {
            "local_status": local_status,
            "hint": hint,
            "scope": _EXPLAIN_SCOPE,
        },
        "warnings": [],
    }


def _memory_contract_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "entry_hash": record.get("entry_hash"),
        "kind": record.get("kind"),
        "statement": record.get("statement"),
        "depends_on": list(record.get("depends_on") or []),
        "source_refs": list(record.get("source_refs") or []),
        "confidence": record.get("confidence"),
    }


def _record_spec(
    *,
    role: str,
    kind: str,
    statement: str,
    metadata: dict[str, Any],
    depends_on_roles: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "role": role,
        "kind": kind,
        "statement": statement,
        "metadata": metadata,
        "depends_on_roles": list(depends_on_roles or []),
    }


def _proposal_text(wrapped_proposal: dict[str, Any]) -> str:
    return (
        str(wrapped_proposal.get("raw_output", ""))
        + "\n"
        + _stable_json(wrapped_proposal.get("structured_output") or {})
    ).lower()


def _issue(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "message": message, **extra}


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    args = list(argv or sys.argv[1:])
    if len(args) != 5 or args[0] != "run" or args[1] != "--provider":
        print(
            "usage: gateway.py run --provider mock RECORDS_JSONL DATA_DIR",
            file=sys.stderr,
        )
        return 2
    provider_name, records_path, data_dir = args[2], args[3], args[4]
    if provider_name != "mock":
        print("only mock provider is supported by this dogfood script", file=sys.stderr)
        return 2
    result = run_agent_proposal_gateway(
        load_records(records_path),
        provider=MockProposalProvider("golden"),
        data_dir=data_dir,
        user_id="mohamed",
        domain="omari_ai",
        skill_id="omari_ai.lead_capture_reliability",
        task_type="prioritization_decision",
        known_inputs={
            "customer_name": "Before",
            "interruption_detected": True,
        },
    )
    print("validated for form/honesty, not truth")
    print(result["persistence"]["markdown"], end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
