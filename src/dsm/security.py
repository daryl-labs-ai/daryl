#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSM v2 - Security Layer (facade)

This module delegates to the reference implementation in core.security.
The DSM kernel (core/security.py) is the single source of truth.

Root-only additions: allow_writes / deny_writes / writes_allowed (contextvars)
for optional write gating outside the kernel.
"""

import contextvars

# Re-export everything from the reference implementation (core)
from .core.security import (
    SecurityLayer,
    CRITICAL_FILES,
    PROTECTED_WRITE_FILES,
    SECURITY_DIR,
    INTEGRITY_FILE,
    AUDIT_LOG,
    BASELINE_LOCK_FILE,
    MAX_API_REQUESTS_PER_CYCLE,
    MAX_FILE_WRITES_PER_CYCLE,
    CYCLE_DURATION_SECONDS,
    REQUIRE_CLEAN_GIT,
    REQUIRE_REASON_ARG,
    REQUIRE_MANUAL_ACK,
    cmd_check,
    cmd_update_baseline,
    cmd_audit,
    cmd_self_check,
)

# Root-only: write token (optional gating, not in core)
_WRITE_TOKEN = contextvars.ContextVar("DSM_WRITE_TOKEN", default=False)


def allow_writes():
    """Allow writes temporarily (set token)."""
    _WRITE_TOKEN.set(True)


def deny_writes():
    """Revoke write access (clear token)."""
    _WRITE_TOKEN.set(False)


def writes_allowed() -> bool:
    """Check if writes are currently allowed."""
    return bool(_WRITE_TOKEN.get())


__all__ = [
    "SecurityLayer",
    "CRITICAL_FILES",
    "PROTECTED_WRITE_FILES",
    "SECURITY_DIR",
    "INTEGRITY_FILE",
    "AUDIT_LOG",
    "BASELINE_LOCK_FILE",
    "MAX_API_REQUESTS_PER_CYCLE",
    "MAX_FILE_WRITES_PER_CYCLE",
    "CYCLE_DURATION_SECONDS",
    "REQUIRE_CLEAN_GIT",
    "REQUIRE_REASON_ARG",
    "REQUIRE_MANUAL_ACK",
    "cmd_check",
    "cmd_update_baseline",
    "cmd_audit",
    "cmd_self_check",
    "allow_writes",
    "deny_writes",
    "writes_allowed",
]
