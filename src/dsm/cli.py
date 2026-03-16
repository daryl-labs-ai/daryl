#!/usr/bin/env python3
"""DSM v2 CLI - Main entry point"""

import argparse
import json
import sys
import time
import uuid
from pathlib import Path
from datetime import datetime

from .core.models import Entry
from .core.storage import Storage
from .core.signing import Signing
from .core.session import SessionTracker
from .core.security import SecurityLayer
from .agent import DarylAgent
from .session.session_graph import SessionGraph
from .witness import ShardWitness
from .anchor import AnchorLog, verify_commitment, verify_all_commitments
from .audit import Policy, audit_shard, audit_all
from .coverage import check_coverage
from .seal import SealRegistry, list_sealed_shards, seal_shard as seal_shard_fn, verify_seal as verify_seal_fn
from .exchange import (
    TaskReceipt,
    issue_receipt as issue_receipt_fn,
    list_received_receipts as list_received_receipts_fn,
    verify_receipt as verify_receipt_fn,
)
from . import verify as dsm_verify


# =============================================================================
# DSM CLI (command name: dsm) — status, list-shards, read, append, replay
# =============================================================================

# ANSI colors for optional event-type coloring
_ANSI_CYAN = "\033[36m"
_ANSI_YELLOW = "\033[33m"
_ANSI_RED = "\033[31m"
_ANSI_RESET = "\033[0m"


def _entry_event_type(e: Entry) -> str:
    """Return event type for coloring: 'session', 'tool_call', 'error', or None."""
    meta = e.metadata or {}
    et = meta.get("event_type")
    if et in ("session_start", "session_end", "snapshot"):
        return "session"
    if et in ("tool_call", "action_intent", "action_result"):
        return "tool_call"
    if et == "error" or meta.get("error"):
        return "error"
    return ""


def _colorize(line: str, event_type: str, use_color: bool) -> str:
    """Optionally wrap line in ANSI color by event type. use_color=False or event_type '' => no color."""
    if not use_color or not event_type:
        return line
    if event_type == "session":
        return f"{_ANSI_CYAN}{line}{_ANSI_RESET}"
    if event_type == "tool_call":
        return f"{_ANSI_YELLOW}{line}{_ANSI_RESET}"
    if event_type == "error":
        return f"{_ANSI_RED}{line}{_ANSI_RESET}"
    return line


def _get_storage(data_dir: str = None):
    """Return a Storage instance; default data_dir is 'data'."""
    return Storage(data_dir=data_dir or "data")


def _cmd_status(args) -> None:
    """dsm status: show data dir and shard summary."""
    storage = _get_storage(args.data_dir)
    shards = storage.list_shards()
    total_entries = sum(s.entry_count for s in shards)
    print(f"Data dir: {storage.data_dir}")
    print(f"Shards: {len(shards)}")
    print(f"Total entries: {total_entries}")
    if shards:
        for s in shards:
            print(f"  - {s.shard_id}: {s.entry_count} entries")


def _cmd_list_shards(args) -> None:
    """dsm list-shards: list all shards with metadata."""
    storage = _get_storage(args.data_dir)
    shards = storage.list_shards()
    if not shards:
        print("No shards found.")
        return
    for s in shards:
        print(f"{s.shard_id}\t{s.entry_count}\t{s.last_updated}\t{s.integrity_status}")


def _print_entry(e: Entry, use_color: bool = False, flush: bool = False) -> None:
    """Print one entry as JSON line, optionally colored by event type."""
    line = _entry_to_json_line(e)
    event_type = _entry_event_type(e)
    out = _colorize(line, event_type, use_color)
    print(out, flush=flush)


def _cmd_read(args) -> None:
    """dsm read <shard_id> --limit N [--follow]: read recent entries; with --follow, poll for new (like tail)."""
    storage = _get_storage(args.data_dir)
    shard_id = args.shard_id
    limit = args.limit
    use_color = getattr(args, "color", False)
    follow = getattr(args, "follow", False)

    if not follow:
        entries = storage.read(shard_id, limit=limit)
        if not entries:
            print("No entries.")
            return
        for e in entries:
            _print_entry(e, use_color=use_color)
        return

    # --follow: same behavior as tail
    interval = getattr(args, "interval", 1.0)
    seen_ids = set()
    entries = storage.read(shard_id, limit=limit)
    if entries:
        for e in reversed(entries):
            _print_entry(e, use_color=use_color, flush=True)
            seen_ids.add(e.id)
    try:
        while True:
            time.sleep(interval)
            entries = storage.read(shard_id, limit=limit)
            new_entries = [e for e in entries if e.id not in seen_ids]
            for e in sorted(new_entries, key=lambda x: x.timestamp):
                _print_entry(e, use_color=use_color, flush=True)
                seen_ids.add(e.id)
    except KeyboardInterrupt:
        pass


def _cmd_append(args) -> None:
    """dsm append <shard_id> <json>: append one entry to a shard."""
    storage = _get_storage(args.data_dir)
    try:
        content = json.loads(args.json)
        if isinstance(content, dict):
            content = json.dumps(content, ensure_ascii=False)
        else:
            content = str(content)
    except json.JSONDecodeError:
        content = args.json
    entry = Entry(
        id=str(uuid.uuid4()),
        timestamp=datetime.utcnow(),
        session_id=args.session_id or "cli",
        source=args.source or "cli",
        content=content,
        shard=args.shard_id,
        hash="",
        prev_hash=None,
        metadata=args.metadata or {},
        version="v2.0",
    )
    stored = storage.append(entry)
    print(f"Appended entry {stored.id[:8]}... to shard {args.shard_id}")
    if stored.hash:
        print(f"Hash: {stored.hash[:16]}...")


def _cmd_verify(args) -> int:
    """dsm verify --all | --shard <shard_id>: verify hash chain integrity. Exit 0 if OK, 1 if tampered/broken."""
    storage = _get_storage(args.data_dir)
    if getattr(args, "all", False):
        results = dsm_verify.verify_all(storage)
    else:
        shard_id = getattr(args, "shard", None)
        if not shard_id:
            print("Error: use --all or --shard <shard_id>", file=sys.stderr)
            return 1
        results = [dsm_verify.verify_shard(storage, shard_id)]

    any_fail = False
    for r in results:
        print(f"Shard: {r['shard_id']} | entries: {r['total_entries']} | verified: {r['verified']} | tampered: {r['tampered']} | chain_breaks: {r['chain_breaks']} | status: {r['status']}")
        if r["status"] != "OK":
            any_fail = True
    return 0 if not any_fail else 1


def _cmd_replay(args) -> None:
    """dsm replay <shard_id>: verify hash chain for a shard (integrity replay)."""
    storage = _get_storage(args.data_dir)
    limit = args.limit or 1_000_000
    entries = storage.read(args.shard_id, limit=limit)
    if not entries:
        print(f"No entries in shard {args.shard_id}.")
        return
    # Verify chain expects chronological order (oldest first); read() returns newest first
    entries_chrono = list(reversed(entries))
    metrics = Signing.verify_chain(entries_chrono)
    total = len(entries)
    verified = metrics.get("verified", 0)
    corrupted = metrics.get("corrupted", 0)
    tampering = metrics.get("tampering_detected", 0)
    rate = metrics.get("verification_rate", 0)
    status = "OK" if (corrupted == 0 and tampering == 0) else "CORRUPT"
    print(f"Shard: {args.shard_id}")
    print(f"Entries: {total}")
    print(f"Verified: {verified} | Corrupted: {corrupted} | Tampering: {tampering}")
    print(f"Verification rate: {rate:.1f}%")
    print(f"Status: {status}")


def _cmd_inspect(args) -> None:
    """dsm inspect: number of shards, entries per shard, last update, recent sessions, recent actions."""
    storage = _get_storage(args.data_dir)
    shards = storage.list_shards()
    limit = args.limit or 500

    print(f"Data dir: {storage.data_dir}")
    print(f"Shards: {len(shards)}")
    print()

    # Entries per shard and last update time
    if shards:
        print("Per shard:")
        for s in shards:
            lu = s.last_updated.isoformat() if hasattr(s.last_updated, "isoformat") else str(s.last_updated)
            print(f"  {s.shard_id}: {s.entry_count} entries, last update {lu}")
    else:
        print("Per shard: (none)")
    print()

    # Recent session count and recent actions (from sessions shard)
    sessions_shard = "sessions"
    session_entries = storage.read(sessions_shard, limit=limit) if shards else []
    if not session_entries:
        print("Recent sessions: 0 (no sessions shard or empty)")
        print("Recent actions: (none)")
        return

    seen_sessions = set()
    for e in session_entries:
        if e.session_id and e.session_id != "cli":
            seen_sessions.add(e.session_id)
    print(f"Recent sessions (unique in last {len(session_entries)} entries): {len(seen_sessions)}")

    actions = []
    for e in session_entries:
        meta = e.metadata or {}
        et = meta.get("event_type")
        if et == "tool_call":
            actions.append(meta.get("action_name", "?") or "?")
        elif et == "action_intent":
            actions.append(meta.get("action_name", "?") or "?")
    if actions:
        print(f"Recent actions (last {len(actions)}):")
        for a in actions[: args.actions_limit]:
            print(f"  - {a}")
        if len(actions) > args.actions_limit:
            print(f"  ... and {len(actions) - args.actions_limit} more")
    else:
        print("Recent actions: (none)")


def _entry_to_json_line(e: Entry) -> str:
    """Format an Entry as a JSON line (same as read command)."""
    line = {
        "id": e.id,
        "timestamp": e.timestamp.isoformat(),
        "session_id": e.session_id,
        "source": e.source,
        "content": e.content,
        "shard": e.shard,
        "metadata": e.metadata,
    }
    return json.dumps(line, ensure_ascii=False)


def _cmd_agent_check(args) -> int:
    """dsm agent-check --data-dir <path>: verify + orphan detection, print summary. Exit 0 if OK, 1 if any issue."""
    data_dir = getattr(args, "data_dir", None) or "data"
    try:
        agent = DarylAgent(agent_id="cli-check", data_dir=data_dir)
    except Exception as e:
        print(f"Error initializing agent: {e}", file=sys.stderr)
        return 1
    verify_result = agent.verify()
    orphans = agent.orphaned_intents()
    results = verify_result if isinstance(verify_result, list) else [verify_result]
    total_entries = sum(r.get("total_entries", 0) for r in results)
    ok = all(r.get("status") == "OK" for r in results)
    orphan_count = len(orphans)
    print(f"Shards: {len(results)} | entries: {total_entries} | integrity: {'OK' if ok else 'FAIL'} | orphaned intents: {orphan_count}")
    for r in results:
        print(f"  {r.get('shard_id', '?')}: {r.get('total_entries', 0)} entries, status={r.get('status', '?')}")
    if orphan_count > 0:
        for e in orphans[:10]:
            meta = e.metadata or {}
            print(f"  orphan intent_id={(meta.get('intent_id') or e.id)[:12]}... action={meta.get('action_name', '?')}")
    return 0 if ok and orphan_count == 0 else 1


def _cmd_audit(args) -> int:
    """dsm audit --data-dir <path> --policy <path> [--shard <id>]: verify actions against policy. Exit 0 if COMPLIANT, 1 if VIOLATIONS_FOUND."""
    data_dir = getattr(args, "data_dir", None) or "data"
    policy_path = getattr(args, "policy", None)
    if not policy_path:
        print("Error: --policy is required", file=sys.stderr)
        return 1
    shard_id = getattr(args, "shard", None)
    try:
        policy = Policy.from_file(policy_path)
    except Exception as e:
        print(f"Error loading policy: {e}", file=sys.stderr)
        return 1
    storage = _get_storage(data_dir)
    if shard_id:
        results = [audit_shard(storage, shard_id, policy)]
    else:
        results = audit_all(storage, policy)

    any_violations = False
    for r in results:
        print(f"Shard: {r['shard_id']} | entries: {r['total_entries']} | actions_checked: {r['actions_checked']} | violations: {r['violation_count']} | status: {r['status']}")
        for v in r["violations"]:
            any_violations = True
            print(f"  violation | rule={v['rule']} detail={v['detail']} action_name={v.get('action_name')} entry_id={v.get('entry_id')}")
    return 1 if any_violations else 0


def _cmd_receipt_issue(args) -> int:
    """dsm receipt-issue: issue a task receipt, print JSON to stdout."""
    data_dir = getattr(args, "data_dir", None) or "data"
    shard_id = getattr(args, "shard", None)
    entry_id = getattr(args, "entry", None)
    task = getattr(args, "task", "") or ""
    agent_id = getattr(args, "agent_id", None) or "cli"
    if not shard_id or not entry_id:
        print("Error: --shard and --entry are required", file=sys.stderr)
        return 1
    try:
        storage = _get_storage(data_dir)
        receipt = issue_receipt_fn(storage, agent_id, entry_id, shard_id, task)
        print(receipt.to_json())
        return 0
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _cmd_receipt_verify(args) -> int:
    """dsm receipt-verify: verify receipt integrity. Exit 0 if INTACT, 1 if TAMPERED."""
    receipt_arg = getattr(args, "receipt", "")
    if not receipt_arg:
        print("Error: receipt (JSON or file path) required", file=sys.stderr)
        return 1
    if receipt_arg.strip().startswith("{"):
        receipt_json = receipt_arg
    elif Path(receipt_arg).exists():
        with open(receipt_arg, "r", encoding="utf-8") as f:
            receipt_json = f.read()
    else:
        receipt_json = receipt_arg
    try:
        receipt = TaskReceipt.from_json(receipt_json)
    except Exception as e:
        print(f"Error parsing receipt: {e}", file=sys.stderr)
        return 1
    result = verify_receipt_fn(receipt)
    print(f"receipt_id={result['receipt_id']} status={result['status']} issuer={result['issuer']} task={result['task']}")
    return 0 if result["status"] == "INTACT" else 1


def _cmd_receipt_list(args) -> int:
    """dsm receipt-list: list received receipts in receipts shard."""
    data_dir = getattr(args, "data_dir", None) or "data"
    storage = _get_storage(data_dir)
    receipts = list_received_receipts_fn(storage, shard_id="receipts")
    for r in receipts:
        task_preview = (r.task_description[:50] + "…") if len(r.task_description) > 50 else r.task_description
        print(f"receipt_id={r.receipt_id} issuer={r.issuer_agent_id} task={task_preview} timestamp={r.timestamp}")
    if not receipts:
        print("No received receipts.")
    return 0


def _cmd_seal(args) -> int:
    """dsm seal --data-dir <path> --shard <id> [--archive <path>]: seal shard, optionally archive. Exit 0 on success."""
    data_dir = getattr(args, "data_dir", None) or "data"
    shard_id = getattr(args, "shard", None)
    archive_path = getattr(args, "archive", None)
    if not shard_id:
        print("Error: --shard is required", file=sys.stderr)
        return 1
    try:
        storage = _get_storage(data_dir)
        registry = SealRegistry(str(Path(data_dir) / "seals"))
        record = seal_shard_fn(storage, shard_id, registry, archive_path)
        print(f"shard_id={record.shard_id} entry_count={record.entry_count} seal_hash={record.seal_hash[:16]}... seal_timestamp={record.seal_timestamp}")
        if record.archived_path:
            print(f"archived_path={record.archived_path}")
        return 0
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _cmd_seal_verify(args) -> int:
    """dsm seal-verify --data-dir <path> [--shard <id>]: verify seal(s). Exit 0 if all VALID."""
    data_dir = getattr(args, "data_dir", None) or "data"
    shard_id = getattr(args, "shard", None)
    registry = SealRegistry(str(Path(data_dir) / "seals"))
    if shard_id:
        results = [verify_seal_fn(registry, shard_id)]
    else:
        all_records = registry.read_all()
        results = [verify_seal_fn(registry, r.shard_id) for r in all_records]
    any_fail = False
    for r in results:
        print(f"shard_id={r['shard_id']} status={r['status']} entry_count={r.get('entry_count', 0)} sealed_at={r.get('sealed_at', '')}")
        if r.get("status") != "VALID":
            any_fail = True
    return 1 if any_fail else 0


def _cmd_sealed(args) -> None:
    """dsm sealed --data-dir <path>: list all sealed shards."""
    data_dir = getattr(args, "data_dir", None) or "data"
    registry = SealRegistry(str(Path(data_dir) / "seals"))
    items = list_sealed_shards(registry)
    for s in items:
        print(f"shard_id={s['shard_id']} entry_count={s['entry_count']} sealed_at={s['sealed_at']} archived={'yes' if s['archived'] else 'no'}")
    if not items:
        print("No sealed shards.")


def _cmd_witness(args) -> None:
    """dsm witness --data-dir <path> --witness-dir <path> [--key <secret>]: capture witness for all shards."""
    data_dir = getattr(args, "data_dir", None) or "data"
    witness_dir = getattr(args, "witness_dir", None)
    if not witness_dir:
        print("Error: --witness-dir is required", file=sys.stderr)
        sys.exit(1)
    witness_key = getattr(args, "key", None) or ""
    storage = _get_storage(data_dir)
    witness = ShardWitness(witness_dir, witness_key=witness_key)
    records = witness.capture_all(storage)
    for r in records:
        print(json.dumps(r, ensure_ascii=False))
    if not records:
        print("No shards to witness.")


def _cmd_witness_check(args) -> int:
    """dsm witness-check: verify shards against witness log. Exit 0 if OK, 1 if any DIVERGED."""
    data_dir = getattr(args, "data_dir", None) or "data"
    witness_dir = getattr(args, "witness_dir", None)
    if not witness_dir:
        print("Error: --witness-dir is required", file=sys.stderr)
        return 1
    witness_key = getattr(args, "key", None) or ""
    shard_id = getattr(args, "shard", None)

    storage = _get_storage(data_dir)
    witness = ShardWitness(witness_dir, witness_key=witness_key)

    if shard_id:
        results = [witness.verify_shard_against_witness(storage, shard_id)]
    else:
        log_records = witness.read_log()
        shard_ids = list({r["shard_id"] for r in log_records})
        results = [witness.verify_shard_against_witness(storage, sid) for sid in shard_ids]

    any_diverged = False
    for r in results:
        print(json.dumps(r, ensure_ascii=False))
        if r.get("status") == "DIVERGED":
            any_diverged = True

    return 1 if any_diverged else 0


def _cmd_orphans(args) -> int:
    """dsm orphans --data-dir <path>: list intents without result (crash detection). Exit 0 if none, 1 if any."""
    data_dir = getattr(args, "data_dir", None) or "data"
    storage = _get_storage(data_dir)
    graph = SessionGraph(storage=storage)
    orphaned = graph.find_orphaned_intents(storage=storage)
    if not orphaned:
        print("No orphaned intents.")
        return 0
    print(f"Found {len(orphaned)} orphaned intent(s):")
    for e in orphaned:
        meta = e.metadata or {}
        intent_id = meta.get("intent_id") or e.id
        action_name = meta.get("action_name", "?")
        ts = e.timestamp.isoformat() if hasattr(e.timestamp, "isoformat") else str(e.timestamp)
        print(f"  intent_id={intent_id[:12]}... action_name={action_name} timestamp={ts}")
    return 1


def _cmd_anchor_verify(args) -> int:
    """dsm anchor-verify --anchor-dir <path> [--intent <id>]: verify pre/post commitment pairs."""
    anchor_dir = getattr(args, "anchor_dir", None)
    if not anchor_dir:
        print("Error: --anchor-dir is required", file=sys.stderr)
        return 1
    intent_id = getattr(args, "intent", None)

    anchor_log = AnchorLog(anchor_dir)

    if intent_id:
        result = verify_commitment(anchor_log, intent_id)
        print(f"Intent: {intent_id} | status: {result['status']} | pre: {result['pre_commit_at']} | post: {result['post_commit_at']} | delta_ms: {result['time_delta_ms']}")
        return 0 if result["status"] == "VERIFIED" else 1

    result = verify_all_commitments(anchor_log)
    print(f"Commits: {result['total_commits']} | verified: {result['verified']} | violations: {result['violations']} | incomplete: {result['incomplete']} | status: {result['status']}")
    return 0 if result["status"] == "ALL_VERIFIED" else 1


def _cmd_coverage(args) -> int:
    """dsm coverage --data-dir <path> --index-file <path> [--shard <id>]: check agent index coverage against DSM log."""
    data_dir = getattr(args, "data_dir", None) or "data"
    index_file = getattr(args, "index_file", None)
    shard_id = getattr(args, "shard", None)

    if not index_file:
        print("Error: --index-file is required (JSON with 'ids' and/or 'hashes' arrays)", file=sys.stderr)
        return 1

    try:
        with open(index_file, "r", encoding="utf-8") as f:
            index_data = json.load(f)
    except Exception as e:
        print(f"Error loading index file: {e}", file=sys.stderr)
        return 1

    indexed_ids = set(index_data.get("ids", []))
    indexed_hashes = set(index_data.get("hashes", []))

    if not indexed_ids and not indexed_hashes:
        print("Error: index file must contain 'ids' and/or 'hashes' arrays", file=sys.stderr)
        return 1

    storage = _get_storage(data_dir)
    shard_ids = [shard_id] if shard_id else None

    result = check_coverage(
        storage,
        indexed_ids=indexed_ids or None,
        indexed_hashes=indexed_hashes or None,
        shard_ids=shard_ids,
    )

    print(f"Coverage: {result['coverage_percent']}% | indexed: {result['indexed_entries']}/{result['total_entries']} | missing: {result['missing_entries']} | status: {result['status']}")
    if result["per_shard"]:
        for sid, info in result["per_shard"].items():
            print(f"  shard {sid}: {info['indexed']}/{info['total']} indexed, {info['missing']} missing")
    if result["gaps"]:
        print(f"Gaps ({len(result['gaps'])}{'+ (truncated)' if result['gaps_truncated'] else ''}):")
        for g in result["gaps"][:20]:
            print(f"  entry={g['entry_id'][:12]}... event={g['event_type']} preview={g['content_preview'][:60]}")
        if len(result["gaps"]) > 20:
            print(f"  ... and {len(result['gaps']) - 20} more")

    return 0 if result["status"] in ("FULLY_COVERED", "PARTIAL_COVERAGE") else 1


def _cmd_tail(args) -> None:
    """dsm tail <shard_id>: continuously display new entries (like tail -f), poll Storage.read."""
    storage = _get_storage(args.data_dir)
    shard_id = args.shard_id
    limit = args.limit
    interval = args.interval
    use_color = getattr(args, "color", False)
    seen_ids = set()

    # Initial read: show last N entries in chronological order, then follow
    entries = storage.read(shard_id, limit=limit)
    if not entries:
        pass  # no initial lines
    else:
        for e in reversed(entries):
            _print_entry(e, use_color=use_color, flush=True)
            seen_ids.add(e.id)

    # Follow: poll and print only new entries
    try:
        while True:
            time.sleep(interval)
            entries = storage.read(shard_id, limit=limit)
            new_entries = [e for e in entries if e.id not in seen_ids]
            for e in sorted(new_entries, key=lambda x: x.timestamp):
                _print_entry(e, use_color=use_color, flush=True)
                seen_ids.add(e.id)
    except KeyboardInterrupt:
        pass


def main_dsm() -> None:
    """Entry point for the 'dsm' command."""
    parser = argparse.ArgumentParser(prog="dsm", description="DSM CLI - status, list-shards, read, append, replay")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # dsm status
    p_status = subparsers.add_parser("status", help="Show DSM status and shard summary")
    p_status.add_argument("--data-dir", default=None, help="DSM data directory (default: data)")
    p_status.set_defaults(func=_cmd_status)

    # dsm list-shards
    p_list = subparsers.add_parser("list-shards", help="List all shards with metadata")
    p_list.add_argument("--data-dir", default=None, help="DSM data directory (default: data)")
    p_list.set_defaults(func=_cmd_list_shards)

    # dsm read <shard_id> [--limit N] [--follow]
    p_read = subparsers.add_parser("read", help="Read recent entries from a shard (JSON lines); --follow polls for new")
    p_read.add_argument("shard_id", help="Shard ID")
    p_read.add_argument("--limit", type=int, default=100, help="Max entries (default: 100)")
    p_read.add_argument("--follow", "-f", action="store_true", help="Keep polling and display new entries (like tail -f)")
    p_read.add_argument("--interval", type=float, default=1.0, help="Poll interval in seconds when using --follow (default: 1.0)")
    p_read.add_argument("--color", action="store_true", help="Color output by event type (session=cyan, tool_call=yellow, error=red)")
    p_read.add_argument("--data-dir", default=None, help="DSM data directory (default: data)")
    p_read.set_defaults(func=_cmd_read)

    # dsm append <shard_id> <json>
    p_append = subparsers.add_parser("append", help="Append one entry (JSON content) to a shard")
    p_append.add_argument("shard_id", help="Shard ID")
    p_append.add_argument("json", help="Entry content (JSON string or object)")
    p_append.add_argument("--session-id", default=None, help="Session ID (default: cli)")
    p_append.add_argument("--source", default=None, help="Source (default: cli)")
    p_append.add_argument("--metadata", type=json.loads, default=None, help="Metadata as JSON object")
    p_append.add_argument("--data-dir", default=None, help="DSM data directory (default: data)")
    p_append.set_defaults(func=_cmd_append)

    # dsm verify --all | --shard <shard_id>
    p_verify = subparsers.add_parser("verify", help="Verify hash chain integrity (--all or --shard <id>)")
    p_verify.add_argument("--all", action="store_true", help="Verify all shards")
    p_verify.add_argument("--shard", type=str, default=None, help="Verify a single shard by ID")
    p_verify.add_argument("--data-dir", default=None, help="DSM data directory (default: data)")
    p_verify.set_defaults(func=_cmd_verify)

    # dsm replay <shard_id>
    p_replay = subparsers.add_parser("replay", help="Verify hash chain for a shard (integrity replay)")
    p_replay.add_argument("shard_id", help="Shard ID")
    p_replay.add_argument("--limit", type=int, default=None, help="Max entries to verify (default: all)")
    p_replay.add_argument("--data-dir", default=None, help="DSM data directory (default: data)")
    p_replay.set_defaults(func=_cmd_replay)

    # dsm inspect
    p_inspect = subparsers.add_parser("inspect", help="Show shard counts, last update, recent sessions and actions")
    p_inspect.add_argument("--data-dir", default=None, help="DSM data directory (default: data)")
    p_inspect.add_argument("--limit", type=int, default=500, help="Max session entries to scan (default: 500)")
    p_inspect.add_argument("--actions-limit", type=int, default=20, help="Max recent actions to display (default: 20)")
    p_inspect.set_defaults(func=_cmd_inspect)

    # dsm tail <shard_id>
    p_tail = subparsers.add_parser("tail", help="Continuously display new entries (like tail -f); poll Storage.read")
    p_tail.add_argument("shard_id", help="Shard ID")
    p_tail.add_argument("--color", action="store_true", help="Color output by event type (session=cyan, tool_call=yellow, error=red)")
    p_tail.add_argument("--data-dir", default=None, help="DSM data directory (default: data)")
    p_tail.add_argument("--limit", type=int, default=100, help="Max entries to read per poll (default: 100)")
    p_tail.add_argument("--interval", type=float, default=1.0, help="Poll interval in seconds (default: 1.0)")
    p_tail.set_defaults(func=_cmd_tail)

    # dsm orphans
    p_orphans = subparsers.add_parser("orphans", help="List action intents without result (crash detection)")
    p_orphans.add_argument("--data-dir", default=None, help="DSM data directory (default: data)")
    p_orphans.set_defaults(func=_cmd_orphans)

    # dsm agent-check
    p_agent_check = subparsers.add_parser("agent-check", help="Verify integrity and orphan intents (summary)")
    p_agent_check.add_argument("--data-dir", default=None, help="DSM data directory (default: data)")
    p_agent_check.set_defaults(func=_cmd_agent_check)

    # dsm audit
    p_audit = subparsers.add_parser("audit", help="Verify shard actions against a policy")
    p_audit.add_argument("--data-dir", default=None, help="DSM data directory (default: data)")
    p_audit.add_argument("--policy", default=None, help="Path to policy JSON file (required)")
    p_audit.add_argument("--shard", default=None, help="Audit a single shard by ID")
    p_audit.set_defaults(func=_cmd_audit)

    # dsm seal
    p_seal = subparsers.add_parser("seal", help="Seal a shard (cryptographic proof)")
    p_seal.add_argument("--data-dir", default=None, help="DSM data directory (default: data)")
    p_seal.add_argument("--shard", default=None, help="Shard ID to seal (required)")
    p_seal.add_argument("--archive", default=None, help="Directory to archive sealed data (gzip)")
    p_seal.set_defaults(func=_cmd_seal)

    # dsm seal-verify
    p_seal_verify = subparsers.add_parser("seal-verify", help="Verify seal record(s)")
    p_seal_verify.add_argument("--data-dir", default=None, help="DSM data directory (default: data)")
    p_seal_verify.add_argument("--shard", default=None, help="Verify single shard seal")
    p_seal_verify.set_defaults(func=_cmd_seal_verify)

    # dsm sealed
    p_sealed = subparsers.add_parser("sealed", help="List sealed shards")
    p_sealed.add_argument("--data-dir", default=None, help="DSM data directory (default: data)")
    p_sealed.set_defaults(func=_cmd_sealed)

    # dsm receipt-issue
    p_receipt_issue = subparsers.add_parser("receipt-issue", help="Issue a cross-agent task receipt (prints JSON)")
    p_receipt_issue.add_argument("--data-dir", default=None, help="DSM data directory (default: data)")
    p_receipt_issue.add_argument("--shard", default=None, help="Shard containing the entry (required)")
    p_receipt_issue.add_argument("--entry", default=None, help="Entry ID (required)")
    p_receipt_issue.add_argument("--task", default="", help="Task description")
    p_receipt_issue.add_argument("--agent-id", default="cli", help="Issuer agent ID")
    p_receipt_issue.set_defaults(func=_cmd_receipt_issue)

    # dsm receipt-verify
    p_receipt_verify = subparsers.add_parser("receipt-verify", help="Verify receipt integrity (offline)")
    p_receipt_verify.add_argument("receipt", help="JSON string or path to file containing receipt")
    p_receipt_verify.set_defaults(func=_cmd_receipt_verify)

    # dsm receipt-list
    p_receipt_list = subparsers.add_parser("receipt-list", help="List received receipts")
    p_receipt_list.add_argument("--data-dir", default=None, help="DSM data directory (default: data)")
    p_receipt_list.set_defaults(func=_cmd_receipt_list)

    # dsm anchor-verify
    p_anchor = subparsers.add_parser("anchor-verify", help="Verify pre/post commitment pairs")
    p_anchor.add_argument("--anchor-dir", default=None, help="Directory containing anchor_log.jsonl (required)")
    p_anchor.add_argument("--intent", default=None, help="Verify a single intent by ID")
    p_anchor.set_defaults(func=_cmd_anchor_verify)

    # dsm coverage
    p_coverage = subparsers.add_parser("coverage", help="Check agent index coverage against DSM log")
    p_coverage.add_argument("--data-dir", default=None, help="DSM data directory (default: data)")
    p_coverage.add_argument("--index-file", default=None, help="JSON file with 'ids' and/or 'hashes' arrays (required)")
    p_coverage.add_argument("--shard", default=None, help="Check a single shard by ID")
    p_coverage.set_defaults(func=_cmd_coverage)

    # dsm witness
    p_witness = subparsers.add_parser("witness", help="Capture witness snapshot for all shards")
    p_witness.add_argument("--data-dir", default=None, help="DSM data directory (default: data)")
    p_witness.add_argument("--witness-dir", default=None, help="Directory for witness log (required)")
    p_witness.add_argument("--key", default=None, help="Optional witness key for signing")
    p_witness.set_defaults(func=_cmd_witness)

    # dsm witness-check
    p_witness_check = subparsers.add_parser("witness-check", help="Verify shards against witness log")
    p_witness_check.add_argument("--data-dir", default=None, help="DSM data directory (default: data)")
    p_witness_check.add_argument("--witness-dir", default=None, help="Directory for witness log (required)")
    p_witness_check.add_argument("--key", default=None, help="Optional witness key (must match capture)")
    p_witness_check.add_argument("--shard", default=None, help="Check a single shard by ID")
    p_witness_check.set_defaults(func=_cmd_witness_check)

    args = parser.parse_args()
    ret = args.func(args)
    if ret is not None and ret != 0:
        sys.exit(ret)


class DSMCLI:
    """Interface CLI DSM v2"""

    def __init__(self):
        self.storage = Storage()
        self.signing = Signing()
        self.session_tracker = SessionTracker()
        self.security = SecurityLayer()

    # ========================================================================
    # STANDARD COMMANDS
    # ========================================================================

    def init(self, args):
        """Initialise DSM v2"""
        print("🚀 Initialisation DSM v2...")
        print(f"   Data dir: {self.storage.data_dir}")
        print(f"   Session state: {self.session_tracker.state_file}")

        # Initialiser la baseline de sécurité
        print("   Initialising security baseline...")
        self.security.update_baseline(reason="Initial setup", force=True)

        print("✅ Initialisation terminée")

    def add(self, args):
        """Ajoute une entrée (avec security guard)"""
        import uuid
        from core.models import Entry

        content = args.content
        source = args.source or "cli"
        shard = args.shard or "default"

        # === SECURITY GUARD ===
        # Rate limit check
        allowed, message = self.security.check_rate_limit("append_shard")
        if not allowed:
            print(f"⚠️  {message}")
            return

        # Create entry
        entry = Entry(
            id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            session_id=self.session_tracker.state.get("current_session", "unknown"),
            source=source,
            content=content,
            shard=shard,
            hash="",  # Will be computed by storage
            prev_hash=None,
            metadata={"manual": True},
            version="v2.0"
        )

        stored = self.storage.append(entry)

        # Audit log
        self.security.audit_action("append_shard", {
            "entry_id": entry.id[:8],
            "shard": shard,
            "content_length": len(content),
            "source": source
        })

        print("✅ Entrée ajoutée")
        print(f"   ID: {entry.id[:8]}...")
        print(f"   Shard: {shard}")
        print(f"   Hash: {stored.hash[:16]}...")

    def verify(self, args):
        """Vérifie l'intégrité"""
        # Read all shards
        shards = self.storage.list_shards()

        # Check each shard
        issues = []
        metrics = {}
        for shard in shards:
            entries = self.storage.read(shard.shard_id, limit=1000)
            shard_metrics = self.signing.verify_chain(entries)
            metrics = shard_metrics  # Update metrics for the last shard

            if shard_metrics.get("corrupted", 0) > 0:
                issues.append(f"{shard.shard_id}: {shard_metrics['corrupted']} corrupted")
            if shard_metrics.get("tampering_detected", 0) > 0:
                issues.append(f"{shard.shard_id}: {shard_metrics['tampering_detected']} tampering")

        if issues:
            print("⚠️  Problèmes détectés :")
            for issue in issues:
                print(f"   {issue}")
        elif shards:
            print("✅ Intégrité vérifiée")
            print(f"   Verification rate: {metrics.get('verification_rate', 100):.1f}%")
        else:
            print("✅ Intégrité vérifiée (aucun shard)")

    def session_start(self, args):
        """Démarre une session"""
        session = self.session_tracker.start_session()
        print("✅ Session démarrée")
        print(f"   Session ID: {session.id[:8]}...")

    def session_status(self, args):
        """Statut des sessions"""
        current = self.session_tracker.get_current_session()
        sessions = self.session_tracker.get_sessions(limit=10)

        print("📊 Sessions")
        if current:
            print(f"   Actuelle: {current.id[:8]}...")
            print(f"   Démarrée: {current.started_at}")
            print(f"   Heartbeats: {current.heartbeat_count}")
            print(f"   Score: {current.stability_score:.2f}")
        else:
            print("   Aucune session active")

        print(f"   Récentes: {len(sessions)} sessions")
        for s in sessions[:5]:
            print(f"   - {s.id[:8]}... | {s.started_at[:19]} | {s.stability_score:.2f}")

    # ========================================================================
    # SECURITY COMMANDS
    # ========================================================================

    def security_check(self, args):
        """Commande: python -m dsm security check"""
        from core.security import cmd_check
        cmd_check(args)

    def security_update_baseline(self, args):
        """Commande: python -m dsm security update-baseline"""
        from core.security import cmd_update_baseline
        cmd_update_baseline(args)

    def security_audit(self, args):
        """Commande: python -m dsm security audit"""
        from core.security import cmd_audit
        cmd_audit(args)

    def security_self_check(self, args):
        """Commande: python -m dsm security self-check"""
        from core.security import cmd_self_check
        cmd_self_check(args)

    # ========================================================================
    # TRACE REPLAY COMMANDS (PR-A)
    # ========================================================================

    def trace_replay(self, args):
        """Commande: python -m dsm trace replay"""
        from core.replay import main as replay_main

        # Passer les arguments
        replay_argv = [
            "--session", args.session,
            "--trace-file", args.trace_file,
            "--output-dir", args.output_dir,
        ]

        if args.strict:
            replay_argv.append("--strict")

        if args.limit:
            replay_argv.extend(["--limit", str(args.limit)])

        # Simuler argv pour le module replay
        import sys
        old_argv = sys.argv
        sys.argv = ["trace"] + replay_argv

        try:
            replay_main()
        finally:
            sys.argv = old_argv

    # ========================================================================
    # MAIN
    # ========================================================================

    def main(self):
        parser = argparse.ArgumentParser(
            description="DSM v2 - Decision Support Memory",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="Use 'python -m dsm <command>' to execute."
        )

        subparsers = parser.add_subparsers(dest="command", help="Commande DSM v2")

        # === STANDARD COMMANDS ===
        # init
        parser_init = subparsers.add_parser("init", help="Initialise DSM v2 (avec baseline integrity)")
        parser_init.set_defaults(func=self.init)

        # add
        parser_add = subparsers.add_parser("add", help="Ajoute une entrée")
        parser_add.add_argument("--content", required=True, help="Contenu de l'entrée")
        parser_add.add_argument("--source", default="cli", help="Source de l'entrée")
        parser_add.add_argument("--shard", default="default", help="Shard cible")
        parser_add.set_defaults(func=self.add)

        # verify
        parser_verify = subparsers.add_parser("verify", help="Vérifie l'intégrité")
        parser_verify.set_defaults(func=self.verify)

        # session-start
        parser_session_start = subparsers.add_parser("session-start", help="Démarre une session")
        parser_session_start.set_defaults(func=self.session_start)

        # session-status
        parser_session_status = subparsers.add_parser("session-status", help="Statut des sessions")
        parser_session_status.set_defaults(func=self.session_status)

        # === TRACE REPLAY COMMANDS (PR-A) ===
        parser_trace = subparsers.add_parser("trace", help="Commandes de trace")
        trace_subparsers = parser_trace.add_subparsers(dest="trace_command", help="Sous-commandes trace")

        # trace replay
        parser_trace_replay = trace_subparsers.add_parser("replay", help="Rejoue une session de trace (audit-only)")
        parser_trace_replay.add_argument("--session", required=True, help="Session ID")
        parser_trace_replay.add_argument("--strict", action="store_true", help="Mode strict")
        parser_trace_replay.add_argument("--limit", type=int, help="Limite de records")
        parser_trace_replay.add_argument("--trace-file", default="data/traces/trace_log.jsonl", help="Fichier de trace")
        parser_trace_replay.add_argument("--output-dir", default="data/diagnostics", help="Répertoire de sortie")
        parser_trace_replay.set_defaults(func=self.trace_replay)

        # === SECURITY COMMANDS ===
        parser_security = subparsers.add_parser("security", help="Commandes de sécurité")
        security_subparsers = parser_security.add_subparsers(dest="security_command", help="Sous-commandes sécurité")

        # security check
        parser_security_check = security_subparsers.add_parser("check", help="Vérifie le statut de sécurité")
        parser_security_check.set_defaults(func=self.security_check)

        # security update-baseline
        parser_security_update = security_subparsers.add_parser("update-baseline", help="Met à jour la baseline (gated)")
        parser_security_update.add_argument("--reason", type=str, help='Raison de la mise à jour (ex: "Updated SOUL.md")')
        parser_security_update.add_argument("--manual-ack", type=str, help='Confirmation manuelle "I UNDERSTAND"')
        parser_security_update.add_argument("--force", action="store_true", help='Force la mise à jour (skip gates, nécessite double I UNDERSTAND)')
        parser_security_update.set_defaults(func=self.security_update_baseline)

        # security audit
        parser_security_audit = security_subparsers.add_parser("audit", help="Montre le log d'audit")
        parser_security_audit.add_argument("--limit", type=int, default=20, help="Nombre d'événements à afficher")
        parser_security_audit.set_defaults(func=self.security_audit)

        # security self-check
        parser_security_self = security_subparsers.add_parser("self-check", help="Self-check (JSON output)")
        parser_security_self.set_defaults(func=self.security_self_check)

        # === TRACE REPLAY COMMANDS (PR-A) ===
        parser_trace = subparsers.add_parser("trace", help="Commandes de trace")
        trace_subparsers = parser_trace.add_subparsers(dest="trace_command", help="Sous-commandes trace")

        # trace replay
        parser_trace_replay = trace_subparsers.add_parser("replay", help="Rejoue une session de trace (audit-only)")
        parser_trace_replay.add_argument("--session", required=True, help="Session ID à rejouer")
        parser_trace_replay.add_argument("--strict", action="store_true", help="Mode strict: toute divergence = CORRUPT")
        parser_trace_replay.add_argument("--limit", type=int, help="Limiter le nombre de records")
        parser_trace_replay.add_argument("--trace-file", default="data/traces/trace_log.jsonl", help="Fichier de trace")
        parser_trace_replay.add_argument("--output-dir", default="data/diagnostics", help="Répertoire de sortie")
        parser_trace_replay.set_defaults(func=self.trace_replay)

        # Parse
        args = parser.parse_args()

        # Router les commandes
        if args.command == "security":
            # Sous-commandes sécurité
            args.func(args)
        elif args.command == "trace":
            # Sous-commandes trace (PR-A)
            args.func(args)
        else:
            # Commandes standard
            args.func(args)


if __name__ == "__main__":
    cli = DSMCLI()
    cli.main()
