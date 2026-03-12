#!/usr/bin/env python3
"""Test unitaire: force requires double I UNDERSTAND acknowledgment"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from dsm_v2.core.security import SecurityLayer

def test_force_requires_double_ack():
    """Vérifie que --force nécessite le double acknowledgment 'I UNDERSTAND I UNDERSTAND'"""

    security = SecurityLayer()

    print("=" * 60)
    print("TEST: Force requires double I UNDERSTAND acknowledgment")
    print("=" * 60)

    # Cas A: --force sans manual_ack → refuse
    print("\n[Test A] --force without manual_ack → should refuse")
    success, message = security.update_baseline(
        reason="Test A: force without manual_ack",
        force=True,
        manual_ack=None
    )
    assert not success, "❌ Cas A FAILED: Should reject force without manual_ack"
    assert "invalid acknowledgment" in message.lower() or "requires" in message.lower(), \
        f"❌ Cas A FAILED: Wrong message: {message}"
    print(f"✅ Cas A PASSED: {message}")

    # Cas B: manual_ack="I UNDERSTAND" → refuse (double requis)
    print("\n[Test B] --force with 'I UNDERSTAND' → should refuse")
    success, message = security.update_baseline(
        reason="Test B: force with single I UNDERSTAND",
        force=True,
        manual_ack="I UNDERSTAND"
    )
    assert not success, "❌ Cas B FAILED: Should reject force with single I UNDERSTAND"
    assert "invalid acknowledgment" in message.lower() or "refused" in message.lower(), \
        f"❌ Cas B FAILED: Wrong message: {message}"
    print(f"✅ Cas B PASSED: {message}")

    # Cas C: manual_ack="I UNDERSTAND I UNDERSTAND" → accepte
    print("\n[Test C] --force with 'I UNDERSTAND I UNDERSTAND' → should accept")
    success, message = security.update_baseline(
        reason="Test C: force with double I UNDERSTAND",
        force=True,
        manual_ack="I UNDERSTAND I UNDERSTAND"
    )
    assert success, f"❌ Cas C FAILED: Should accept force with double I UNDERSTAND - {message}"
    print(f"✅ Cas C PASSED: {message}")

    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED")
    print("=" * 60)

if __name__ == "__main__":
    test_force_requires_double_ack()
