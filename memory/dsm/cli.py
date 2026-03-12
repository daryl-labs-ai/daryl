#!/usr/bin/env python3
"""DSM v2 CLI - Main entry point"""

import argparse
import sys
from pathlib import Path
from datetime import datetime

# Add dsm_v2 to path
sys.path.insert(0, str(Path(__file__).parent))

from core.models import Entry
from core.storage import Storage
from core.signing import Signing
from core.session import SessionTracker
from core.security import SecurityLayer


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
        """Commande: python -m dsm_v2 security check"""
        from core.security import cmd_check
        cmd_check(args)

    def security_update_baseline(self, args):
        """Commande: python -m dsm_v2 security update-baseline"""
        from core.security import cmd_update_baseline
        cmd_update_baseline(args)

    def security_audit(self, args):
        """Commande: python -m dsm_v2 security audit"""
        from core.security import cmd_audit
        cmd_audit(args)

    def security_self_check(self, args):
        """Commande: python -m dsm_v2 security self-check"""
        from core.security import cmd_self_check
        cmd_self_check(args)

    # ========================================================================
    # TRACE REPLAY COMMANDS (PR-A)
    # ========================================================================

    def trace_replay(self, args):
        """Commande: python -m dsm_v2 trace replay"""
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
            epilog="Use 'python -m dsm_v2 <command>' to execute."
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
