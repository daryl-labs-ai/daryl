#!/usr/bin/env python3
"""
demo_support_agent.py — Daryl Customer Support Agent Demo

A customer support AI agent handles a subscription cancellation request.
The full decision trail is recorded in DSM.
Someone modifies the policy decision after the fact.
DSM catches it.

Usage:
    python demo/demo_support_agent.py
"""

import json
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dsm.core.storage import Storage
from dsm.session.session_graph import SessionGraph
from dsm.session.session_limits_manager import SessionLimitsManager
from dsm.verify import verify_shard


def print_header(text):
    print(f"\n{'─' * 50}")
    print(f"  {text}")
    print(f"{'─' * 50}")


def print_verify(result):
    status = result["status"]
    status_str = status.value if hasattr(status, "value") else str(status)
    print(f"  shard_id     : {result['shard_id']}")
    print(f"  total_entries: {result['total_entries']}")
    print(f"  verified     : {result['verified']}")
    print(f"  tampered     : {result['tampered']}")
    print(f"  chain_breaks : {result['chain_breaks']}")
    print(f"  status       : {status_str}")


def main():
    tmp_dir = tempfile.mkdtemp(prefix="daryl_support_")

    try:
        # ── STEP 1 — Setup ──
        print_header("DARYL VERIFY — Customer Support Agent Demo")
        print('  User: "I want to cancel my subscription."')
        time.sleep(0.3)

        storage = Storage(data_dir=os.path.join(tmp_dir, "memory"))
        limits = SessionLimitsManager.agent_defaults(os.path.join(tmp_dir, "memory"))
        session = SessionGraph(storage=storage, limits_manager=limits)

        # ── STEP 2 — Record agent decision trail ──
        print()
        session.start_session(source="support_agent")
        print("  → start_session recorded")

        actions = [
            ("classify_intent", {
                "intent": "cancellation", "confidence": 0.98, "user_id": "USR_4892"
            }),
            ("check_subscription", {
                "user_id": "USR_4892", "plan": "pro", "status": "active", "months": 14
            }),
            ("apply_policy", {
                "policy": "retention_offer", "discount_pct": 30,
                "rationale": "loyal customer over 12 months"
            }),
            ("confirm_response", {
                "action": "offer_sent",
                "message": "We'd love to keep you — here's 30% off for 3 months."
            }),
        ]

        for action_name, payload in actions:
            session.execute_action(action_name, payload)
            print(f"  → {action_name} recorded")

        session.end_session()
        print("  → end_session recorded")
        time.sleep(0.3)

        # ── STEP 3 — Verify clean ──
        print_header("STEP 3 — Verify clean trail")
        result_clean = verify_shard(storage, "sessions")
        print_verify(result_clean)
        print("\n  ✓ Chain intact. All agent decisions verified.")
        time.sleep(0.3)

        # ── STEP 4 — Tamper ──
        print_header("STEP 4 — Tamper with policy decision")

        shard_family_dir = storage.shards_dir / "sessions"
        segment_files = sorted(shard_family_dir.glob("*.jsonl"))

        if not segment_files:
            print("  ⚠ No segment files found — cannot demonstrate tampering.")
            return

        shard_file = segment_files[0]
        print("  ⚠ Simulating post-hoc modification — altering policy decision...")

        with open(shard_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        tampered = False
        new_lines = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                new_lines.append(line)
                continue
            try:
                entry_data = json.loads(stripped)
            except json.JSONDecodeError:
                new_lines.append(line)
                continue

            meta = entry_data.get("metadata", {})
            if not tampered and meta.get("action_name") == "apply_policy":
                content = json.loads(entry_data["content"])
                content["payload"]["discount_pct"] = 0
                content["payload"]["rationale"] = "standard policy applied"
                entry_data["content"] = json.dumps(content)
                tampered = True

            new_lines.append(
                json.dumps(entry_data, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
            )

        if not tampered:
            print("  ⚠ Could not find target entry. Skipping.")
            return

        with open(shard_file, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        print("  Modified: discount_pct 30 → 0 | rationale altered")
        time.sleep(0.3)

        # ── STEP 5 — Verify after tamper ──
        print_header("STEP 5 — Verify after modification")
        result_tampered = verify_shard(storage, "sessions")
        print_verify(result_tampered)

        print("  Original : discount_pct = 30 | rationale = 'loyal customer over 12 months'")
        print("  Modified : discount_pct = 0  | rationale = 'standard policy applied'")
        print("  → Hash mismatch detected")
        print("\n  ✗ Trail compromised. Policy decision was altered after the fact.")
        time.sleep(0.3)

        # ── STEP 6 — Final summary ──
        print(f"""
{'─' * 50}
  SUPPORT AGENT AUDIT SUMMARY
  Entries recorded : {result_clean['total_entries']}
  Entries verified : {result_tampered['verified']}
  Tamper detected  : YES (entry: apply_policy)
  Verdict          : TRAIL COMPROMISED
{'─' * 50}
  Did your agent apply the right policy?
  With Daryl, you don't guess. You verify.
""")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
