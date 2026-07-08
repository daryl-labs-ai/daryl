#!/usr/bin/env python3
"""OrchestratedMemory Axe 3+4 — Reprise après interruption + Audit.

Axe 3: Un agent travaille pendant des heures. Le process est tué.
       Au redémarrage, peut-il reconstruire son propre contexte?
       Mesure: combien d'entries sont récupérées, à quelle vitesse,
       et avec quelle complétude (attribution, timestamps, actions).

Axe 4: Après une session multi-agents, peut-on retrouver:
       - qui a écrit quoi (attribution)
       - quand (temporalité)
       - quelle action (action_name)
       - dans quel ordre (séquence)

       Et l'orchestrator_audit shard contient-elle les décisions
       d'admission (allow/deny) avec leur raison?
"""
from __future__ import annotations
import shutil, sys, tempfile, time, json
from datetime import datetime, timezone, timedelta
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


def make_entry(agent_id, i, content, action, ts_offset_min=0):
    ts = datetime.now(timezone.utc) - timedelta(minutes=ts_offset_min)
    return Entry(
        id=f"{agent_id}_h{i:04d}", timestamp=ts,
        session_id=f"sess_{agent_id}", source=agent_id,
        content=content, shard="private",
        hash="", prev_hash=None,
        metadata={"event_type": "tool_call", "action_name": action},
        version="v2.0",
    )


def setup_stack(tmp):
    storage = Storage(data_dir=str(tmp))
    identity = IdentityRegistry(storage=storage)
    policy = SovereigntyPolicy(storage=storage)
    orch = NeutralOrchestrator(storage=storage, rules=RuleSet.default(),
                                identity=identity, policy=policy)
    lanes = LaneGroup(storage, identity, policy, orch)
    return storage, identity, policy, orch, lanes


def register_with_policy(identity, policy, lanes, agent_ids, owner="owner"):
    for aid in agent_ids:
        identity.register(agent_id=aid, public_key=f"pk_{aid}",
                          owner_id=owner, owner_signature=f"sig_{owner}", model="m")
        lanes.register_lane(aid)
    policy.set(owner_id=owner, owner_signature=f"sig_{owner}",
               policy={"agents": list(agent_ids), "min_trust_score": 0.3,
                       "allowed_types": ["decision", "tool_call", "observation", "action_result"],
                       "approval_required": [], "cross_ai": True})


def main():
    tmp = Path(tempfile.mkdtemp(prefix="om34_"))
    try:
        storage, identity, policy, orch, lanes = setup_stack(tmp)
        register_with_policy(identity, policy, lanes, ["agent_A", "agent_B", "agent_C"])

        # === Simulate hours of work: 3 agents, 50 entries each, spread over 8 hours ===
        print("=" * 80)
        print("AXE 3+4 — REPRISE APRÈS INTERRUPTION + AUDIT")
        print("=" * 80)
        print()
        actions = ["write_file", "edit", "test", "review", "deploy", "debug", "refactor"]
        contents = ["Implement auth module", "Fix bug in parser", "Add unit tests",
                    "Review PR #42", "Deploy v1.2", "Debug memory leak",
                    "Refactor storage layer", "Update docs", "Optimize query"]

        # Agent A: morning (8h ago), Agent B: afternoon (4h ago), Agent C: now
        for agent, hours_ago in [("agent_A", 480), ("agent_B", 240), ("agent_C", 0)]:
            entries = []
            for i in range(50):
                content = f"{contents[i % len(contents)]} (step {i})"
                action = actions[i % len(actions)]
                entries.append(make_entry(agent, i, content, action, ts_offset_min=hours_ago + i))
            def summary_fn(e): return e.content[:50]
            def detail_fn(e): return (f"Detail: {e.content}", [])
            lanes.push(agent, "owner", entries, summary_fn=summary_fn, detail_fn=detail_fn)

        print(f"=== Setup: 3 agents × 50 entries = 150 entries sur 8h ===")
        print()

        # === AXE 3: Reprise — kill, restart, reconstruct ===
        print(f"=== AXE 3: REPRISE APRÈS KILL ===")
        # Simulate process death: rebuild stack from same storage
        storage2, identity2, policy2, orch2, lanes2 = setup_stack(tmp)
        register_with_policy(identity2, policy2, lanes2, ["agent_A", "agent_B", "agent_C"])

        t0 = time.monotonic()
        recent = lanes2.recent(limit=200)
        reconstruct_time = time.monotonic() - t0

        n = len(recent)
        agents_found = set()
        actions_found = set()
        for r in recent:
            if isinstance(r, dict):
                agents_found.add(r.get("agent_id", "?"))
                actions_found.add(r.get("action_type", "?"))
            else:
                agents_found.add(getattr(r, "agent_id", "?"))
                actions_found.add(getattr(r, "action_type", "?"))

        print(f"  entries récupérées: {n}/150")
        print(f"  agents distincts:   {len(agents_found)} ({sorted(agents_found)})")
        print(f"  action_types:       {len(actions_found)} distincts")
        print(f"  temps:              {reconstruct_time*1000:.1f} ms")
        print()

        # === AXE 4: Audit — who/what/when/why ===
        print(f"=== AXE 4: AUDIT ===")
        # 4a. Attribution: who wrote what?
        per_agent = {}
        for r in recent:
            agent = r.get("agent_id") if isinstance(r, dict) else getattr(r, "agent_id", "?")
            per_agent[agent] = per_agent.get(agent, 0) + 1
        print(f"  Attribution (entries par agent):")
        for agent, count in sorted(per_agent.items()):
            print(f"    {agent}: {count} entries")
        print()

        # 4b. Temporalité: when?
        timestamps = []
        for r in recent:
            ts = r.get("contributed_at") if isinstance(r, dict) else getattr(r, "contributed_at", None)
            if ts: timestamps.append(str(ts))
        if timestamps:
            print(f"  Temporalité: {min(timestamps)[:19]} → {max(timestamps)[:19]}")
        print()

        # 4c. Orchestrator audit trail
        audit_entries = storage2.read("orchestrator_audit", limit=1000)
        print(f"  Orchestrator audit shard: {len(audit_entries)} décisions d'admission")
        if audit_entries:
            allows = 0; denies = 0
            reasons = {}
            for e in audit_entries:
                try:
                    d = json.loads(e.content)
                    verdict = d.get("verdict", "?")
                    reason = d.get("reason", "?")
                    if verdict == "allow": allows += 1
                    else: denies += 1
                    reasons[reason] = reasons.get(reason, 0) + 1
                except Exception:
                    pass
            print(f"    allows={allows}  denies={denies}")
            print(f"    top reasons: {dict(sorted(reasons.items(), key=lambda x:-x[1])[:3])}")
        print()

        # 4d. Replay exactness: can we replay the full sequence?
        # The private shards contain the full entries (collective has projections)
        print(f"  Replay capability (private shards):")
        for agent in ["agent_A", "agent_B", "agent_C"]:
            private_entries = storage2.read(f"private", limit=1000)
            agent_entries = [e for e in private_entries if e.source == agent]
            print(f"    {agent}: {len(agent_entries)} entries in private shard")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
