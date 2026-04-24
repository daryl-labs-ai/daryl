"""Canonical DSM Entry fixture shared between daryl-dsm and agent-mesh
for cross-package parity tests.

Per ADR-0002, any change to this fixture is a breaking schema change
requiring a new hash version.
"""

CANONICAL_ENTRY_V1 = {
    "session_id": "s-test-001",
    "source": "agent-test",
    "timestamp": "2026-01-01T00:00:00Z",
    "metadata": {"action_name": "test_action", "success": True},
    "content": {"msg": "canonical test entry"},
    "prev_hash": None,
}
