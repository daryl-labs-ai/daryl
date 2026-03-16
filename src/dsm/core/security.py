#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSM Kernel — Frozen Module

This file is part of the DSM storage kernel freeze (March 2026).

The kernel is considered stable and audited.

Modifications must follow the DSM kernel evolution process
and should not be changed casually.

See:
docs/architecture/DSM_KERNEL_FREEZE_2026_03.md
"""
"""
DSM v2 - Security Layer (Kernel v2 Integration)

Protection for Sharding Memory System:
- Anti-injection (kernel v2 code integrity)
- Anti-erasure (integrity logs protection)
- Baseline gating (manual ack required)
- Rate limiting (API + file writes)

Architecture:
- Critical files: src/dsm/core/*.py, data/security/*
- Excluded: data/shards/*.jsonl (append-only, hash chain protected)
"""

# MIGRATION NOTE (March 2026):
# Path constants (CRITICAL_FILES, PROTECTED_WRITE_FILES) updated during
# src/ layout migration. No logic change. See repo-restructure branch.
# This is a configuration-only exception to the kernel freeze.

import hashlib
import json
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import logging
import sys

# ============================================================================
# CONFIGURATION
# ============================================================================

# Security directory
SECURITY_DIR = Path("data/security")
INTEGRITY_FILE = SECURITY_DIR / "integrity.json"
AUDIT_LOG = SECURITY_DIR / "audit.jsonl"
BASELINE_LOCK_FILE = SECURITY_DIR / "baseline.lock"

# Critical files for DSM v2 Sharding Memory (protected by baseline)
# NOTE: 
# - shards (data/shards/*.jsonl) are EXCLUDED - they change constantly
#   and are protected by the hash chain, not by baseline monitoring
# - Runtime state files are EXCLUDED - they change during normal operation
#   and are not protected by baseline (protected by code integrity instead)
CRITICAL_FILES = [
    # DSM kernel (src/dsm/core/)
    "src/dsm/core/models.py",
    "src/dsm/core/storage.py",
    "src/dsm/core/signing.py",
    "src/dsm/core/shard_segments.py",
    "src/dsm/core/replay.py",
    "src/dsm/core/security.py",  # Self-protection
    # Integrity baseline & policy (protected, not runtime state)
    "data/security/baseline.json",
    "data/security/policy.json",
]

# Protected files (write guard - prevent automatic rewrites)
PROTECTED_WRITE_FILES = [
    "src/dsm/core/security.py",
    "src/dsm/cli.py",
    "data/security/policy.json",
    "data/security/integrity.json",
]

# Rate limits
MAX_API_REQUESTS_PER_CYCLE = 10
MAX_FILE_WRITES_PER_CYCLE = 5
CYCLE_DURATION_SECONDS = 3600  # 1 hour

# Baseline gating requirements
REQUIRE_CLEAN_GIT = True      # Must have clean working tree
REQUIRE_REASON_ARG = True        # Must provide --reason
REQUIRE_MANUAL_ACK = True      # Must type "I UNDERSTAND" manually


# ============================================================================
# SECURITY LAYER CLASS
# ============================================================================

class SecurityLayer:
    """
    Couche de sécurité DSM v2 (Sharding Memory)

    Public API:
        - verify_integrity() -> Dict[file, status]
        - check_baseline_gate(reason: str, manual_ack: bool) -> Tuple[bool, str]
        - update_baseline(reason: str, force: bool = False) -> None
        - audit_action(action_type: str, details: Dict) -> None
        - get_cycle_stats() -> Dict
        - reset_cycle() -> None
        - self_check() -> Dict
    """

    def __init__(self, workspace_dir: Path = None):
        self.workspace_dir = workspace_dir or Path.cwd()
        self.security_dir = self.workspace_dir / SECURITY_DIR
        self.security_dir.mkdir(parents=True, exist_ok=True)

        self.cycle_stats = {
            "api_requests": 0,
            "file_writes": 0,
            "external_connections": 0,
            "started_at": datetime.now(timezone.utc).isoformat()
        }

        self.logger = logging.getLogger("dsm_security")

    # -------------------------------------------------------------------------
    # INTEGRITY VERIFICATION
    # -------------------------------------------------------------------------

    def compute_file_hash(self, filepath: Path) -> str:
        """Calcule le hash SHA256 d'un fichier"""
        if not filepath.exists():
            return None

        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def verify_integrity(self) -> Dict[str, Optional[bool]]:
        """
        Vérifie l'intégrité des fichiers critiques

        Returns:
            Dict mapping fichier -> status:
                - True: OK (hash correspond à la baseline)
                - False: MODIFIED (hash différent)
                - None: NEW (pas dans la baseline)
        """
        integrity_data = self._load_integrity_data()

        results = {}
        has_anomalies = False

        for filename in CRITICAL_FILES:
            filepath = self.workspace_dir / filename
            current_hash = self.compute_file_hash(filepath)

            if filepath.exists():
                # Vérifier si le hash a changé
                known_hash = integrity_data.get("files", {}).get(filename)

                if known_hash is None:
                    # Premier scan - pas de baseline
                    results[filename] = None
                    integrity_data.setdefault("files", {})[filename] = current_hash
                    self.logger.info(f"[baseline] NEW: {filename}")
                else:
                    results[filename] = (current_hash == known_hash)
                    if current_hash != known_hash:
                        has_anomalies = True
                        self.logger.warning(f"[integrity] MODIFIED: {filename}")
                        self._audit_event("file_modified", {
                            "file": filename,
                            "old_hash": known_hash[:16],
                            "new_hash": current_hash[:16]
                        })
            else:
                results[filename] = None
                self.logger.warning(f"[integrity] MISSING: {filename}")

        self._save_integrity_data(integrity_data)

        # Git status check (warning only, not blocking)
        git_status = self._check_git_status()

        return {
            "files": results,
            "has_anomalies": has_anomalies,
            "git_status": git_status,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    # -------------------------------------------------------------------------
    # BASELINE GATING
    # -------------------------------------------------------------------------

    def check_baseline_gate(self, reason: str = None, manual_ack: str = None, force: bool = False) -> Tuple[bool, str]:
        """
        Vérifie les conditions pour mettre à jour la baseline

        Args:
            reason: Raison de la mise à jour (--reason)
            manual_ack: Confirmation manuelle ("I UNDERSTAND")
            force: Forcé la mise à jour (--force flag)

        Returns:
            Tuple[allowed: bool, message: str]
        """
        # Si force=True, autoriser si acknowledgment fourni
        if force:
            if manual_ack != "I UNDERSTAND":
                return False, "❌ Forced update requires acknowledgment: \"I UNDERSTAND\""
            return True, "⚠️ Forced update approved (double ack required)"

        checks = []

        # Check 1: Clean git tree
        if REQUIRE_CLEAN_GIT:
            git_status = self._check_git_status()
            if git_status:
                error_files = [f for f, status in git_status.items() if status != "clean"]
                if error_files:
                    checks.append(f"❌ Git working tree is dirty:")
                    for f in error_files[:5]:  # Max 5 files shown
                        checks.append(f"   • {f} ({git_status[f]})")
                    if len(error_files) > 5:
                        checks.append(f"   ... and {len(error_files) - 5} more")
            else:
                checks.append("❌ Git working tree is dirty (run `git status` to see changes)")

        # Check 2: Reason provided
        if REQUIRE_REASON_ARG and not reason:
            checks.append(f"❌ Missing --reason argument")
            checks.append(f"   Usage: python -m dsm security update-baseline --reason \"...\"")

        # Check 3: Manual acknowledgment
        if REQUIRE_MANUAL_ACK and not manual_ack:
            checks.append(f"❌ Manual acknowledgment required")
            checks.append(f"   Type 'I UNDERSTAND' to confirm you understand the security implications")

        if checks:
            return False, "\n".join(checks)
        else:
            return True, "✅ All baseline gate checks passed"

    def update_baseline(self, reason: str = None, force: bool = False, manual_ack: str = None) -> Tuple[bool, str]:
        """
        Met à jour la baseline d'intégrité

        Args:
            reason: Raison de la mise à jour (audit trail)
            force: Forcer la mise à jour (skip gates)

        Returns:
            Tuple[success: bool, message: str]
        """
        if not force:
            # Baseline gating
            allowed, message = self.check_baseline_gate(reason=reason, manual_ack=None)
            if not allowed:
                return False, message

        # === DOUBLE-ACK CHECK FOR FORCED UPDATES ===
        # Forcer une baseline update nécessite une confirmation renforcée
        # "I UNDERSTAND" doit apparaître DEUX FOIS (pas sensible à la casse)
        if force:
            if not manual_ack or manual_ack.upper() != "I UNDERSTAND I UNDERSTAND":
                return False, "❌ Refused: invalid acknowledgment for forced baseline update"

        # Compute new hashes
        integrity_data = self._load_integrity_data()

        updated_files = []
        for filename in CRITICAL_FILES:
            filepath = self.workspace_dir / filename
            if filepath.exists():
                current_hash = self.compute_file_hash(filepath)
                old_hash = integrity_data.get("files", {}).get(filename)

                if current_hash != old_hash:
                    integrity_data.setdefault("files", {})[filename] = current_hash
                    updated_files.append(filename)

        # Update metadata
        integrity_data["last_update"] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": reason or "forced",
            "updated_files": updated_files,
            "user": subprocess.getoutput("whoami").strip(),
            "forced": force
        }

        self._save_integrity_data(integrity_data, bypass_protection=True)

        message = f"✅ Baseline updated ({len(updated_files)} files)"
        if reason:
            message += f"\n   Reason: {reason}"
        if force:
            message += f"\n   ⚠️ Forced update (bypassed gates)"

        # Audit log enriched for forced updates
        self._audit_event("baseline_update", {
            "files_updated": updated_files,
            "reason": reason or "forced",
            "forced": force,
            "ack": bool(manual_ack),
            "user": subprocess.getoutput("whoami").strip(),
            "baseline_update_forced": force
        })

        return True, message

    # -------------------------------------------------------------------------
    # AUDIT & RATE LIMITING
    # -------------------------------------------------------------------------

    def audit_action(self, action_type: str, details: Dict):
        """
        Enregistre une action dans l'audit log

        Actions types:
            - api_request: Appel API externe
            - file_write: Écriture fichier
            - external_connection: Connexion externe
            - append_shard: Ajout entry dans shard
            - baseline_update: Mise à jour baseline
            - security_check: Vérification sécurité
        """
        self._audit_event(action_type, details)

        # Mise à jour des stats du cycle
        if action_type == "api_request":
            self.cycle_stats["api_requests"] += 1
        elif action_type in ["file_write", "append_shard"]:
            self.cycle_stats["file_writes"] += 1
        elif action_type == "external_connection":
            self.cycle_stats["external_connections"] += 1

        # Vérifier les limits
        if self.cycle_stats["api_requests"] > MAX_API_REQUESTS_PER_CYCLE:
            self.logger.warning(f"[rate_limit] API requests exceeded: {self.cycle_stats['api_requests']}/{MAX_API_REQUESTS_PER_CYCLE}")
            self._audit_event("rate_limit_exceeded", {"type": "api_requests", "count": self.cycle_stats["api_requests"]})

        if self.cycle_stats["file_writes"] > MAX_FILE_WRITES_PER_CYCLE:
            self.logger.warning(f"[rate_limit] File writes exceeded: {self.cycle_stats['file_writes']}/{MAX_FILE_WRITES_PER_CYCLE}")
            self._audit_event("rate_limit_exceeded", {"type": "file_writes", "count": self.cycle_stats["file_writes"]})

    def audit_external_action(self, event_type: str, details: Dict):
        """
        Public API for external integrations (e.g. security_listener) to log audit events.
        Delegates to _audit_event; does not update cycle stats.
        """
        self._audit_event(event_type, details)

    def check_rate_limit(self, action_type: str) -> Tuple[bool, str]:
        """
        Vérifie si une action est autorisée par le rate limit

        Args:
            action_type: Type d'action (api_request, file_write)

        Returns:
            Tuple[allowed: bool, message: str]
        """
        if action_type == "api_request":
            if self.cycle_stats["api_requests"] >= MAX_API_REQUESTS_PER_CYCLE:
                remaining = CYCLE_DURATION_SECONDS
                return False, f"❌ API rate limit exceeded ({MAX_API_REQUESTS_PER_CYCLE} per cycle, ~{remaining}s remaining)"
            return True, "OK"

        elif action_type in ["file_write", "append_shard"]:
            if self.cycle_stats["file_writes"] >= MAX_FILE_WRITES_PER_CYCLE:
                remaining = CYCLE_DURATION_SECONDS
                return False, f"❌ File write rate limit exceeded ({MAX_FILE_WRITES_PER_CYCLE} per cycle, ~{remaining}s remaining)"
            return True, "OK"

        return True, "OK"

    def get_cycle_stats(self) -> Dict:
        """Récupère les statistiques du cycle"""
        return self.cycle_stats.copy()

    def reset_cycle(self):
        """Réinitialise les statistiques du cycle"""
        self.logger.info(f"[cycle] Resetting cycle stats (API: {self.cycle_stats['api_requests']}, Files: {self.cycle_stats['file_writes']})")
        self.cycle_stats = {
            "api_requests": 0,
            "file_writes": 0,
            "external_connections": 0,
            "started_at": datetime.now(timezone.utc).isoformat()
        }

    # -------------------------------------------------------------------------
    # SELF-CHECK & REPORTING
    # -------------------------------------------------------------------------

    def self_check(self) -> Dict:
        """
        Effectue un auto-check complet du système DSM v2

        Returns:
            Dict avec le rapport de sécurité
        """
        # Vérification intégrité
        integrity_report = self.verify_integrity()

        # Vérification chain integrity
        chain_status = self._verify_chain_integrity()

        # Anomalies
        anomalies = []

        if integrity_report["has_anomalies"]:
            anomalies.append(f"Modified critical files: {sum(1 for s in integrity_report['files'].values() if s is False)}")

        if integrity_report["git_status"]:
            dirty_files = [f for f, s in integrity_report["git_status"].items() if s != "clean"]
            if dirty_files:
                anomalies.append(f"Git dirty state: {len(dirty_files)} files")

        if not chain_status["valid"]:
            anomalies.append(f"Integrity chain broken: {chain_status['error']}")

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "integrity": integrity_report,
            "chain_status": chain_status,
            "cycle_stats": self.get_cycle_stats(),
            "anomalies": anomalies,
            "security_status": "WARNING" if anomalies else "OK"
        }

    def generate_report(self) -> str:
        """Génère un rapport de sécurité lisible"""
        report = self.self_check()

        output = [
            "=" * 60,
            "🛡️ DSM v2 SECURITY REPORT",
            "=" * 60,
            f"Timestamp: {report['timestamp']}",
            f"Status: {report['security_status']}",
            "",
            "📁 Critical File Integrity (Kernel v2 + Integrity Data):",
            "-" * 60
        ]

        for file, status in report["integrity"]["files"].items():
            if status is None:
                status_str = "⚪ NEW"
            elif status:
                status_str = "✅ OK"
            else:
                status_str = "⚠️ MODIFIED"
            output.append(f"  {status_str} {file}")

        # Git status
        output.append("")
        output.append("🌿 Git Status (warning only):")
        output.append("-" * 40)
        if report["integrity"]["git_status"]:
            for file, status in report["integrity"]["git_status"].items():
                status_str = {"clean": "✅", "modified": "⚠️", "untracked": "🆕"}[status]
                output.append(f"  {status_str} {file} ({status})")
        else:
            output.append("  ✅ Clean working tree")

        # Chain integrity
        output.append("")
        output.append("⛓️ Integrity Chain (Shards):")
        output.append("-" * 40)
        chain = report["chain_status"]
        if chain["valid"]:
            output.append(f"  ✅ Valid ({chain['entries']} entries)")
        else:
            output.append(f"  ⚠️ BROKEN: {chain['error']}")

        # Cycle stats
        output.append("")
        output.append("📊 Cycle Stats:")
        output.append("-" * 40)
        stats = report["cycle_stats"]
        output.append(f"  API requests: {stats['api_requests']}/{MAX_API_REQUESTS_PER_CYCLE}")
        output.append(f"  File writes: {stats['file_writes']}/{MAX_FILE_WRITES_PER_CYCLE}")
        output.append(f"  External connections: {stats['external_connections']}")

        # Anomalies
        if report["anomalies"]:
            output.append("")
            output.append("⚠️ ANOMALIES DETECTED:")
            output.append("-" * 40)
            for anomaly in report["anomalies"]:
                output.append(f"  • {anomaly}")

        output.append("")
        output.append("=" * 60)

        return '\n'.join(output)

    # -------------------------------------------------------------------------
    # PROTECTED FILES GUARD (anti-rewrite protection)
    # -------------------------------------------------------------------------

    def _load_policy(self) -> Dict:
        """Charge la configuration de security policy"""
        policy_file = self.security_dir / "policy.json"
        if policy_file.exists():
            with open(policy_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            "protected_files": {
                "enabled": False,
                "allow_rewrite": False,
                "token_file": ".dsm_write_token",
                "protected_paths": PROTECTED_WRITE_FILES
            }
        }

    def check_protected_write(self, path: str) -> Tuple[bool, str]:
        """
        Vérifie si l'écriture sur un fichier est autorisée

        Args:
            path: Chemin relatif du fichier à écrire

        Returns:
            Tuple[allowed: bool, message: str]
        """
        import os

        policy = self._load_policy()
        config = policy.get("protected_files", {})

        # Si la protection n'est pas activée, OK
        if not config.get("enabled", False):
            return True, "Protection désactivée"

        # Normaliser le chemin
        normalized_path = str(Path(path).as_posix())

        # Vérifier si le chemin est dans la liste des fichiers protégés
        protected_paths = config.get("protected_paths", PROTECTED_WRITE_FILES)
        is_protected = any(
            normalized_path == str(Path(p).as_posix()) or
            normalized_path.endswith(str(Path(p).as_posix()))
            for p in protected_paths
        )

        if not is_protected:
            return True, "Fichier non protégé"

        # Migration: warn if old env var is set
        if os.getenv("DSM_SECURITY_REWRITE_OK", "").strip() == "1":
            self.logger.warning(
                "DSM_SECURITY_REWRITE_OK is deprecated and no longer bypasses protection. "
                "Use a file-based token: create .dsm_write_token in workspace (single-use, < 60s old)."
            )

        # Fichier protégé : vérifier l'override
        token_file_name = config.get("token_file", ".dsm_write_token")
        allow_rewrite = config.get("allow_rewrite", False)

        # Si allow_rewrite est true, OK
        if allow_rewrite:
            return True, "Réécriture autorisée par policy"

        # Check for file-based write token (replaces env var bypass)
        token_path = Path(self.workspace_dir) / token_file_name
        if token_path.exists():
            try:
                import time
                token_age = time.time() - token_path.stat().st_mtime
                if token_age < 60:  # Token must be < 60 seconds old
                    token_content = token_path.read_text().strip()
                    token_path.unlink()  # Single-use: delete after read
                    self._audit_event("protected_write_override", {
                        "path": normalized_path,
                        "token_used": True,
                        "token_age_seconds": round(token_age, 1),
                    })
                    return True, "Override via write token (single-use, expired after read)"
                else:
                    token_path.unlink()  # Expired token: clean up
                    self._audit_event("protected_write_token_expired", {
                        "path": normalized_path,
                        "token_age_seconds": round(token_age, 1),
                    })
            except OSError as e:
                self.logger.debug("write token cleanup failed: %s", e)

        # Refuser l'écriture
        self._audit_event("protected_write_blocked", {
            "path": normalized_path,
            "reason": "no_override",
            "token_file": token_file_name,
        })
        return False, f"❌ Écriture refusée sur fichier protégé : {path}\n   Créez un fichier {token_file_name} à la racine du workspace (contenu: nonce UUID, < 60s, usage unique)"

    def safe_write_protected(self, path: Path, content: str) -> bool:
        """
        Écriture sécurisée pour fichiers protégés

        Args:
            path: Chemin du fichier
            content: Contenu à écrire

        Returns:
            bool: True si écriture réussie
        """
        # Vérifier si le chemin est protégé
        allowed, message = self.check_protected_write(str(path))
        if not allowed:
            print(message)
            return False

        # Écriture atomique (avec fichier temporaire)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = path.with_suffix('.tmp')

        with open(tmp_file, 'w', encoding='utf-8') as f:
            f.write(content)

        tmp_file.replace(path)
        return True

    # -------------------------------------------------------------------------
    # INTERNAL HELPERS
    # -------------------------------------------------------------------------

    def _load_integrity_data(self) -> Dict:
        """Charge les données d'intégrité"""
        if INTEGRITY_FILE.exists():
            with open(INTEGRITY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"files": {}, "last_update": None}

    def _save_integrity_data(self, data: Dict, bypass_protection: bool = False):
        """
        Sauvegarde les données d'intégrité (atomic write, protected)

        Args:
            data: Données d'intégrité à sauvegarder
            bypass_protection: Si True, skip le check de fichier protégé (pour update_baseline autorisé)
        """
        self.security_dir.mkdir(parents=True, exist_ok=True)
        tmp_file = INTEGRITY_FILE.with_suffix('.tmp')

        with open(tmp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        # Vérifier si le fichier est protégé avant de remplacer (sauf si bypass)
        if not bypass_protection:
            allowed, message = self.check_protected_write(str(INTEGRITY_FILE))
            if not allowed:
                raise PermissionError(message)

        tmp_file.replace(INTEGRITY_FILE)

    def _audit_event(self, event_type: str, details: Dict):
        """Enregistre un événement dans l'audit log (JSONL append)"""
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "details": details
        }

        self.security_dir.mkdir(parents=True, exist_ok=True)

        audit_log = self.security_dir / "audit.jsonl"
        with open(audit_log, 'a', encoding='utf-8') as f:
            f.write(json.dumps(event) + '\n')

    def _check_git_status(self) -> Dict[str, str]:
        """
        Vérifie le statut git des fichiers critiques

        Returns:
            Dict mapping fichier -> statut (clean/modified/untracked)
        """
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=10
            )

            git_status = {}
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue

                status_code = line[:2]
                filepath = line[3:].strip()

                # Vérifier si c'est un fichier critique
                # BUG FIX: Comparer le chemin complet, pas juste le nom du fichier
                # CRITICAL_FILES contient "src/dsm/core/..." donc on doit matcher ça
                if any(cf in filepath for cf in CRITICAL_FILES):
                    # Extraire le nom du fichier pour la clé du dict
                    filename_key = Path(filepath).name
                    if 'M' in status_code:
                        git_status[filename_key] = "modified"
                    elif '??' in status_code:
                        git_status[filename_key] = "untracked"
                    else:
                        git_status[filename_key] = "clean"

            return git_status

        except Exception as e:
            self.logger.error(f"Git status check failed: {e}")
            return {}

    def _verify_chain_integrity(self) -> Dict:
        """
        Vérifie l'intégrité de la chaîne de hash (shards)

        Returns:
            Dict avec valid et error si invalide
        """
        try:
            chain_file = self.workspace_dir / "data/integrity/chain.json"
            if not chain_file.exists():
                return {"valid": True, "entries": 0, "error": None}

            with open(chain_file, 'r') as f:
                chain_data = json.load(f)

            entries = chain_data.get("entries", [])
            if not entries:
                return {"valid": True, "entries": 0, "error": None}

            # Vérifier la chaîne
            prev_hash = None
            for entry in entries:
                if entry.get("hash") is None:
                    return {"valid": False, "entries": len(entries), "error": "Entry missing hash"}

                if prev_hash and entry.get("prev_hash") != prev_hash:
                    return {"valid": False, "entries": len(entries), "error": f"Chain break at entry {entry.get('id')}"}

                prev_hash = entry.get("hash")

            return {"valid": True, "entries": len(entries), "error": None}

        except Exception as e:
            return {"valid": False, "entries": 0, "error": str(e)}


# ============================================================================
# CLI INTERFACE
# ============================================================================

def cmd_check(args):
    """Commande: python -m dsm security check"""
    security = SecurityLayer()
    report = security.generate_report()
    print(report)

    # Exit code basé sur le statut
    report_data = security.self_check()
    sys.exit(1 if report_data["anomalies"] else 0)


def cmd_update_baseline(args):
    """
    Commande: python -m dsm security update-baseline

    Baseline gating en place:
        - Git working tree must be clean
        --reason argument is required
        Manual "I UNDERSTAND" acknowledgment required

    Pour forcer: --force --manual-ack "I UNDERSTAND I UNDERSTAND"
    """
    security = SecurityLayer()

    reason = getattr(args, 'reason', None)
    manual_ack = getattr(args, 'manual_ack', None)
    force = getattr(args, 'force', False)

    # Mode force: skip les checks de gate, passage direct
    if force:
        if not reason:
            print("❌ --force requires --reason")
            return
        if not manual_ack:
            print("❌ --force requires --manual-ack \"I UNDERSTAND I UNDERSTAND\"")
            return
        success, message = security.update_baseline(reason=reason, force=force, manual_ack=manual_ack)
        if success:
            print(message)
            sys.exit(0)
        else:
            print(message)
            sys.exit(1)

    # Mode normal: check les gates
    if not reason or not manual_ack:
        print("⚠️ BASELINE UPDATE - Security Gate")
        print("=" * 40)
        print()

        # Check 1: Git status
        allowed, message = security.check_baseline_gate(reason="", manual_ack="")
        if not allowed:
            print(message)
            print()
            print("Requirements:")
            print("  1. Git working tree must be clean")
            print("  2. Provide --reason \"...\"")
            print("  3. Type \"I UNDERSTAND\" to confirm")
            print()
            return

        # Prompt pour reason
        if not reason:
            reason = input("Reason for baseline update: ").strip()
            if not reason:
                print("❌ Canceled: No reason provided")
                return

        # Prompt pour acknowledgment
        if not manual_ack:
            print()
            print("Security Implications:")
            print("  • Updating baseline acknowledges that YOU reviewed the changes")
            print("  • This is NOT automated security - it's YOUR responsibility")
            print("  • Malware could use this to hide tampering")
            print()
            ack = input("Type 'I UNDERSTAND' to confirm: ").strip().upper()
            if ack != "I UNDERSTAND":
                print("❌ Canceled: Incorrect acknowledgment")
                return

    # Exécuter la mise à jour
    success, message = security.update_baseline(reason=reason, force=force, manual_ack=manual_ack)

    if success:
        print(message)
        sys.exit(0)
    else:
        print(message)
        sys.exit(1)


def cmd_audit(args):
    """Commande: python -m dsm security audit"""
    security = SecurityLayer()

    AUDIT_LOG_FILE = security.security_dir / "audit.jsonl"
    if not AUDIT_LOG_FILE.exists():
        print("No audit log found")
        return

    limit = getattr(args, 'limit', 20)

    print("=" * 60)
    print("📋 DSM v2 AUDIT LOG")
    print("=" * 60)
    print()

    events = []
    with open(AUDIT_LOG_FILE, 'r') as f:
        for line in f:
            events.append(json.loads(line.strip()))

    # Afficher les N derniers événements
    for event in events[-limit:]:
        timestamp = event.get("timestamp", "")[:19]
        event_type = event.get("type", "unknown")
        details = event.get("details", {})

        print(f"[{timestamp}] {event_type}")
        for key, value in details.items():
            print(f"    {key}: {value}")
        print()

    print("=" * 60)


def cmd_self_check(args):
    """Commande: python -m dsm security self-check (JSON output)"""
    security = SecurityLayer()
    report = security.self_check()
    print(json.dumps(report, indent=2, ensure_ascii=False))


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="DSM v2 Security Layer")
    subparsers = parser.add_subparsers(dest='command', help='Security commands')

    # check command
    parser_check = subparsers.add_parser('check', help='Check security status')
    parser_check.set_defaults(func=cmd_check)

    # update-baseline command
    parser_update = subparsers.add_parser('update-baseline', help='Update security baseline (gated)')
    parser_update.add_argument('--reason', type=str, help='Reason for update (required)')
    parser_update.add_argument('--manual-ack', type=str, help='Manual acknowledgment "I UNDERSTAND"')
    parser_update.add_argument('--force', action='store_true', help='Force baseline update (skip gates, requires double I UNDERSTAND)')
    parser_update.set_defaults(func=cmd_update_baseline)

    # audit command
    parser_audit = subparsers.add_parser('audit', help='Show audit log')
    parser_audit.add_argument('--limit', type=int, default=20, help='Number of events to show')
    parser_audit.set_defaults(func=cmd_audit)

    # self-check command
    parser_self = subparsers.add_parser('self-check', help='Self-check (JSON output)')
    parser_self.set_defaults(func=cmd_self_check)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)
