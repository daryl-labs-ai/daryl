from __future__ import annotations

import json
from pathlib import Path

from eval.skill_execution_v0 import (
    MAX_SCORE,
    compose_skill_trace,
    score_skill_trace,
)
from eval.skill_retrieval_v0 import load_records, retrieve_skill_context
from eval.skill_trace_memory_v0 import (
    SKILL_TRACE_MEMORY_SCHEMA_VERSION,
    persist_skill_trace_to_agent_memory,
    skill_trace_to_agent_memory_records,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
RECORDS_PATH = REPO_ROOT / "datasets" / "dsm_reasoning_v0" / "records.jsonl"
ADAPTER_PATH = REPO_ROOT / "eval" / "skill_trace_memory_v0" / "adapter.py"


def test_skill_trace_persists_to_agent_memory_and_markdown_audit(tmp_path):
    trace = _trace()
    assert score_skill_trace(trace, _retrieved_context())["score"] == MAX_SCORE

    result = persist_skill_trace_to_agent_memory(
        trace,
        data_dir=tmp_path / "data",
    )

    assert result["schema_version"] == SKILL_TRACE_MEMORY_SCHEMA_VERSION
    assert result["trace_schema_version"] == "skill_execution_trace.v0"
    assert result["decision_hash"].startswith("v1:")
    assert result["explain"]["schema_version"] == "agent_memory.explain.v1"
    assert result["explain"]["status"] == "ok"
    assert result["explain"]["query"]["decision_hash"] == result["decision_hash"]
    assert result["explain"]["query"]["depth"] == 3
    assert result["explain"]["decision"]["kind"] == "decision"

    markdown = result["markdown"]
    assert "# Agent Memory Audit Report" in markdown
    assert "## Trust Model / Limitations" in markdown
    assert "v1:" in markdown
    assert "skill_execution_trace.v0" in markdown
    assert "required_checks" in markdown or "Required checks" in markdown
    assert "external_evidence_limit_disclosed" in markdown
    assert "missing_required_check" in markdown
    assert "candidate_rule" in markdown
    assert "candidate rules remain candidate" in markdown
    assert "requires_reasoner" in markdown
    assert "not_produced" in markdown


def test_adapter_source_does_not_use_direct_storage():
    source = ADAPTER_PATH.read_text(encoding="utf-8")

    forbidden_fragments = (
        "from dsm." + "core",
        "import dsm." + "core",
        "Stor" + "age",
        "DSMReadRelay",
        "read_recent",
    )
    for fragment in forbidden_fragments:
        assert fragment not in source


def test_candidate_rules_remain_candidates_in_memory_audit(tmp_path):
    result = persist_skill_trace_to_agent_memory(
        _trace(),
        data_dir=tmp_path / "data",
    )

    statements = _all_explain_statements(result["explain"])
    candidate_statement = next(
        statement
        for statement in statements
        if statement.startswith("Candidate rules remain candidates:")
    )

    assert "skill-01-omari-lead-capture-correction" in candidate_statement
    assert '"rule_status":"candidate_rule"' in candidate_statement
    assert '"applied":false' in candidate_statement
    assert "validated_rule" not in candidate_statement


def test_decision_scaffold_does_not_persist_business_decision(tmp_path):
    result = persist_skill_trace_to_agent_memory(
        _trace(),
        data_dir=tmp_path / "data",
    )
    decision_statement = result["explain"]["decision"]["statement"]

    assert "Skill execution scaffold only" in decision_statement
    assert "requires_reasoner" in decision_statement
    assert "not_produced" in decision_statement
    assert "no business decision produced" in decision_statement
    assert "Prioritize fixing" not in decision_statement
    assert "Omari AI devrait" not in decision_statement


def test_trust_model_is_preserved_in_memory_audit(tmp_path):
    result = persist_skill_trace_to_agent_memory(
        _trace(),
        data_dir=tmp_path / "data",
    )

    statements = _all_explain_statements(result["explain"])
    trust_statement = next(
        statement
        for statement in statements
        if statement.startswith("Trust model:")
    )

    assert "deterministic_scaffold" in trust_statement
    assert "does not prove factual truth" in trust_statement
    assert "does not prove reasoning validity" in trust_statement
    assert "candidate rules remain candidates" in trust_statement


def test_scope_isolation_is_preserved_in_memory_audit(tmp_path):
    result = persist_skill_trace_to_agent_memory(
        _trace(),
        data_dir=tmp_path / "data",
    )
    serialized = json.dumps(result["explain"], sort_keys=True)

    assert "mohamed" in serialized
    assert "omari_ai" in serialized
    assert "omari_ai.lead_capture_reliability" in serialized
    assert "other_user" not in serialized
    assert "billing_ops" not in serialized
    assert "billing_ops.refund_triage" not in serialized


def test_skill_trace_mapping_is_logically_deterministic(tmp_path):
    trace = _trace()
    first_plan = skill_trace_to_agent_memory_records(trace)
    second_plan = skill_trace_to_agent_memory_records(trace)

    assert first_plan == second_plan

    first = persist_skill_trace_to_agent_memory(
        trace,
        data_dir=tmp_path / "first",
    )
    second = persist_skill_trace_to_agent_memory(
        trace,
        data_dir=tmp_path / "second",
    )

    assert first["logical_mapping"] == second["logical_mapping"]
    assert _normalized_persisted_entries(first) == _normalized_persisted_entries(second)


def test_agent_memory_explain_contains_expected_chain_shapes(tmp_path):
    result = persist_skill_trace_to_agent_memory(
        _trace(),
        data_dir=tmp_path / "data",
    )
    explain = result["explain"]

    facts = explain["supporting_chain"]["facts"]
    hypotheses = explain["supporting_chain"]["hypotheses"]
    inferences = explain["supporting_chain"]["inferences"]

    assert facts
    assert hypotheses
    assert inferences
    assert any("Required checks:" in entry["statement"] for entry in facts)
    assert any("Missing checks" in entry["statement"] for entry in inferences)
    assert any(
        "Skill execution scaffold assembled" in entry["statement"]
        for entry in inferences
    )
    assert explain["source_refs"]
    assert explain["verification"]["scope"] == "local tamper-evident; not external anchoring"
    assert result["markdown"].count("Entry hash: `v1:") >= 4


def _retrieved_context() -> dict:
    return retrieve_skill_context(
        load_records(RECORDS_PATH),
        user_id="mohamed",
        domain="omari_ai",
        skill_id="omari_ai.lead_capture_reliability",
        task_type="prioritization_decision",
    )


def _query() -> dict:
    return {
        "user_id": "mohamed",
        "domain": "omari_ai",
        "skill_id": "omari_ai.lead_capture_reliability",
        "task_type": "prioritization_decision",
        "known_inputs": {
            "customer_name": "Before",
            "interruption_detected": True,
            "phone_number": None,
            "denial_reason": None,
        },
    }


def _trace() -> dict:
    return compose_skill_trace(_retrieved_context(), _query())


def _all_explain_statements(explain: dict) -> list[str]:
    chain = explain["supporting_chain"]
    return [
        explain["decision"]["statement"],
        *[entry["statement"] for entry in chain["facts"]],
        *[entry["statement"] for entry in chain["hypotheses"]],
        *[entry["statement"] for entry in chain["inferences"]],
    ]


def _normalized_persisted_entries(result: dict) -> list[dict]:
    return [
        {
            "role": entry["role"],
            "kind": entry["kind"],
            "shard": entry["shard"],
        }
        for entry in result["persisted_entries"]
    ]
