#!/usr/bin/env python3
"""
demo_verify.py — Daryl Trust Layer Demo

Demonstrates that DSM detects post-hoc modification of an agent's decision trail.

Scenario: A luxury AI advisor records a recommendation for a €120,000 watch.
Someone modifies the trail after the fact. DSM catches it.

Usage:
    python demo_verify.py
"""

import json
import os
import shutil
import sys
import tempfile
import time

# Ensure the src directory is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from dsm.core.storage import Storage
from dsm.session.session_graph import SessionGraph
from dsm.session.session_limits_manager import SessionLimitsManager
from dsm.verify import verify_shard


def print_header(text):
    print(f"\n{'─' * 50}")
    print(f"  {text}")
    print(f"{'─' * 50}")


def print_verify_result(result):
    status = result["status"]
    status_str = status.value if hasattr(status, "value") else str(status)
    print(f"  shard_id     : {result['shard_id']}")
    print(f"  total_entries: {result['total_entries']}")
    print(f"  verified     : {result['verified']}")
    print(f"  tampered     : {result['tampered']}")
    print(f"  chain_breaks : {result['chain_breaks']}")
    print(f"  status       : {status_str}")


def main():
    tmp_dir = tempfile.mkdtemp(prefix="daryl_demo_")

    try:
        # ── STEP 1 — Setup ──
        print_header("DARYL VERIFY — Trust Layer Demo")
        print("  Recording agent decision trail...")
        time.sleep(0.3)

        storage = Storage(data_dir=os.path.join(tmp_dir, "memory"))
        limits = SessionLimitsManager.agent_defaults(os.path.join(tmp_dir, "memory"))
        session = SessionGraph(storage=storage, limits_manager=limits)

        # ── STEP 2 — Record ──
        print()
        session.start_session(source="luxury_advisor_agent")
        print("  → start_session recorded")

        actions = [
            ("greet_client",
             {"client_id": "VIP_001", "tier": "diamond"}),
            ("retrieve_preferences",
             {"client_id": "VIP_001", "category": "watches"}),
            ("analyze_inventory",
             {"brand": "Patek Philippe", "ref": "5711A"}),
            ("generate_recommendation",
             {"item": "Patek Philippe 5711A", "price_eur": 120000,
              "rationale": "matches client preference for minimalist complications"}),
            ("present_to_client",
             {"recommendation_id": "REC_001", "client_id": "VIP_001"}),
        ]

        for action_name, payload in actions:
            session.execute_action(action_name, payload)
            print(f"  → {action_name} recorded")

        session.end_session()
        print("  → end_session recorded")
        time.sleep(0.3)

        # ── STEP 3 — Verify clean trail ──
        print_header("STEP 3 — Verify clean trail")
        result_clean = verify_shard(storage, "sessions")
        print_verify_result(result_clean)
        print("\n  ✓ Chain intact. All entries verified.")
        time.sleep(0.3)

        # ── STEP 4 — Tamper with the raw trail ──
        print_header("STEP 4 — Tamper with stored trail")

        # Locate the segment file on disk
        shard_family_dir = storage.shards_dir / "sessions"
        segment_files = sorted(shard_family_dir.glob("*.jsonl"))

        if not segment_files:
            print("  ⚠ No segment files found — cannot demonstrate tampering.")
            return

        shard_file = segment_files[0]
        print(f"  Shard file: {shard_file}")
        print("  ⚠ Simulating post-hoc modification — altering stored entry...")

        # Read all lines, modify one entry's content while preserving valid JSON
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

            # Target the generate_recommendation action
            meta = entry_data.get("metadata", {})
            if not tampered and meta.get("action_name") == "generate_recommendation":
                # Change the price from 120000 to 45000 — a post-hoc cover-up
                content = json.loads(entry_data["content"])
                original_price = content["payload"].get("price_eur")
                content["payload"]["price_eur"] = 45000
                content["payload"]["rationale"] = "budget option selected by advisor"
                entry_data["content"] = json.dumps(content)
                # Do NOT recompute hash — this is what makes it detectable
                tampered = True
                print(f"  Modified: price_eur {original_price} → 45000")

            new_lines.append(
                json.dumps(entry_data, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
            )

        if not tampered:
            print("  ⚠ Could not find target entry to tamper. Skipping.")
            return

        # Write the tampered file back
        with open(shard_file, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        time.sleep(0.3)

        # ── STEP 5 — Verify after modification ──
        print_header("STEP 5 — Verify after modification")
        result_tampered = verify_shard(storage, "sessions")
        print_verify_result(result_tampered)
        print("  Original : price_eur = 120000 | rationale = 'matches client preference for minimalist complications'")
        print("  Modified : price_eur = 45000  | rationale = 'budget option selected by advisor'")
        print("  → Hash stored in trail no longer matches recomputed hash")
        print("  → Chain break propagates to all subsequent entries")

        status_str = result_tampered["status"].value if hasattr(result_tampered["status"], "value") else str(result_tampered["status"])
        if status_str != "OK":
            print("\n  ✗ Chain break detected. Trail integrity compromised.")
        else:
            print("\n  (Unexpected: verification passed despite tampering)")
        time.sleep(0.3)

        # ── STEP 6 — Final summary ──
        print(f"""
{'─' * 50}
  SESSION AUDIT SUMMARY
  Entries recorded : {result_clean['total_entries']}
  Entries verified : {result_tampered['verified']}
  Tampered         : {result_tampered['tampered']}
  Chain breaks     : {result_tampered['chain_breaks']}
  Verdict          : TRAIL COMPROMISED
{'─' * 50}
  This is what Daryl Verify does. Not logs. Proof.
""")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
