#!/usr/bin/env python3
"""OrchestratedMemory Axe 6 — Panne: kill/restart autour des writes.

Scénarios de panne:
  P1. Crash MID-PUSH: agent pousse 100 entries, mais le process est tué
      après 50. Au restart, que reste-t-il? Y a-t-il des doublons si on retry?
  P2. Crash après admission mais avant write: l'orchestrator_audit a loggé
      "allow" mais l'entry collective n'a pas été écrite. Incohérence?
  P3. Crash du storage (segment corrompu): peut-on lire ce qui a survécu?
  P4. Retry idempotent: re-pousser les mêmes entries crée-t-il des doublons?
"""
from __future__ import annotations
import json, shutil, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "packages" / "dsm-primitives" / "src"))

from dsm.core.storage import Storage
from dsm.core.models import Entry
from dsm.identity.identity_registry import IdentityRegistry
from dsm.orchestrator import NeutralOrchestrator, RuleSet
from dsm.sovereignty import SovereigntyPolicy
from dsm.lanes import LaneGroup


def make_entry(agent_id, i):
    return Entry(
        id=f"{agent_id}_f{i:04d}", timestamp=datetime.now(timezone.utc),
        session_id=f"sess_{agent_id}", source=agent_id,
        content=f"failure-test entry {i}", shard="private",
        hash="", prev_hash=None,
        metadata={"event_type": "tool_call", "action_name": f"act_{i%5}"},
        version="v2.0",
    )


def setup_stack(tmp, agent_ids):
    storage = Storage(data_dir=str(tmp))
    identity = IdentityRegistry(storage=storage)
    policy = SovereigntyPolicy(storage=storage)
    orch = NeutralOrchestrator(storage=storage, rules=RuleSet.default(),
                                identity=identity, policy=policy)
    lanes = LaneGroup(storage, identity, policy, orch)
    for aid in agent_ids:
        identity.register(agent_id=aid, public_key=f"pk_{aid}",
                          owner_id="owner", owner_signature="sig", model="m")
        lanes.register_lane(aid)
    policy.set(owner_id="owner", owner_signature="sig",
               policy={"agents": list(agent_ids), "min_trust_score": 0.3,
                       "allowed_types": ["tool_call"], "approval_required": [], "cross_ai": True})
    return storage, orch, lanes


def main():
    print("=" * 80)
    print("AXE 6 — PANNE: kill/restart autour des writes")
    print("=" * 80)
    print()

    # === P1: Crash mid-push ===
    print("=== P1: CRASH MID-PUSH (50/100 written, then kill) ===")
    tmp = Path(tempfile.mkdtemp(prefix="om6_p1_"))
    try:
        storage, orch, lanes = setup_stack(tmp, ["agent_A"])
        entries = [make_entry("agent_A", i) for i in range(100)]
        # Simulate: push first 50, then "crash" (don't push the rest)
        first_half = entries[:50]
        lanes.push("agent_A", "owner", first_half,
                   summary_fn=lambda e: e.content[:30], detail_fn=lambda e: (e.content[:40], []))
        # "Crash" — process dies here. Restart:
        storage2, orch2, lanes2 = setup_stack(tmp, ["agent_A"])
        recent = lanes2.recent(limit=200)
        print(f"  après crash+restart: {len(recent)} entries survived (expected 50)")
        print(f"  → {'OK' if len(recent) == 50 else 'DATA LOSS or DOUBLES'}")
        print()

        # === P4: Retry idempotent? Re-push the same 50 ===
        print("=== P4: RETRY IDEMPOTENT (re-push same 50 entries) ===")
        lanes2.push("agent_A", "owner", first_half,
                    summary_fn=lambda e: e.content[:30], detail_fn=lambda e: (e.content[:40], []))
        recent_after_retry = lanes2.recent(limit=200)
        print(f"  après retry: {len(recent_after_retry)} entries (expected 50 if idempotent, 100 if not)")
        print(f"  → {'IDEMPOTENT' if len(recent_after_retry) == 50 else 'NOT IDEMPOTENT — DOUBLES created'}")
        print()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # === P2: Admission logged but entry not written ===
    print("=== P2: ADMISSION LOGGED BUT COLLECTIVE NOT WRITTEN ===")
    tmp = Path(tempfile.mkdtemp(prefix="om6_p2_"))
    try:
        storage, orch, lanes = setup_stack(tmp, ["agent_A"])
        e = make_entry("agent_A", 0)
        # Admit only (no push) — simulates crash between admit and write
        result = orch.admit(e, "agent_A", "owner")
        print(f"  admit verdict: {result.verdict}")
        # Check: orchestrator_audit has the decision
        audit = storage.read("orchestrator_audit", limit=10)
        print(f"  orchestrator_audit entries: {len(audit)} (decision logged)")
        # Check: collective has the entry?
        recent = lanes.recent(limit=10)
        print(f"  collective entries: {len(recent)} (entry NOT written)")
        if len(audit) > 0 and len(recent) == 0:
            print(f"  → INCONSISTENCY: audit says 'allow' but collective is empty")
            print(f"    → Crash window between admit() and push() leaves audit trail")
            print(f"      without corresponding collective entry")
        print()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # === P3: Segment corruption ===
    print("=== P3: SEGMENT CORRUPTION (truncate last line) ===")
    tmp = Path(tempfile.mkdtemp(prefix="om6_p3_"))
    try:
        storage, orch, lanes = setup_stack(tmp, ["agent_A"])
        entries = [make_entry("agent_A", i) for i in range(20)]
        lanes.push("agent_A", "owner", entries,
                   summary_fn=lambda e: e.content[:30], detail_fn=lambda e: (e.content[:40], []))
        # Corrupt: truncate the collective lane shard's last line
        lane_shard = "collective_lane_agent_A"
        family = lane_shard.replace("shard_", "")
        segs = sorted((tmp / "shards" / family).glob("*.jsonl"))
        if segs:
            with open(segs[-1], "r") as f:
                lines = f.readlines()
            # Corrupt last line (write half a JSON)
            if len(lines) > 1:
                lines[-1] = lines[-1][:len(lines[-1])//2]
            with open(segs[-1], "w") as f:
                f.writelines(lines)
            # Try to read after corruption
            recent = lanes.recent(limit=50)
            print(f"  entries après corruption: {len(recent)} (expected ~19, one corrupted)")
            print(f"  → {'OK — corruption contained' if 15 <= len(recent) <= 19 else 'BROKEN — mass loss'}")
        print()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
