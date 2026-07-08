#!/usr/bin/env python3
"""DCP v1.1 Conformance Test Suite.

Tests T1-T5 from the DCP v1.1 specification.
A provider passing T1-T5 may claim "DCP 1.1 Core Certified".

This suite is provider-agnostic: it tests ANY object that implements
the 5 DCP primitives with the correct signatures.
"""
import sys
import tempfile
import shutil
import json
from pathlib import Path

# Import the toy provider
sys.path.insert(0, str(Path(__file__).parent))
from provider import ToyDCPProvider


def run_conformance_suite(provider_factory, provider_name="toy_provider"):
    """Run the full DCP conformance suite against a provider.

    provider_factory: a callable that takes (data_dir) and returns
    a provider instance with the 5 DCP primitives.
    """
    results = {}

    print(f"{'='*60}")
    print(f"DCP v1.1 Conformance Suite — {provider_name}")
    print(f"{'='*60}")

    # === T1: join_project ===
    print(f"\n--- T1: join_project ---")
    tmp = Path(tempfile.mkdtemp(prefix="dcp_t1_"))
    try:
        p = provider_factory(str(tmp))
        ctx = p.join_project("test_project", agent_id="agent_A", owner_id="owner")
        t1_pass = (
            hasattr(ctx, "authorized") and ctx.authorized == True
            and hasattr(ctx, "project_exists") and ctx.project_exists == False
            and hasattr(ctx, "entry_count") and ctx.entry_count == 0
        )
        print(f"  join_project on empty project: authorized={ctx.authorized}, exists={ctx.project_exists}")
        results["T1_join_project"] = t1_pass
        print(f"  → {'PASS' if t1_pass else 'FAIL'}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # === T2: publish_receipt ===
    print(f"\n--- T2: publish_receipt ---")
    tmp = Path(tempfile.mkdtemp(prefix="dcp_t2_"))
    try:
        p = provider_factory(str(tmp))
        r = p.publish_receipt("test_project", "agent_A", "define", "Decision: build feature X")
        t2_pass = (
            hasattr(r, "entry_hash") and r.entry_hash.startswith("v1:")
            and hasattr(r, "agent_id") and r.agent_id == "agent_A"
            and hasattr(r, "receipt_hash") and len(r.receipt_hash) > 10
        )
        print(f"  receipt: entry_hash={r.entry_hash[:24]}..., agent={r.agent_id}")
        results["T2_publish_receipt"] = t2_pass
        print(f"  → {'PASS' if t2_pass else 'FAIL'}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # === T3: catch_up ===
    print(f"\n--- T3: catch_up (context reconstruction) ---")
    tmp = Path(tempfile.mkdtemp(prefix="dcp_t3_"))
    try:
        p = provider_factory(str(tmp))
        # Write 3 entries from 2 agents
        p.publish_receipt("proj", "agent_A", "define", "Define feature")
        p.publish_receipt("proj", "agent_B", "implement", "Implement feature")
        p.publish_receipt("proj", "agent_A", "test", "Test feature")

        ctx = p.catch_up("proj")
        t3_pass = (
            ctx.total_decisions == 3
            and ctx.integrity_ok == True
            and len(ctx.decisions) == 3
            and ctx.decisions[0]["agent"] == "agent_A"
            and ctx.decisions[2]["agent"] == "agent_A"
        )
        print(f"  catch_up: {ctx.total_decisions} decisions, integrity={ctx.integrity_status}")
        print(f"  agents seen: {set(d['agent'] for d in ctx.decisions)}")
        results["T3_catch_up"] = t3_pass
        print(f"  → {'PASS' if t3_pass else 'FAIL'}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # === T4: verify (integrity + tamper detection) ===
    print(f"\n--- T4: verify (tamper detection) ---")
    tmp = Path(tempfile.mkdtemp(prefix="dcp_t4_"))
    try:
        p = provider_factory(str(tmp))
        p.publish_receipt("proj", "agent_A", "define", "Decision A")
        p.publish_receipt("proj", "agent_B", "implement", "Decision B")

        # Verify clean
        ir_clean = p.verify("proj")
        print(f"  clean verify: {ir_clean.status}, {ir_clean.entry_count} entries")

        # Tamper: mutate the first entry's content
        family = "proj".replace("shard_", "")
        segs = sorted((tmp / "shards" / family).glob("*.jsonl"))
        lines = open(segs[0]).readlines()
        obj = json.loads(lines[0])
        obj["content"] = "TAMPERED CONTENT"
        lines[0] = json.dumps(obj, ensure_ascii=False) + "\n"
        open(segs[0], "w").writelines(lines)

        ir_tampered = p.verify("proj")
        print(f"  tampered verify: {ir_tampered.status}")

        t4_pass = (ir_clean.status == "OK" and ir_tampered.status == "TAMPERED")
        results["T4_verify"] = t4_pass
        print(f"  → {'PASS' if t4_pass else 'FAIL'}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # === T5: Hot Swap (multi-actor continuity) ===
    print(f"\n--- T5: Hot Swap (3-actor continuity) ---")
    tmp = Path(tempfile.mkdtemp(prefix="dcp_t5_"))
    try:
        p = provider_factory(str(tmp))

        # Actor 1 joins, works, publishes
        ctx1 = p.join_project("hotswap", "claude", "owner")
        r1 = p.publish_receipt("hotswap", "claude", "define", "Define: auth module")

        # Actor 2 joins, catches up, works
        ctx2 = p.join_project("hotswap", "zcode", "owner")
        saw_context = ctx2.context_bundle is not None and ctx2.context_bundle.get("total_decisions", 0) >= 1
        r2 = p.publish_receipt("hotswap", "zcode", "implement", "Implement: auth.py")

        # Actor 3 joins, catches up, sees both prior actors
        ctx3 = p.join_project("hotswap", "lmstudio", "owner")
        saw_both = ctx3.context_bundle is not None and ctx3.context_bundle.get("total_decisions", 0) >= 2
        r3 = p.publish_receipt("hotswap", "lmstudio", "review", "Review: looks good")

        # Final verification
        ir = p.verify("hotswap")
        catch_up_final = p.catch_up("hotswap")
        agents_in_final = set(d["agent"] for d in catch_up_final.decisions)

        t5_pass = (
            saw_context and saw_both
            and ir.status == "OK"
            and catch_up_final.total_decisions == 3
            and agents_in_final == {"claude", "zcode", "lmstudio"}
        )
        print(f"  3 actors: claude → zcode → lmstudio")
        print(f"  context propagated: actor2 saw {ctx2.entry_count} prior, actor3 saw {ctx3.entry_count} prior")
        print(f"  final: {catch_up_final.total_decisions} decisions, integrity={ir.status}")
        print(f"  agents in final context: {agents_in_final}")
        results["T5_hot_swap"] = t5_pass
        print(f"  → {'PASS' if t5_pass else 'FAIL'}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # === SUMMARY ===
    print(f"\n{'='*60}")
    print("CONFORMANCE SUMMARY")
    print(f"{'='*60}")
    all_pass = True
    for test, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {test:25} {status}")
        all_pass &= passed

    print(f"\n  {'DCP 1.1 Core Certified' if all_pass else 'NOT CERTIFIED — failing tests above'}")
    return all_pass


if __name__ == "__main__":
    run_conformance_suite(
        provider_factory=lambda data_dir: ToyDCPProvider(data_dir),
        provider_name="ToyDCPProvider (specification-only implementation)"
    )
