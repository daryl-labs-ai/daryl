# -*- coding: utf-8 -*-
"""
Minimal wall-clock profiler for RR internals.

Used by ADR 0001 Phase 7a.5 root-cause decomposition
(see docs/architecture/ADR_0001_PHASE_7A_5_ROOTCAUSE.md).

Design:
  - Off by default. Enabled by env var DSM_RR_PROFILE=1 at import time, or
    programmatically via set_enabled(True).
  - `Timed(section)` is a zero-allocation context manager when disabled
    (no timing call, no dict write).
  - Samples are stored in-process as a list of floats per section; callers
    own the snapshot / reset lifecycle.
  - No dependency beyond stdlib `os` and `time`.

Instrumentation is strictly section-level. Do NOT use Timed() inside tight
per-entry or per-record loops — that would alter what we are measuring.
"""

from __future__ import annotations

import os
import time
from typing import Dict, List


class _State:
    # Activated either from env at import time, or via set_enabled(True).
    enabled: bool = os.environ.get("DSM_RR_PROFILE", "0") == "1"
    samples: Dict[str, List[float]] = {}


def enabled() -> bool:
    """Return True iff profiling is currently active."""
    return _State.enabled


def set_enabled(value: bool) -> None:
    """Enable / disable profiling programmatically. Intended for test harnesses."""
    _State.enabled = bool(value)


def reset() -> None:
    """Clear all recorded samples. Idempotent. Safe to call when disabled."""
    _State.samples.clear()


def record(section: str, duration_s: float) -> None:
    """Append a duration (seconds) under a named section. No-op when disabled."""
    if not _State.enabled:
        return
    bucket = _State.samples.get(section)
    if bucket is None:
        bucket = []
        _State.samples[section] = bucket
    bucket.append(duration_s)


def snapshot() -> Dict[str, List[float]]:
    """Return a shallow copy of the recorded samples dict."""
    return {k: list(v) for k, v in _State.samples.items()}


class Timed:
    """
    Context manager that records a wall-clock duration under `section` when
    the profiler is enabled, and is a cheap no-op otherwise.

    Usage:
        with Timed("build:timeline_sort"):
            timeline_index.sort(...)

    Constraints:
      - Do NOT nest inside tight per-entry loops (e.g. one per record, one per
        dict insert). Profiler overhead would become comparable to the work.
      - Do use around section-level blocks: a sort pass, a file write, a
        top-level method boundary.
    """

    __slots__ = ("section", "_t0")

    def __init__(self, section: str) -> None:
        self.section = section
        self._t0 = 0.0

    def __enter__(self) -> "Timed":
        if _State.enabled:
            self._t0 = time.monotonic()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if _State.enabled:
            duration = time.monotonic() - self._t0
            bucket = _State.samples.get(self.section)
            if bucket is None:
                bucket = []
                _State.samples[self.section] = bucket
            bucket.append(duration)
        return False
