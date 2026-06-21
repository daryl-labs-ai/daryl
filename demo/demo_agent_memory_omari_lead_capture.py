#!/usr/bin/env python3
"""Omari AI lead-capture Agent Memory dogfood demo.

Deterministic scenario: an agent answers a product prioritization question and
justifies the answer with DSM-backed fact -> hypothesis -> inference -> decision
entries. No LLM, no network, no external dependencies.

Usage:
    python demo/demo_agent_memory_omari_lead_capture.py
    python demo/demo_agent_memory_omari_lead_capture.py --data-dir /tmp/daryl-omari-agent-memory
"""

from __future__ import annotations

import argparse
import json
import shlex
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


QUESTION = (
    "Should Omari AI prioritize fixing lead-capture interruption before "
    "adding new sales features?"
)
FACT_LOSS_RATE = (
    "Sur les 30 derniers jours, 18% des soumissions du formulaire de "
    "lead-capture n'ont pas été persistées."
)
FACT_SINGLE_ENTRY = (
    "Le lead-capture est l'unique point d'entrée du pipeline commercial "
    "inbound ; aucun chemin de capture alternatif n'existe."
)
HYPOTHESIS_STABLE_VOLUME = (
    "Les nouvelles features commerciales envisagées supposent un volume de "
    "leads inbound stable pour démontrer une valeur mesurable."
)
INFERENCE_FIX_FIRST = (
    "Si une part significative des leads inbound est perdue à l'entrée, le "
    "revenu actuel et l'impact mesurable de toute nouvelle feature sont "
    "affaiblis tant que la capture n'est pas réparée."
)
DECISION_FIX_CAPTURE = (
    "Omari AI devrait réparer l'interruption de lead-capture avant d'ajouter "
    "de nouvelles features commerciales."
)
EXTERNAL_EVIDENCE_LIMITATION = (
    "Known V1 limitation: external evidence such as logs/tickets is not yet "
    "represented as first-class source_refs unless imported into DSM first."
)


def _ref(entry) -> dict[str, str]:
    return {"shard": entry.shard, "entry_hash": entry.hash}


def _short_hash(value: str) -> str:
    if not value:
        return ""
    return f"{value[:12]}...{value[-6:]}" if len(value) > 24 else value


def build_omari_lead_capture_decision(storage: Storage) -> dict[str, Any]:
    """Write the Omari chain to DSM and return the entries + explanation."""
    session_id = "demo_agent_memory_omari_lead_capture"

    loss_rate_fact = record_fact(
        FACT_LOSS_RATE,
        confidence=0.9,
        session_id=session_id,
        storage=storage,
    )
    single_entry_fact = record_fact(
        FACT_SINGLE_ENTRY,
        confidence=0.95,
        session_id=session_id,
        storage=storage,
    )
    stable_volume_hypothesis = record_hypothesis(
        HYPOTHESIS_STABLE_VOLUME,
        depends_on=[loss_rate_fact.hash, single_entry_fact.hash],
        source_refs=[_ref(loss_rate_fact), _ref(single_entry_fact)],
        confidence=0.7,
        session_id=session_id,
        storage=storage,
    )
    revenue_inference = record_inference(
        INFERENCE_FIX_FIRST,
        depends_on=[
            loss_rate_fact.hash,
            single_entry_fact.hash,
            stable_volume_hypothesis.hash,
        ],
        source_refs=[
            _ref(loss_rate_fact),
            _ref(single_entry_fact),
            _ref(stable_volume_hypothesis),
        ],
        confidence=0.85,
        session_id=session_id,
        storage=storage,
    )
    decision = record_decision(
        DECISION_FIX_CAPTURE,
        depends_on=[revenue_inference.hash],
        confidence=0.8,
        session_id=session_id,
        storage=storage,
    )

    explanation = explain_decision(decision.hash, storage=storage)
    verification = verify_shard(storage, DEFAULT_MEMORY_SHARD)

    return {
        "question": QUESTION,
        "entries": {
            "facts": [loss_rate_fact, single_entry_fact],
            "hypothesis": stable_volume_hypothesis,
            "inference": revenue_inference,
            "decision": decision,
        },
        "explanation": explanation,
        "verification": verification,
    }


def render_demo(result: dict[str, Any]) -> str:
    """Render the Omari scenario in a compact human-readable form."""
    entries = result["entries"]
    explanation = result["explanation"]
    verification = result["verification"]
    decision = explanation["decision"]
    dependencies = explanation["dependencies"]
    dependency_map = explanation["dependency_map"]
    status = verification["status"]
    status_str = status.value if hasattr(status, "value") else str(status)
    data_dir = result["data_dir"]
    decision_hash = decision["entry_hash"]
    cli_command = (
        f"python -m dsm memory explain {shlex.quote(decision_hash)} "
        f"--data-dir {shlex.quote(data_dir)} --shard {DEFAULT_MEMORY_SHARD} --markdown"
    )

    lines = [
        "Daryl Agent Memory - Omari Lead-Capture Decision Demo",
        "",
        f"Question: {result['question']}",
        f"Data dir: {data_dir}",
        f"Decision hash: {decision_hash}",
        "CLI markdown command:",
        f"  {cli_command}",
        "",
        "Decision:",
        f"  {decision['statement']}",
        f"  hash: {decision_hash}",
        "",
        "Facts:",
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
        f"  depends_on: {json.dumps(hypothesis_payload['depends_on'])}",
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
        f"  source_refs: {json.dumps(inference_payload['source_refs'], sort_keys=True)}",
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
        "External evidence limitation:",
        f"  {EXTERNAL_EVIDENCE_LIMITATION}",
        "",
        "Scope note:",
        "  DSM currently provides local tamper-evidence only. This demo does",
        "  not prove factual truth, reasoning validity, or external anchoring.",
    ])
    return "\n".join(lines)


def run_demo(
    data_dir: Optional[str] = None,
    *,
    print_output: bool = True,
) -> dict[str, Any]:
    """Run the demo and optionally print the rendered output."""
    if data_dir is None:
        tmp_dir = tempfile.mkdtemp(prefix="daryl_omari_agent_memory_demo_")
        data_dir = str(Path(tmp_dir) / "memory")

    storage = Storage(data_dir=data_dir)
    result = build_omari_lead_capture_decision(storage)
    result["data_dir"] = data_dir
    result["output"] = render_demo(result)

    if print_output:
        print(result["output"])

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Omari Agent Memory lead-capture dogfood demo.")
    parser.add_argument(
        "--data-dir",
        default=None,
        help="DSM data directory to write; defaults to a preserved temporary directory.",
    )
    args = parser.parse_args()
    run_demo(data_dir=args.data_dir)


if __name__ == "__main__":
    main()
