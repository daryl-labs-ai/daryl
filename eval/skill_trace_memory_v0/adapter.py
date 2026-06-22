#!/usr/bin/env python3
"""Persist deterministic skill execution traces through Agent Memory V1."""

from __future__ import annotations

import json
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


SKILL_TRACE_MEMORY_SCHEMA_VERSION = "skill_trace_memory.v0"
SKILL_TRACE_SCHEMA_VERSION = "skill_execution_trace.v0"
EXPLAIN_SCHEMA_VERSION = "agent_memory.explain.v1"
_EXPLAIN_SCOPE = "local tamper-evident; not external anchoring"
_ADAPTER_SOURCE = "skill_trace_memory_v0"


def skill_trace_to_agent_memory_records(trace: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a deterministic logical Agent Memory write plan for a trace."""
    _validate_trace(trace)

    return [
        _record_spec(
            role="trace_scope",
            kind="fact",
            statement=(
                "Skill trace scope: "
                f"schema_version={SKILL_TRACE_SCHEMA_VERSION}; "
                f"user_id={trace.get('user_id')}; "
                f"domain={trace.get('domain')}; "
                f"skill_id={trace.get('skill_id')}; "
                f"task_type={trace.get('task_type')}"
            ),
        ),
        _record_spec(
            role="required_checks",
            kind="fact",
            statement="Required checks: " + _stable_json(trace.get("required_checks") or []),
            depends_on_roles=["trace_scope"],
            source_ref_roles=["trace_scope"],
        ),
        _record_spec(
            role="missing_checks",
            kind="inference",
            statement="Missing checks requiring reasoner verification: "
            + _stable_json(trace.get("missing_checks") or []),
            depends_on_roles=["required_checks"],
            source_ref_roles=["required_checks"],
        ),
        _record_spec(
            role="applied_validated_rules",
            kind="fact",
            statement="Applied validated rules: "
            + _stable_json(trace.get("applied_validated_rules") or []),
            depends_on_roles=["trace_scope"],
            source_ref_roles=["trace_scope"],
        ),
        _record_spec(
            role="candidate_rules",
            kind="hypothesis",
            statement="Candidate rules remain candidates: "
            + _stable_json(trace.get("candidate_rules") or []),
            depends_on_roles=["trace_scope"],
            source_ref_roles=["trace_scope"],
        ),
        _record_spec(
            role="supporting_cases",
            kind="fact",
            statement="Supporting cases: " + _stable_json(trace.get("supporting_cases") or []),
            depends_on_roles=["trace_scope"],
            source_ref_roles=["trace_scope"],
        ),
        _record_spec(
            role="warnings",
            kind="fact",
            statement="Warnings and limitations surfaced by scaffold: "
            + _stable_json(trace.get("warnings") or []),
            depends_on_roles=["missing_checks"],
            source_ref_roles=["missing_checks"],
        ),
        _record_spec(
            role="trust_model",
            kind="fact",
            statement="Trust model: " + _stable_json(trace.get("trust_model") or {}),
            depends_on_roles=["trace_scope"],
            source_ref_roles=["trace_scope"],
        ),
        _record_spec(
            role="execution_scaffold",
            kind="inference",
            statement=(
                "Skill execution scaffold assembled from retrieved skill context; "
                "decision_status=not_produced; status=requires_reasoner; "
                "candidate rules remain candidate."
            ),
            depends_on_roles=[
                "required_checks",
                "missing_checks",
                "applied_validated_rules",
                "candidate_rules",
                "supporting_cases",
                "warnings",
                "trust_model",
            ],
            source_ref_roles=[
                "required_checks",
                "missing_checks",
                "applied_validated_rules",
                "candidate_rules",
                "supporting_cases",
                "warnings",
                "trust_model",
            ],
        ),
        _record_spec(
            role="decision_scaffold",
            kind="decision",
            statement="Skill execution scaffold only: "
            + _stable_json(trace.get("decision_scaffold") or {})
            + "; decision_status=not_produced; no business decision produced.",
            depends_on_roles=["execution_scaffold"],
            source_ref_roles=["execution_scaffold"],
        ),
    ]


def persist_skill_trace_to_agent_memory(
    trace: dict[str, Any],
    *,
    data_dir: Path | str,
    shard: str = DEFAULT_MEMORY_SHARD,
    max_depth: int = 3,
) -> dict[str, Any]:
    """Persist a skill trace via Agent Memory V1 and return its audit artifacts."""
    logical_mapping = skill_trace_to_agent_memory_records(trace)
    data_dir_text = str(data_dir)
    entries_by_role: dict[str, Any] = {}
    persisted_entries: list[dict[str, Any]] = []

    for spec in logical_mapping:
        depends_on = [
            entries_by_role[role].hash
            for role in spec.get("depends_on_roles", [])
        ]
        source_refs = [
            {
                "shard": entries_by_role[role].shard,
                "entry_hash": entries_by_role[role].hash,
            }
            for role in spec.get("source_ref_roles", [])
        ]
        entry = _write_spec(
            spec,
            data_dir=data_dir_text,
            shard=shard,
            depends_on=depends_on,
            source_refs=source_refs,
        )
        entries_by_role[spec["role"]] = entry
        persisted_entries.append(
            {
                "role": spec["role"],
                "kind": spec["kind"],
                "entry_hash": entry.hash,
                "shard": entry.shard,
                "depends_on": depends_on,
            }
        )

    decision = entries_by_role["decision_scaffold"]
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
        local_status="not_verified_by_adapter",
    )
    markdown = render_explain_markdown(explain_contract)

    return {
        "schema_version": SKILL_TRACE_MEMORY_SCHEMA_VERSION,
        "trace_schema_version": SKILL_TRACE_SCHEMA_VERSION,
        "decision_hash": decision.hash,
        "shard": shard,
        "logical_mapping": logical_mapping,
        "persisted_entries": persisted_entries,
        "explain": explain_contract,
        "markdown": markdown,
    }


def _write_spec(
    spec: dict[str, Any],
    *,
    data_dir: str,
    shard: str,
    depends_on: list[str],
    source_refs: list[dict[str, str]],
) -> Any:
    kwargs = {
        "data_dir": data_dir,
        "shard": shard,
        "source": _ADAPTER_SOURCE,
        "depends_on": depends_on,
        "source_refs": source_refs,
    }
    kind = spec["kind"]
    statement = spec["statement"]
    if kind == "fact":
        return record_fact(statement, **kwargs)
    if kind == "hypothesis":
        return record_hypothesis(statement, **kwargs)
    if kind == "inference":
        return record_inference(statement, **kwargs)
    if kind == "decision":
        return record_decision(statement, **kwargs)
    raise ValueError(f"unsupported Agent Memory kind: {kind}")


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
        "schema_version": EXPLAIN_SCHEMA_VERSION,
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
        "source_refs": _memory_contract_source_refs([decision, *supporting]),
        "verification": {
            "local_status": local_status,
            "hint": hint,
            "scope": _EXPLAIN_SCOPE,
        },
        "warnings": _memory_explain_warnings(explanation, query),
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


def _memory_contract_source_refs(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for record in records:
        owner_hash = record.get("entry_hash")
        for ref in record.get("source_refs", []) or []:
            shard = ref.get("shard")
            entry_hash = ref.get("entry_hash")
            key = (owner_hash, shard, entry_hash)
            if key in seen:
                continue
            seen.add(key)
            refs.append(
                {
                    "owner_kind": record.get("kind"),
                    "owner_entry_hash": owner_hash,
                    "shard": shard,
                    "entry_hash": entry_hash,
                }
            )
    return refs


def _memory_explain_warnings(
    explanation: dict[str, Any],
    query: dict[str, Any],
) -> list[dict[str, Any]]:
    warnings = [
        {
            "code": "missing_dependency",
            "message": f"Dependency not found: {ref}",
            "ref": ref,
        }
        for ref in explanation.get("missing_dependencies", [])
    ]

    supporting = explanation.get("supporting_entries", [])
    dependency_map = explanation.get("dependency_map", {})
    unexplored = [
        record.get("entry_hash")
        for record in supporting
        if record.get("depends_on") and record.get("entry_hash") not in dependency_map
    ]
    if unexplored:
        warnings.append(
            {
                "code": "depth_limit_reached",
                "message": (
                    f"Traversal stopped at depth {query['depth']}; "
                    "some dependencies may remain unexplored."
                ),
                "entry_hashes": unexplored,
            }
        )
    return warnings


def _record_spec(
    *,
    role: str,
    kind: str,
    statement: str,
    depends_on_roles: list[str] | None = None,
    source_ref_roles: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "role": role,
        "kind": kind,
        "statement": statement,
        "depends_on_roles": list(depends_on_roles or []),
        "source_ref_roles": list(source_ref_roles or []),
    }


def _validate_trace(trace: dict[str, Any]) -> None:
    if not isinstance(trace, dict):
        raise TypeError("trace must be a dict")
    if trace.get("trace_type") != SKILL_TRACE_SCHEMA_VERSION:
        raise ValueError(f"trace_type must be {SKILL_TRACE_SCHEMA_VERSION}")
    if not isinstance(trace.get("trust_model"), dict):
        raise ValueError("trace must include trust_model")
    scaffold = trace.get("decision_scaffold")
    if not isinstance(scaffold, dict):
        raise ValueError("trace must include decision_scaffold")
    if trace["trust_model"].get("decision_status") != "not_produced":
        raise ValueError("trace decision_status must be not_produced")
    if scaffold.get("status") != "requires_reasoner":
        raise ValueError("trace decision_scaffold.status must be requires_reasoner")


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
