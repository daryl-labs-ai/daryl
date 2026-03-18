"""Verify all DSM timestamps use valid ISO 8601 format (no double-offset)."""

import re

import pytest

VALID_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
INVALID_DOUBLE = re.compile(r"\+00:00Z")


def test_timestamp_format_valid():
    """Z-terminated timestamps must not contain +00:00."""
    from datetime import datetime, timezone

    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    assert VALID_Z.match(ts), f"Bad format: {ts}"
    assert not INVALID_DOUBLE.search(ts)


def test_timestamp_double_offset_detected():
    """Catch the exact bug: .isoformat() + 'Z' on aware datetime."""
    from datetime import datetime, timezone

    bad = datetime.now(timezone.utc).isoformat() + "Z"
    assert INVALID_DOUBLE.search(bad), "Should detect double-offset"


def test_seal_timestamp_format():
    """seal.py must use the correct pattern."""
    import inspect

    from dsm import seal

    source = inspect.getsource(seal)
    assert '.isoformat() + "Z"' not in source
    assert ".isoformat() + 'Z'" not in source


def test_witness_timestamp_format():
    """witness.py must use the correct pattern."""
    import inspect

    from dsm import witness

    source = inspect.getsource(witness)
    assert '.isoformat() + "Z"' not in source
    assert ".isoformat() + 'Z'" not in source


def test_signing_timestamp_format():
    """signing.py must use the correct pattern."""
    import inspect

    from dsm import signing

    source = inspect.getsource(signing)
    assert '.isoformat() + "Z"' not in source
    assert ".isoformat() + 'Z'" not in source


def test_anchor_timestamp_format():
    """anchor.py must use the correct pattern."""
    import inspect

    from dsm import anchor

    source = inspect.getsource(anchor)
    assert '.isoformat() + "Z"' not in source
    assert ".isoformat() + 'Z'" not in source


def test_exchange_timestamp_format():
    """exchange.py must use the correct pattern."""
    import inspect

    from dsm import exchange

    source = inspect.getsource(exchange)
    assert '.isoformat() + "Z"' not in source
    assert ".isoformat() + 'Z'" not in source
