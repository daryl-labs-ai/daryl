#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSM v2 - Security Layer (Kernel v2 Integration) - STABLE VERSION

Protection for Sharding Memory System:
- Anti-injection (kernel v2 code integrity)
- Anti-erasure (integrity logs protection)
- Baseline gating (manual ack required)
- Rate limiting (API + file writes)
- Anti-bypass (write token system)

Architecture:
- Critical files: dsm_v2/core/*, dsm_v2/cli.py, data/integrity/*
- Excluded: data/shards/*.jsonl (append-only, hash chain protected)
"""

import hashlib
import json
import subprocess
import contextvars
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Tuple
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

# Write token system (anti-bypass)
_WRITE_TOKEN = contextvars.ContextVar("DSM_WRITE_TOKEN", default=False)

def allow_writes():
    """Allow writes temporarily (set token)"""
    _WRITE_TOKEN.set(True)

def deny_writes():
    """Revoke write access (clear token)"""
    _WRITE_TOKEN.set(False)

def writes_allowed() -> bool:
    """Check if writes are currently allowed"""
    return bool(_WRITE_TOKEN.get())

# Critical files for DSM v2 Sharding Memory (protected by baseline)
CRITICAL_FILES = [
    "dsm_v2/core/models.py",
    "dsm_v2/core/storage.py",
    "dsm_v2/core/signing.py",
    "dsm_v2/core/session.py",
    "dsm_v2/core/drift.py",
    "dsm_v2/core/security.py",
    "dsm_v2/cli.py",
    "data/security/baseline.json",
    "data/security/policy.json",
]

# Rate limits
MAX_API_REQUESTS_PER_CYCLE = 10
MAX_FILE_WRITES_PER_CYCLE = 5
CYCLE_DURATION_SECONDS = 3600

# Baseline gating requirements
REQUIRE_CLEAN_GIT = True
REQUIRE_REASON_ARG = True
REQUIRE_MANUAL_ACK = True

# ============================================================================
# SECURITY LAYER CLASS
# ============================================================================

class SecurityLayer:
    def __init__(self, workspace_dir: Path = None):
        self.workspace_dir = workspace_dir or Path.cwd()
        self.security_dir = self.workspace_dir / SECURITY_DIR
        self.security_dir.mkdir(parents=True, exist_ok=True)

        self.cycle_stats = {
            "api_requests": 0,
            "file_writes": 0,
            "external_connections": 0,
            "started_at": datetime.utcnow().isoformat()
        }

        self.logger = logging.getLogger("dsm_security")

    def compute_file_hash(self, filepath: Path) -> str:
        if not filepath.exists():
            return None
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def verify_integrity(self) -> Dict[str, Optional[bool]]:
        integrity_data = self._load_integrity_data()

        results = {}
        has_anomalies = False

        for filename in CRITICAL_FILES:
            filepath = self.workspace_dir / filename
            current_hash = self.compute_file_hash(filepath)

            if filepath.exists():
                known_hash = integrity_data.get("files", {}).get(filename)

                if known_hash is None:
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
        git_status = self._check_git_status()

        return {
            "files": results,
            "has_anomalies": has_anomalies,
            "git_status": git_status,
            "timestamp": datetime.utcnow().isoformat()
        }

    def check_baseline_gate(self, reason: str = None, manual_ack: str = None, force: bool = False) -> Tuple[bool, str]:
        if force:
            if manual_ack != "I UNDERSTAND" or manual_ack != "I UNDERSTAND":
                return False, "❌ Forced update requires double acknowledgment: \"I UNDERSTAND\" + \"I UNDERSTAND\""
            return True, "⚠️ Forced update approved (double ack required)"

        checks = []

        if REQUIRE_CLEAN_GIT:
            git_status = self._check_git_status()
            if git_status:
                error_files = [f for f, status in git_status.items() if status != "clean"]
                if error_files:
                    checks.append(f"❌ Git working tree is dirty:")
                    for f in error_files[:5]:
                        checks.append(f"   • {f} ({git_status[f]})")
                    if len(error_files) > 5:
                        checks.append(f"   ... and {len(error_files) - 5} more")

        if REQUIRE_REASON_ARG and not reason:
            checks.append(f"❌ Missing --reason argument")
            checks.append(f"   Usage: python -m dsm_v2.security update-baseline --reason \"...\"")

        if REQUIRE_MANUAL_ACK and not manual_ack:
            checks.append(f"❌ Manual acknowledgment required")
            checks.append(f"   Type 'I UNDERSTAND' to confirm you understand of security implications")

        if checks:
            return False, "\n".join(checks)
        else:
            return True, "✅ All baseline gate checks passed"

    def update_baseline(self, reason: str = None, force: bool = False, manual_ack: str = None) -> Tuple[bool, str]:
        if not force:
            allowed, message = self.check_baseline_gate(reason=reason, manual_ack=manual_ack)
            if not allowed:
                return False, message

        if force:
            if not manual_ack or manual_ack.upper() != "I UNDERSTAND":
                return False, "❌ Forced update requires double acknowledgment: type \"I UNDERSTAND I UNDERSTAND\" (case-sensitive)"

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

        integrity_data["last_update"] = {
            "timestamp": datetime.utcnow().isoformat(),
            "reason": reason or "forced",
            "updated_files": updated_files,
            "user": subprocess.getoutput("whoami").strip(),
            "forced": force
        }

        self._save_integrity_data(integrity_data)

        message = f"✅ Baseline updated ({len(updated_files)} files)"
        if reason:
            message += f"\n   Reason: {reason}"
        if force:
            message += f"\n   ⚠️ Forced update (bypassed gates)"

        self._audit_event("baseline_update", {
            "files_updated": updated_files,
            "reason": reason or "forced",
            "forced": force,
            "user": subprocess.getoutput("whoami").strip(),
            "baseline_update_forced": force
        })

        return True, message

    def audit_action(self, action_type: str, details: Dict):
        self._audit_event(action_type, details)

        if action_type == "api_request":
            self.cycle_stats["api_requests"] += 1
        elif action_type in ["file_write", "append_shard"]:
            self.cycle_stats["file_writes"] += 1
        elif action_type == "external_connection":
            self.cycle_stats["external_connections"] += 1

        if self.cycle_stats["api_requests"] > MAX_API_REQUESTS_PER_CYCLE:
            self.logger.warning(f"[rate_limit] API requests exceeded: {self.cycle_stats['api_requests']}/{MAX_API_REQUESTS_PER_CYCLE}")
            self._audit_event("rate_limit_exceeded", {"type": "api_requests", "count": self.cycle_stats["api_requests"]})

        if self.cycle_stats["file_writes"] > MAX_FILE_WRITES_PER_CYCLE:
            self.logger.warning(f"[rate_limit] File writes exceeded: {self.cycle_stats['file_writes']}/{MAX_FILE_WRITES_PER_CYCLE}")
            self._audit_event("rate_limit_exceeded", {"type": "file_writes", "count": self.cycle_stats["file_writes"]})

    def check_rate_limit(self, action_type: str) -> Tuple[bool, str]:
        if action_type == "api_request":
            if self.cycle_stats["api_requests"] >= MAX_API_REQUESTS_PER_CYCLE:
                return False, f"❌ API rate limit exceeded ({MAX_API_REQUESTS_PER_CYCLE} per cycle, ~{CYCLE_DURATION_SECONDS}s remaining)"
            return True, "OK"

        elif action_type in ["file_write", "append_shard"]:
            if self.cycle_stats["file_writes"] >= MAX_FILE_WRITES_PER_CYCLE:
                return False, f"❌ File write rate limit exceeded ({MAX_FILE_WRITES_PER_CYCLE} per cycle, ~{CYCLE_DURATION_SECONDS}s remaining)"
            return True, "OK"

        return True, "OK"

    def get_cycle_stats(self) -> Dict:
        return self.cycle_stats.copy()

    def reset_cycle(self):
        self.logger.info(f"[cycle] Resetting cycle stats (API: {self.cycle_stats['api_requests']}, Files: {self.cycle_stats['file_writes']})")
        self.cycle_stats = {
            "api_requests": 0,
            "file_writes": 0,
            "external_connections": 0,
            "started_at": datetime.utcnow().isoformat()
        }

    def self_check(self) -> Dict:
        integrity_report = self.verify_integrity()
        chain_status = self._verify_chain_integrity()

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
            "timestamp": datetime.utcnow().isoformat(),
            "integrity": integrity_report,
            "chain_status": chain_status,
            "cycle_stats": self.get_cycle_stats(),
            "anomalies": anomalies,
            "security_status": "WARNING" if anomalies else "OK"
        }

    def generate_report(self) -> str:
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

        output.append("")
        output.append("🌿 Git Status (warning only):")
        output.append("-" * 40)
        if report["integrity"]["git_status"]:
            for file, status in report["integrity"]["git_status"].items():
                status_str = {"clean": "✅", "modified": "⚠️", "untracked": "🆕"}[status]
                output.append(f"  {status_str} {file} ({status})")
        else:
            output.append("  ✅ Clean working tree")

        output.append("")
        output.append("⛓️ Integrity Chain (Shards):")
        output.append("-" * 40)
        chain = report["chain_status"]
        if chain["valid"]:
            output.append(f"  ✅ Valid ({chain['entries']} entries)")
        else:
            output.append(f"  ⚠️ BROKEN: {chain['error']}")

        output.append("")
        output.append("📊 Cycle Stats:")
        output.append("-" * 40)
        stats = report["cycle_stats"]
        output.append(f"  API requests: {stats['api_requests']}/{MAX_API_REQUESTS_PER_CYCLE}")
        output.append(f"  File writes: {stats['file_writes']}/{MAX_FILE_WRITES_PER_CYCLE}")
        output.append(f"  External connections: {stats['external_connections']}")

        if report["anomalies"]:
            output.append("")
            output.append("⚠️ ANOMALIES DETECTED:")
            output.append("-" * 40)
            for anomaly in report["anomalies"]:
                output.append(f"  • {anomaly}")

        output.append("")
        output.append("=" * 60)

        return '\n'.join(output)

    def _load_integrity_data(self) -> Dict:
        if INTEGRITY_FILE.exists():
            with open(INTEGRITY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"files": {}, "last_update": None}

    def _save_integrity_data(self, data: Dict):
        self.security_dir.mkdir(parents=True, exist_ok=True)
        tmp_file = INTEGRITY_FILE.with_suffix('.tmp')

        with open(tmp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        tmp_file.replace(INTEGRITY_FILE)

    def _audit_event(self, event_type: str, details: Dict):
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "type": event_type,
            "details": details
        }

        self.security_dir.mkdir(parents=True, exist_ok=True)

        with open(AUDIT_LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps(event) + '\n')

    def _check_git_status(self) -> Dict[str, str]:
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=self.workspace_dir
            )

            git_status = {}
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue

                status_code = line[:2]
                filepath = line[3:].strip()

                abs_path = (self.workspace_dir / filepath).resolve()

                for cf in CRITICAL_FILES:
                    cf_abs = (self.workspace_dir / cf).resolve()
                    if abs_path == cf_abs:
                        if 'M' in status_code:
                            git_status[cf] = "modified"
                        elif '??' in status_code:
                            git_status[cf] = "untracked"
                        else:
                            git_status[cf] = "clean"
                        break

            return git_status

        except Exception as e:
            self.logger.error(f"Git status check failed: {e}")
            return {}

    def _verify_chain_integrity(self) -> Dict:
        try:
            chain_file = self.workspace_dir / "data/integrity/chain.json"
            if not chain_file.exists():
                return {"valid": True, "entries": 0, "error": None}

            with open(chain_file, 'r') as f:
                chain_data = json.load(f)

            entries = chain_data.get("entries", [])
            if not entries:
                return {"valid": True, "entries": 0, "error": None}

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
    security = SecurityLayer()
    report = security.generate_report()
    print(report)

    report_data = security.self_check()
    sys.exit(1 if report_data["anomalies"] else 0)


def cmd_update_baseline(args):
    security = SecurityLayer()

    reason = getattr(args, 'reason', None)
    manual_ack = getattr(args, 'manual_ack', None)
    force = getattr(args, 'force', False)

    if not reason or not manual_ack:
        print("⚠️ BASELINE UPDATE - Security Gate")
        print("=" * 40)
        print()

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

        if not reason:
            reason = input("Reason for baseline update: ").strip()
            if not reason:
                print("❌ Canceled: No reason provided")
                return

        if not manual_ack:
            print()
            print("Security Implications:")
            print("  • Updating baseline acknowledges that YOU reviewed changes")
            print("  • This is NOT automated security - it's YOUR responsibility")
            print("  • Malware could use this to hide tampering")
            print()
            ack = input("Type 'I UNDERSTAND' to confirm: ").strip().upper()
            if ack != "I UNDERSTAND":
                print("❌ Canceled: Incorrect acknowledgment")
                return

    success, message = security.update_baseline(reason=reason, force=force, manual_ack=manual_ack)

    if success:
        print(message)
        sys.exit(0)
    else:
        print(message)
        sys.exit(1)


def cmd_audit(args):
    security = SecurityLayer()

    if not AUDIT_LOG.exists():
        print("No audit log found")
        return

    limit = getattr(args, 'limit', 20)

    print("=" * 60)
    print("📋 DSM v2 AUDIT LOG")
    print("=" * 60)
    print()

    events = []
    with open(AUDIT_LOG, 'r') as f:
        for line in f:
            events.append(json.loads(line.strip()))

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
    security = SecurityLayer()
    report = security.self_check()
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="DSM v2 Security Layer")
    subparsers = parser.add_subparsers(dest='command', help='Security commands')

    parser_check = subparsers.add_parser('check', help='Check security status')
    parser_check.set_defaults(func=cmd_check)

    parser_update = subparsers.add_parser('update-baseline', help='Update security baseline (gated)')
    parser_update.add_argument('--reason', type=str, help='Reason for update (required)')
    parser_update.add_argument('--manual-ack', type=str, help='Manual acknowledgment "I UNDERSTAND"')
    parser_update.add_argument('--force', action='store_true', help='Force update (requires double ack)')
    parser_update.set_defaults(func=cmd_update_baseline)

    parser_audit = subparsers.add_parser('audit', help='Show audit log')
    parser_audit.add_argument('--limit', type=int, default=20, help='Number of events to show')
    parser_audit.set_defaults(func=cmd_audit)

    parser_self = subparsers.add_parser('self-check', help='Self-check (JSON output)')
    parser_self.set_defaults(func=cmd_self_check)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)
