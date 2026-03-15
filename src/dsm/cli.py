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
    if et == "tool_call":
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
        if meta.get("event_type") == "tool_call":
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
