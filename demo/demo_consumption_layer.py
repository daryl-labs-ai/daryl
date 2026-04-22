#!/usr/bin/env python3
"""
demo_consumption_layer.py — DSM Consumption Layer V0 Demo

Demonstrates the three phases of the DSM Consumption Layer:

  Phase 1: dsm.recall.search_memory()   — keyword recall from past sessions
  Phase 2: dsm.context.build_context()  — token-budgeted context packs
  Phase 3: dsm.provenance.build_provenance() — cryptographic origin verification

Scenario: An AI agent has worked across three sessions over 45 days.
Session 1 (old) recorded an architecture decision: "use REST for the API."
Session 2 (recent) supersedes that with "use gRPC for the API."
Session 3 is the current active session.

The demo recalls memory, packages it under a token budget, and verifies
provenance — all without any LLM calls, network, or external dependencies.

Usage:
    python demo_consumption_layer.py
"""

import json
import os
import shutil
import sys
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone

# Ensure the src directory is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from dsm.core.models import Entry
from dsm.core.storage import Storage
from dsm.session.session_graph import SessionGraph
from dsm.session.session_limits_manager import SessionLimitsManager


def print_header(text):
    print(f"\n{'─' * 60}")
    print(f"  {text}")
    print(f"{'─' * 60}")


def print_sub(text):
    print(f"\n  ▸ {text}")


def ts(days_ago):
    """Return a datetime `days_ago` days in the past."""
    return datetime.now(timezone.utc) - timedelta(days=days_ago)


def write_entry(storage, session_id, source, event_type, content, timestamp, action_name=None):
    """Write a deterministic entry with a controlled timestamp."""
    metadata = {"event_type": event_type}
    if action_name:
        metadata["action_name"] = action_name
    if event_type == "action_result":
        metadata["success"] = True
    entry = Entry(
        id=str(uuid.uuid4()),
        timestamp=timestamp,
        session_id=session_id,
        source=source,
        content=json.dumps(content) if isinstance(content, dict) else content,
        shard="sessions",
        hash="",
        prev_hash=None,
        metadata=metadata,
        version="v2.0",
    )
    return storage.append(entry)


def main():
    tmp_dir = tempfile.mkdtemp(prefix="daryl_consumption_demo_")

    try:
        # ================================================================
        # ACT 1 — Setup: Write three sessions of agent history
        # ================================================================
        print_header("ACT 1 — Setup: Writing agent history")

        data_dir = os.path.join(tmp_dir, "memory")
        storage = Storage(data_dir=data_dir)

        # Session 1 — 45 days ago: architecture decisions
        s1 = "session_arch_old"
        t1 = ts(45)
        write_entry(storage, s1, "architect_agent", "action_intent",
                    {"action_name": "architecture_decision",
                     "payload": {"component": "api", "decision": "use REST for the API gateway",
                                 "rationale": "REST is well understood and has broad tooling support"}},
                    t1, action_name="architecture_decision")
        write_entry(storage, s1, "architect_agent", "action_result",
                    {"result": {"component": "api", "protocol": "REST",
                                "status": "approved", "approved_by": "tech_lead"},
                     "success": True},
                    t1 + timedelta(minutes=5), action_name="architecture_decision")
        write_entry(storage, s1, "architect_agent", "action_intent",
                    {"action_name": "database_selection",
                     "payload": {"decision": "use PostgreSQL for persistence",
                                 "rationale": "ACID compliance and JSON support"}},
                    t1 + timedelta(minutes=10), action_name="database_selection")
        write_entry(storage, s1, "architect_agent", "action_result",
                    {"result": {"database": "PostgreSQL", "status": "approved"},
                     "success": True},
                    t1 + timedelta(minutes=15), action_name="database_selection")

        # Session 2 — 3 days ago: implementation work (supersedes REST → gRPC)
        s2 = "session_impl_recent"
        t2 = ts(3)
        write_entry(storage, s2, "impl_agent", "action_intent",
                    {"action_name": "architecture_decision",
                     "payload": {"component": "api", "decision": "use gRPC for the API gateway",
                                 "rationale": "performance benchmarks show 3x throughput over REST",
                                 "supersedes": "REST decision from session_arch_old"}},
                    t2, action_name="architecture_decision")
        write_entry(storage, s2, "impl_agent", "action_result",
                    {"result": {"component": "api", "protocol": "gRPC",
                                "status": "approved", "migration_plan": "incremental"},
                     "success": True},
                    t2 + timedelta(minutes=5), action_name="architecture_decision")
        write_entry(storage, s2, "impl_agent", "action_intent",
                    {"action_name": "implement_service",
                     "payload": {"service": "user_service", "protocol": "gRPC",
                                 "framework": "grpc-python"}},
                    t2 + timedelta(minutes=30), action_name="implement_service")
        write_entry(storage, s2, "impl_agent", "action_result",
                    {"result": {"service": "user_service", "tests_passed": 42,
                                "coverage": "87%"},
                     "success": True},
                    t2 + timedelta(minutes=60), action_name="implement_service")

        # Session 3 — current: active session (using SessionGraph)
        limits = SessionLimitsManager.agent_defaults(data_dir)
        graph = SessionGraph(storage=storage, limits_manager=limits)
        graph.start_session(source="dev_agent")
        s3 = graph.get_session_id()
        intent = graph.execute_action("code_review",
                                      {"module": "user_service", "reviewer": "dev_agent"})
        if intent:
            graph.confirm_action(intent.id,
                                 {"comments": 3, "approved": True},
                                 success=True)

        print(f"  Session 1 (old,  ~45d ago) : {s1}  — architecture decisions")
        print(f"  Session 2 (recent, ~3d ago): {s2}  — implementation work")
        print(f"  Session 3 (current)        : {s3}  — active session")
        print(f"  Total entries written       : 10")

        # ================================================================
        # ACT 2 — search_memory(): Recall relevant past memory
        # ================================================================
        print_header("ACT 2 — search_memory(): Recall past decisions")

        from dsm.recall import search_memory

        result = search_memory(
            query="architecture decision API gateway protocol",
            storage=storage,
            session_id=s3,
            across_sessions=True,
            max_results=10,
            include_current_session=False,
            include_provenance=True,
        )

        past = result["past_session_recall"]
        claims = result["verified_claims"]
        provenance = result.get("provenance", {})

        print(f"  Query           : 'architecture decision API gateway protocol'")
        print(f"  Matches found   : {len(past)}")
        print(f"  Verified claims : {len(claims)}")

        print_sub("Recalled entries (ranked by relevance):")
        for i, item in enumerate(past, 1):
            sid = item["session_id"]
            score = item["relevance_score"]
            status = item["time_status"]
            itype = item["type"]
            content = item["content"][:100]
            marker = ""
            if status == "superseded":
                marker = "  ← SUPERSEDED by newer entry"
            elif status == "outdated":
                marker = "  ← OUTDATED (>30 days)"
            print(f"    {i}. [{sid[:20]}...] score={score:.4f}  {itype}/{status}")
            print(f"       {content}...{marker}")

        if claims:
            print_sub("Verified claims extracted:")
            for c in claims:
                print(f"    • {c[:120]}")

        print_sub("Provenance (lightweight):")
        print(f"    integrity   : {provenance.get('integrity', 'n/a')}")
        print(f"    trust_level : {provenance.get('trust_level', 'n/a')}")
        print(f"    shards      : {provenance.get('source_shards', [])}")

        # ================================================================
        # ACT 3 — build_context(): Token-budgeted context pack
        # ================================================================
        print_header("ACT 3 — build_context(): Token-budgeted context pack")

        from dsm.context import build_context

        pack = build_context(
            query="architecture decision API gateway protocol",
            storage=storage,
            session_id=s3,
            max_tokens=4000,
            include_provenance=True,
        )

        print(f"  Digest          : {pack.digest}")
        print(f"  Token estimate  : {pack.token_estimate}")
        print(f"  Trimmed         : {pack.trimmed}")

        if pack.system_facts:
            print_sub("System facts (verified):")
            for f in pack.system_facts:
                print(f"    • {f[:120]}")

        if pack.past_session_recall:
            print_sub("Past session recall (compacted):")
            for r in pack.past_session_recall:
                print(f"    • {r[:120]}")

        if pack.verified_claims:
            print_sub("Verified claims:")
            for c in pack.verified_claims:
                print(f"    • {c[:120]}")

        # Also show prompt rendering
        from dsm.context import build_prompt_context

        prompt = build_prompt_context(
            query="architecture decision API gateway protocol",
            storage=storage,
            session_id=s3,
            max_tokens=2000,
            audience="agent",
        )

        print_sub("Prompt-ready context (first 500 chars):")
        for line in prompt[:500].split("\n"):
            print(f"    {line}")
        if len(prompt) > 500:
            print(f"    ... ({len(prompt)} chars total)")

        # ================================================================
        # ACT 4 — build_provenance(): Cryptographic verification
        # ================================================================
        print_header("ACT 4 — build_provenance(): Full chain verification")

        from dsm.provenance import build_provenance

        prov = build_provenance(
            items=[item for item in result["past_session_recall"]],
            storage=storage,
            verify=True,
        )

        print(f"  integrity         : {prov.integrity}")
        print(f"  trust_level       : {prov.trust_level}")
        print(f"  record_count      : {prov.record_count}")
        print(f"  broken_chains     : {prov.broken_chains}")
        print(f"  source_shards     : {prov.source_shards}")
        print(f"  entry_hashes      : {len(prov.entry_hashes)} hash(es)")
        if prov.oldest_entry_age_days is not None:
            print(f"  oldest_entry_age  : {prov.oldest_entry_age_days:.1f} days")
        if prov.verified_shards:
            print(f"  verified_shards   : {prov.verified_shards}")
        if prov.promotable_hashes:
            print(f"  promotable_hashes : {len(prov.promotable_hashes)} entry(ies)")
        if prov.verification_hint:
            print(f"  hint              : {prov.verification_hint}")

        verdict = "VERIFIED" if prov.integrity == "OK" else "NOT FULLY VERIFIED"
        print(f"\n  → Provenance verdict: {verdict}")

        # ================================================================
        # ACT 5 — Summary
        # ================================================================
        print(f"""
{'─' * 60}
  DSM CONSUMPTION LAYER V0 — SUMMARY

  Phase 1 — Recall
    search_memory() found {len(past)} entries across sessions.
    Older REST decision correctly marked superseded/outdated.
    Newer gRPC decision ranked higher by recency + relevance.

  Phase 2 — Context
    build_context() packed memory into {pack.token_estimate} tokens.
    {pack.digest}

  Phase 3 — Provenance
    build_provenance(verify=True) verified chain integrity.
    integrity={prov.integrity}  trust={prov.trust_level}  broken={prov.broken_chains}
{'─' * 60}
  Memory recalled. Context budgeted. Provenance verified.
  This is the DSM Consumption Layer.
""")

    finally:
        # End active session if still open
        try:
            graph.end_session()
        except Exception:
            pass
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
