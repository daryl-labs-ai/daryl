"""HexaShard Adapter test support."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "hexashard_adapter_fixtures"
if str(FIXTURES) not in sys.path:
    sys.path.insert(0, str(FIXTURES))


@pytest.fixture(scope="session", autouse=True)
def _core_frozen():
    """Adapter work never mutates Core — asserted before and after the suite."""
    from hexashard_adapter.core_lock import assert_core_unmodified

    assert_core_unmodified()
    yield
    assert_core_unmodified()
