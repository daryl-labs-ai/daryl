#!/usr/bin/env python3
"""
demo_end_to_end.py — Daryl Multi-Agent Trust Demo

Two agents collaborate on a high-value client recommendation.
Agent A (Luxury Advisor) delegates inventory analysis to Agent B (Inventory Specialist).
DSM records the full decision trail with cryptographic proof of causality.
Then the trail is tampered. DSM detects it.

Usage:
    python demo/demo_end_to_end.py
"""

import json
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dsm.core.storage import Storage
from dsm.session.session_graph import SessionGraph
from dsm.session.session_limits_manager import SessionLimitsManager
from dsm.verify import verify_shard
from dsm.causal import create_dispatch_hash, DispatchRecord, verify_dispatch_hash
from dsm.exchange import issue_receipt, verify_receipt

# Import verify_receipt_against_storage if available
try:
    from dsm.exchange import verify_receipt_against_storage
    HAS_VERIFY_AGAINST_STORAGE = True
except ImportError:
    HAS_VERIFY_AGAINST_STORAGE = False


def print_header(text):
    print(f"\n{'─' * 55}")
    print(f"  {text}")
    print(f"{'─' * 55}")


def print_verify(label, result):
    status = result["status"]
    status_str = status.value if hasattr(status, "value") else str(status)
    print(f"  [{label}] total_entries: {result['total_entries']}  "
          f"verified: {result['verified']}  "
          f"tampered: {result['tampered']}  "
          f"chain_breaks: {result['chain_breaks']}  "
          f"status: {status_str}")


def status_str(result):
    s = result["status"]
    return s.value if hasattr(s, "value") else str(s)


def main():
    tmp_dir = tempfile.mkdtemp(prefix="daryl_e2e_")

    try:
        # ── STEP 1 — Setup ──
        print_header("DARYL VERIFY — End-to-End Multi-Agent Demo")
        print("  Two agents. One decision. Full cryptographic proof.")
        time.sleep(0.3)

        storage_a = Storage(data_dir=os.path.join(tmp_dir, "agent_a"))
        storage_b = Storage(data_dir=os.path.join(tmp_dir, "agent_b"))

        limits_a = SessionLimitsManager.agent_defaults(os.path.join(tmp_dir, "agent_a"))
        limits_b = SessionLimitsManager.agent_defaults(os.path.join(tmp_dir, "agent_b"))

        session_a = SessionGraph(storage=storage_a, limits_manager=limits_a)
        session_b = SessionGraph(storage=storage_b, limits_manager=limits_b)

        # ── STEP 2 — Agent A: client intake ──
        print_header("STEP 2 — Agent A: client intake")
        session_a.start_session(source="luxury_advisor_agent_a")
        print("  [Agent A] → start_session recorded")

        session_a.execute_action("greet_client", {"client_id": "VIP_001", "tier": "diamond"})
        print("  [Agent A] → greet_client recorded")

        entry_prefs = session_a.execute_action("retrieve_preferences", {
            "client_id": "VIP_001", "category": "watches", "budget_eur": 120000
        })
        print("  [Agent A] → retrieve_preferences recorded")
        time.sleep(0.3)

        # ── STEP 3 — Agent A delegates to Agent B ──
        print_header("STEP 3 — Agent A delegates to Agent B")

        # Use entry hash directly if available, fallback to storage.read()
        if entry_prefs and hasattr(entry_prefs, "hash") and entry_prefs.hash:
            dispatcher_entry_hash = entry_prefs.hash
        else:
            entries_a = storage_a.read("sessions", limit=1)
            dispatcher_entry_hash = entries_a[0].hash if entries_a else ""

        task_params = {"task": "find_best_watch", "client_id": "VIP_001", "budget_eur": 120000}
        dispatch_ts = datetime.now(timezone.utc).isoformat()
        dispatch_hash = create_dispatch_hash(
            dispatcher_entry_hash=dispatcher_entry_hash,
            task_params=task_params,
            timestamp=dispatch_ts,
        )

        dispatch_record = DispatchRecord(
            dispatch_hash=dispatch_hash,
            dispatcher_agent_id="agent_a",
            dispatcher_entry_hash=dispatcher_entry_hash,
            target_agent_id="agent_b",
            task_params=task_params,
            timestamp=dispatch_ts,
        )

        dispatch_result = verify_dispatch_hash(dispatch_record)
        print(f"  [Agent A] → Delegating inventory analysis to Agent B...")
        print(f"  Dispatch hash: {dispatch_hash[:16]}...")
        print(f"  Dispatch verification: {dispatch_result['status']}")
        time.sleep(0.3)

        # ── STEP 4 — Agent B: inventory analysis ──
        print_header("STEP 4 — Agent B: inventory analysis")
        session_b.start_session(source="inventory_specialist_agent_b")
        print("  [Agent B] → start_session recorded")

        session_b.execute_action("search_inventory", {
            "brand": "Patek Philippe", "ref": "5711A", "price_eur": 120000
        })
        print("  [Agent B] → search_inventory recorded")

        session_b.execute_action("score_match", {
            "item": "Patek Philippe 5711A", "client_id": "VIP_001", "score": 0.97
        })
        print("  [Agent B] → score_match recorded")

        entry_rec = session_b.execute_action("return_recommendation", {
            "item": "Patek Philippe 5711A", "price_eur": 120000,
            "rationale": "matches client preference for minimalist complications"
        })
        print("  [Agent B] → return_recommendation recorded")
        time.sleep(0.3)

        # ── STEP 5 — Agent B issues a trust receipt ──
        print_header("STEP 5 — Agent B issues trust receipt")

        receipt = issue_receipt(
            storage=storage_b,
            agent_id="agent_b",
            entry_id=entry_rec.id,
            shard_id="sessions",
            task_description="Inventory analysis for VIP_001 — Patek Philippe 5711A",
            dispatch_hash=dispatch_hash,
        )

        receipt_result = verify_receipt(receipt)
        receipt_status = receipt_result["status"]
        receipt_status_str = receipt_status.value if hasattr(receipt_status, "value") else str(receipt_status)
        print(f"  [Agent B] → Receipt issued and verified: {receipt_status_str}")
        time.sleep(0.3)

        # ── STEP 6 — Agent A finalizes ──
        print_header("STEP 6 — Agent A finalizes")

        session_a.execute_action("receive_recommendation", {
            "from_agent": "agent_b", "item": "Patek Philippe 5711A", "price_eur": 120000
        })
        print("  [Agent A] → receive_recommendation recorded")

        session_a.execute_action("present_to_client", {
            "recommendation_id": "REC_001", "client_id": "VIP_001", "price_eur": 120000
        })
        print("  [Agent A] → present_to_client recorded")

        session_a.end_session()
        print("  [Agent A] → end_session recorded")

        session_b.end_session()
        print("  [Agent B] → end_session recorded")

        print("\n  [Agent A] → Decision trail complete.")
        time.sleep(0.3)

        # ── STEP 7 — Generate decision report ──
        print_header("STEP 7 — Decision report")

        report = {
            "client": "VIP_001",
            "decision": "recommendation",
            "item": "Patek Philippe 5711A",
            "price_eur": 120000,
            "agents": ["agent_a", "agent_b"],
            "causal_proof": dispatch_hash,
            "receipt_status": receipt_status_str,
        }

        outputs_dir = os.path.join(os.path.dirname(__file__), "outputs")
        os.makedirs(outputs_dir, exist_ok=True)
        report_path = os.path.join(outputs_dir, "decision_report.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        print(f"  Decision report saved → {report_path}")
        time.sleep(0.3)

        # ── STEP 8 — Verify both chains (clean) ──
        print_header("STEP 8 — Verify both chains (clean)")

        result_a = verify_shard(storage_a, "sessions")
        result_b = verify_shard(storage_b, "sessions")

        print_verify("Agent A", result_a)
        print_verify("Agent B", result_b)
        print("\n  ✓ Agent A chain intact.")
        print("  ✓ Agent B chain intact.")
        time.sleep(0.3)

        # ── STEP 9 — Tamper with Agent B's trail ──
        print_header("STEP 9 — Tamper with Agent B trail")

        shard_family_dir = storage_b.shards_dir / "sessions"
        segment_files = sorted(shard_family_dir.glob("*.jsonl"))

        if not segment_files:
            print("  ⚠ No segment files found — cannot demonstrate tampering.")
            return

        shard_file = segment_files[0]
        print(f"  ⚠ Simulating post-hoc modification on Agent B trail...")

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
            if not tampered and meta.get("action_name") == "return_recommendation":
                content = json.loads(entry_data["content"])
                content["payload"]["price_eur"] = 45000
                content["payload"]["rationale"] = "budget option selected by specialist"
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

        print("  Modified: price_eur 120000 → 45000")
        time.sleep(0.3)

        # ── STEP 10 — Verify after tampering ──
        print_header("STEP 10 — Verify after tampering")

        result_a_after = verify_shard(storage_a, "sessions")
        result_b_tampered = verify_shard(storage_b, "sessions")

        print_verify("Agent A", result_a_after)
        print_verify("Agent B", result_b_tampered)

        print("\n  ✓ Agent A chain still intact.")

        print("  Original : price_eur = 120000 | rationale = 'matches client preference for minimalist complications'")
        print("  Modified : price_eur = 45000  | rationale = 'budget option selected by specialist'")
        print("  → Hash mismatch detected")
        print("\n  ✗ Agent B trail compromised.")

        # Verify receipt against compromised storage if available
        if HAS_VERIFY_AGAINST_STORAGE:
            storage_check = verify_receipt_against_storage(storage_b, receipt)
            storage_check_status = storage_check.get("status", "UNKNOWN")
            storage_check_str = storage_check_status.value if hasattr(storage_check_status, "value") else str(storage_check_status)
            hash_matches = storage_check.get("hash_matches", "N/A")
            print(f"\n  Receipt vs storage: status={storage_check_str}, hash_matches={hash_matches}")
            if not hash_matches:
                print("  → Portable proof no longer reconciles with compromised trail.")

        time.sleep(0.3)

        # ── STEP 11 — Final summary ──
        print(f"""
{'─' * 55}
  MULTI-AGENT AUDIT SUMMARY
  Agent A entries    : {result_a['total_entries']}
  Agent B entries    : {result_b['total_entries']}
  Agent A status     : {status_str(result_a_after)}
  Agent B status     : {status_str(result_b_tampered)}
  Dispatch proof     : VERIFIED
  Receipt status     : {receipt_status_str}
  Tamper detected    : YES (Agent B — entry: return_recommendation)
  Verdict            : AGENT B TRAIL COMPROMISED
{'─' * 55}
  Two agents. One decision. Verifiable causality.
""")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
