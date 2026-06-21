#!/usr/bin/env python3
"""Agent Memory justified-answer demo.

Deterministic scenario: an agent answers a simple operational question and
justifies the answer with DSM-backed fact -> hypothesis -> inference -> decision
entries. No LLM, no network, no external dependencies.

Usage:
    python demo/demo_agent_memory_justified_answer.py
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Optional

from dsm.core.storage import Storage
from dsm.memory import (
    DEFAULT_MEMORY_SHARD,
    explain_decision,
    record_decision,
    record_fact,
    record_hypothesis,
    record_inference,
)
from dsm.verify import verify_shard


QUESTION = "Should the agent recommend replacing the used board immediately?"


def _ref(entry) -> dict[str, str]:
    return {"shard": entry.shard, "entry_hash": entry.hash}


def _short_hash(value: str) -> str:
    if not value:
        return ""
    return f"{value[:12]}...{value[-6:]}" if len(value) > 24 else value


def build_justified_answer(storage: Storage) -> dict[str, Any]:
    """Write the demo chain to DSM and return the recorded entries + explanation."""
    session_id = "demo_agent_memory_justified_answer"

    downtime_fact = record_fact(
        "Downtime costs $50,000 per day.",
        confidence=1.0,
        session_id=session_id,
        storage=storage,
    )
    board_cost_fact = record_fact(
        "A used replacement board costs $40,000.",
        confidence=1.0,
        session_id=session_id,
        storage=storage,
    )
    installation_hypothesis = record_hypothesis(
        "The used board can be sourced and installed quickly.",
        source_refs=[_ref(board_cost_fact)],
        confidence=0.7,
        session_id=session_id,
        storage=storage,
    )
    economic_inference = record_inference(
        "If the board restores operation within one day, replacement is economically justified.",
        depends_on=[downtime_fact.hash, board_cost_fact.hash, installation_hypothesis.hash],
        confidence=0.85,
        session_id=session_id,
        storage=storage,
    )
    decision = record_decision(
        "Recommend replacing the board immediately while separately planning a fleet-level obsolescence strategy.",
        depends_on=[economic_inference.hash],
        confidence=0.8,
        session_id=session_id,
        storage=storage,
    )

    explanation = explain_decision(decision.hash, storage=storage)
    verification = verify_shard(storage, DEFAULT_MEMORY_SHARD)

    return {
        "question": QUESTION,
        "entries": {
            "facts": [downtime_fact, board_cost_fact],
            "hypothesis": installation_hypothesis,
            "inference": economic_inference,
            "decision": decision,
        },
        "explanation": explanation,
        "verification": verification,
    }


def render_demo(result: dict[str, Any]) -> str:
    """Render the scenario in a compact human-readable form."""
    entries = result["entries"]
    explanation = result["explanation"]
    verification = result["verification"]
    decision = explanation["decision"]
    dependencies = explanation["dependencies"]
    dependency_map = explanation["dependency_map"]
    status = verification["status"]
    status_str = status.value if hasattr(status, "value") else str(status)

    lines = [
        "Daryl Agent Memory — First Justified Answer Demo",
        "",
        f"Question: {result['question']}",
        "",
        "Decision:",
        f"  {decision['statement']}",
        f"  hash: {decision['entry_hash']}",
        "",
        "Supporting facts:",
    ]
    for fact in entries["facts"]:
        payload = json.loads(fact.content)
        lines.append(f"  - {payload['statement']}")
        lines.append(f"    hash: {fact.hash}")

    hypothesis = entries["hypothesis"]
    hypothesis_payload = json.loads(hypothesis.content)
    lines.extend([
        "",
        "Hypothesis:",
        f"  {hypothesis_payload['statement']}",
        f"  hash: {hypothesis.hash}",
        f"  source_refs: {json.dumps(hypothesis_payload['source_refs'], sort_keys=True)}",
        "",
        "Inference:",
    ])
    inference = entries["inference"]
    inference_payload = json.loads(inference.content)
    lines.extend([
        f"  {inference_payload['statement']}",
        f"  hash: {inference.hash}",
        f"  depends_on: {json.dumps(inference_payload['depends_on'])}",
        "",
        "explain_decision:",
        f"  direct_dependencies: {[d['entry_hash'] for d in dependencies]}",
    ])
    for parent_hash, nested in dependency_map.items():
        lines.append(
            f"  nested_dependencies[{_short_hash(parent_hash)}]: "
            f"{[item['entry_hash'] for item in nested]}"
        )

    lines.extend([
        "",
        "DSM verification:",
        f"  shard: {DEFAULT_MEMORY_SHARD}",
        f"  status: {status_str}",
        f"  total_entries: {verification['total_entries']}",
        "",
        "Scope note:",
        "  DSM currently provides tamper-evidence in local trust. Strong proof",
        "  against fully privileged local rewrite remains out of scope without",
        "  future witness / anchoring work.",
    ])
    return "\n".join(lines)


def run_demo(
    data_dir: Optional[str] = None,
    *,
    print_output: bool = True,
) -> dict[str, Any]:
    """Run the demo and optionally print the rendered output."""
    owned_tmp: Optional[str] = None
    if data_dir is None:
        owned_tmp = tempfile.mkdtemp(prefix="daryl_agent_memory_demo_")
        data_dir = str(Path(owned_tmp) / "memory")

    storage = Storage(data_dir=data_dir)
    result = build_justified_answer(storage)
    result["data_dir"] = data_dir
    result["output"] = render_demo(result)

    if print_output:
        print(result["output"])

    if owned_tmp is not None:
        shutil.rmtree(owned_tmp, ignore_errors=True)

    return result


def main() -> None:
    run_demo()


if __name__ == "__main__":
    main()
