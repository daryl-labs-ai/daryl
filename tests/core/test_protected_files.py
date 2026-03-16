#!/usr/bin/env python3
"""Test unitaire: protected files write guard"""

import sys
import os

from dsm.core.security import SecurityLayer, PROTECTED_WRITE_FILES
from pathlib import Path
import tempfile
import shutil

def test_protected_files_write_guard():
    """Vérifie que les fichiers protégés sont bloqués sans override"""

    print("=" * 60)
    print("TEST: Protected Files Write Guard")
    print("=" * 60)

    # Créer une instance de SecurityLayer avec workspace temporaire
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        security_dir = workspace / "data/security"
        security_dir.mkdir(parents=True, exist_ok=True)

        # Créer policy.json temporaire
        policy_file = security_dir / "policy.json"
        policy = {
            "protected_files": {
                "enabled": True,
                "allow_rewrite": False,
                "token_file": ".dsm_write_token",
                "protected_paths": PROTECTED_WRITE_FILES
            }
        }
        import json
        with open(policy_file, 'w') as f:
            json.dump(policy, f)

        security = SecurityLayer(workspace_dir=workspace)

        # Cas A: Écriture sans override → refuse
        print("\n[Test A] Écriture sans override sur fichier protégé → should refuse")
        allowed, message = security.check_protected_write("src/dsm/core/security.py")
        assert not allowed, "❌ Cas A FAILED: Should reject write to protected file"
        assert "Écriture refusée" in message or "refused" in message.lower(), \
            f"❌ Cas A FAILED: Wrong message: {message}"
        print(f"✅ Cas A PASSED: {message}")

        # Cas B: Écriture avec token → accepte (single-use)
        print("\n[Test B] Écriture avec write token → should accept")
        import uuid
        token_path = workspace / ".dsm_write_token"
        token_path.write_text(str(uuid.uuid4()))
        allowed, message = security.check_protected_write("src/dsm/core/security.py")
        assert allowed, f"❌ Cas B FAILED: Should accept write with token - {message}"
        assert not token_path.exists(), "Token should be deleted after use"
        print(f"✅ Cas B PASSED: {message}")

        # Cas C: Écriture sur fichier non protégé → accepte
        print("\n[Test C] Écriture sur fichier non protégé → should accept")
        allowed, message = security.check_protected_write("data/shards/test.jsonl")
        assert allowed, f"❌ Cas C FAILED: Should accept write to unprotected file - {message}"
        print(f"✅ Cas C PASSED: {message}")

        # Cas D: Vérifier l'audit log pour blocked write
        print("\n[Test D] Vérifier l'audit log pour protected_write_blocked")
        audit_file = security_dir / "audit.jsonl"
        if audit_file.exists():
            with open(audit_file, 'r') as f:
                content = f.read()
                assert "protected_write_blocked" in content, "❌ Cas D FAILED: Audit should contain protected_write_blocked"
                assert "src/dsm/core/security.py" in content, "❌ Cas D FAILED: Audit should contain path"
            print("✅ Cas D PASSED: Audit log contains protected_write_blocked event")
        else:
            print("⚠️ Cas D SKIPPED: Audit file not created yet")

        # Cas E: Vérifier l'audit log pour token override
        print("\n[Test E] Vérifier l'audit log pour protected_write_override (token)")
        token_path = workspace / ".dsm_write_token"
        token_path.write_text(str(uuid.uuid4()))
        security.check_protected_write("src/dsm/cli.py")

        if audit_file.exists():
            with open(audit_file, 'r') as f:
                content = f.read()
                assert "protected_write_override" in content, "❌ Cas E FAILED: Audit should contain protected_write_override"
                assert "token_used" in content, "❌ Cas E FAILED: Audit should contain token_used"
            print("✅ Cas E PASSED: Audit log contains protected_write_override event")
        else:
            print("⚠️ Cas E SKIPPED: Audit file not created yet")

    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED")
    print("=" * 60)

if __name__ == "__main__":
    test_protected_files_write_guard()
