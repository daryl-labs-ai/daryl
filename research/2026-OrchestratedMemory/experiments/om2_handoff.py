#!/usr/bin/env python3
"""OrchestratedMemory Axe 2 — Handoff: B reprend A depuis DSM.

Scénario:
  Agent A travaille: 5 décisions, chacune avec un rationale et un résultat.
  A pousse tout dans sa lane collective (projections).
  Agent A "quitte" (process meurt, état mémoire perdu).
  Agent B "arrive" (nouveau process, nouveau LaneGroup, lit depuis le même storage).
  B doit reconstruire: que décida A, dans quel ordre, sur quelle preuve.

Mesures:
  - exactitude: B récupère-t-il les 5 décisions dans l'ordre?
  - complétude: chaque décision a-t-elle son summary + detail + key_findings?
  - timing: temps de reconstruction
  - propriété: peut B attribuer chaque décision à A?
"""
from __future__ import annotations
import shutil, sys, tempfile, time
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


def make_entry(agent_id, i, content, action):
    return Entry(
        id=f"{agent_id}_d{i:03d}", timestamp=datetime.now(timezone.utc),
        session_id=f"sess_{agent_id}", source=agent_id,
        content=content, shard="private",
        hash="", prev_hash=None,
        metadata={"event_type": "decision", "action_name": action},
        version="v2.0",
    )


def setup_orchestrated_stack(tmp):
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
                          owner_id=owner, owner_signature=f"sig_{owner}",
                          model="test-model")
        lanes.register_lane(aid)
    policy.set(owner_id=owner, owner_signature=f"sig_{owner}",
               policy={"agents": list(agent_ids), "min_trust_score": 0.3,
                       "allowed_types": ["decision", "observation", "tool_call", "action_result"],
                       "approval_required": [], "cross_ai": True})


def main():
    tmp = Path(tempfile.mkdtemp(prefix="om2_"))
    try:
        # === Agent A works ===
        storage, identity, policy, orch, lanes = setup_orchestrated_stack(tmp)
        register_with_policy(identity, policy, lanes, ["agent_A", "agent_B"])

        decisions_A = [
            ("Refactor auth module to use Ed25519", "refactor"),
            ("Fix race condition in session.py:147", "bugfix"),
            ("Add test coverage for hash perimeter", "test"),
            ("Decide: use blake3 in v2 hash (deferred)", "decision"),
            ("Document ADR-0002 entry schema", "docs"),
        ]
        entries_A = [make_entry("agent_A", i, c, a) for i, (c, a) in enumerate(decisions_A)]

        def summary_fn(e): return e.content[:60]
        def detail_fn(e): return (f"Detailed rationale for: {e.content}", [f"finding_{e.id}"])

        t0 = time.monotonic()
        result = lanes.push("agent_A", "owner", entries_A,
                            summary_fn=summary_fn, detail_fn=detail_fn)
        push_time = time.monotonic() - t0
        print("=" * 80)
        print("AXE 2 — HANDOFF: B reprend A depuis DSM")
        print("=" * 80)
        print()
        print(f"=== Agent A a travaillé ===")
        print(f"  {len(entries_A)} décisions poussées")
        print(f"  admitted={len(result.admitted)} rejected={len(result.rejected)}")
        print(f"  push time: {push_time*1000:.1f} ms")
        print(f"  Agent A quitte (state perdu).")
        print()

        # === Agent B arrives: NEW stack, SAME storage ===
        # Simulate a new process: rebuild everything from disk
        storage2, identity2, policy2, orch2, lanes2 = setup_orchestrated_stack(tmp)
        register_with_policy(identity2, policy2, lanes2, ["agent_A", "agent_B"])

        print(f"=== Agent B arrive (nouveau process, même storage) ===")
        t0 = time.monotonic()
        # B reads the collective memory to reconstruct A's work
        recent = lanes2.recent(limit=100)
        reconstruct_time = time.monotonic() - t0

        print(f"  lanes.recent(limit=100) → {len(recent)} entries en {reconstruct_time*1000:.1f} ms")
        print()

        # === Verify reconstruction ===
        # recent() returns CollectiveEntry dataclass objects; handle both shapes.
        print(f"=== Reconstruction par B ===")
        recovered_decisions = []
        attribution_ok = True
        completeness_ok = True

        for r in recent:
            if isinstance(r, dict):
                agent = r.get("agent_id", "?")
                summary = r.get("summary", "")
                detail = r.get("detail", "")
                findings = r.get("key_findings", [])
                ts = r.get("contributed_at", "?")
            else:  # CollectiveEntry dataclass
                agent = getattr(r, "agent_id", "?")
                summary = getattr(r, "summary", "")
                detail = getattr(r, "detail", "")
                findings = getattr(r, "key_findings", ())
                ts = getattr(r, "contributed_at", "?")

            if agent != "agent_A":
                attribution_ok = False
            if not summary or not detail:
                completeness_ok = False
            recovered_decisions.append((agent, summary, detail, len(findings), ts))

        print(f"  Décisions reconstruites: {len(recovered_decisions)}")
        for i, (agent, summary, detail, nfind, ts) in enumerate(recovered_decisions):
            print(f"    [{i}] agent={agent} summary=\"{summary[:40]}...\" findings={nfind}")
        print()

        # Compare to original
        correct_order = True
        if len(recovered_decisions) == len(decisions_A):
            for i, ((agent, summary, _, _, _), (orig_content, _)) in enumerate(zip(recovered_decisions, decisions_A)):
                if orig_content[:40] not in summary:
                    correct_order = False
                    print(f"  ORDER MISMATCH at [{i}]: expected '{orig_content[:40]}' got '{summary[:40]}'")

        print(f"=== Mesures ===")
        print(f"  décisions attendues:     {len(decisions_A)}")
        print(f"  décisions reconstruites: {len(recovered_decisions)}")
        print(f"  ordre correct:           {correct_order}")
        print(f"  attribution à A correcte:{attribution_ok}")
        print(f"  complétude (sum+detail): {completeness_ok}")
        print(f"  temps de reconstruction: {reconstruct_time*1000:.1f} ms")
        print()
        all_ok = (len(recovered_decisions) == len(decisions_A) and correct_order
                  and attribution_ok and completeness_ok)
        if all_ok:
            print(f"  → HANDOFF RÉUSSI: B reconstruit intégralement le travail de A depuis DSM")
        else:
            print(f"  → HANDOFF PARTIEL/ÉCHEC: voir mesures ci-dessus")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
