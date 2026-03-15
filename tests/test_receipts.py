"""Tests for input receipt utilities."""

import hashlib
import json
from dsm.receipts import hash_input, make_receipt


def test_hash_input_string():
    result = hash_input("hello world")
    expected = hashlib.sha256(b"hello world").hexdigest()
    assert result == expected


def test_hash_input_bytes():
    data = b"\x00\x01\x02"
    result = hash_input(data)
    expected = hashlib.sha256(data).hexdigest()
    assert result == expected


def test_hash_input_dict():
    data = {"b": 2, "a": 1}
    result = hash_input(data)
    # dict is sorted before hashing
    expected = hashlib.sha256(
        json.dumps({"a": 1, "b": 2}, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    assert result == expected


def test_hash_input_deterministic():
    """Same input always produces same hash."""
    assert hash_input("test") == hash_input("test")
    assert hash_input({"a": 1}) == hash_input({"a": 1})


def test_hash_input_different():
    """Different inputs produce different hashes."""
    assert hash_input("hello") != hash_input("world")


def test_make_receipt_string():
    receipt = make_receipt("some api response data here")
    assert "input_hash" in receipt
    assert "input_preview" in receipt
    assert len(receipt["input_hash"]) == 64  # SHA-256 hex
    assert receipt["input_preview"] == "some api response data here"


def test_make_receipt_long_string_truncated():
    long_text = "x" * 500
    receipt = make_receipt(long_text, preview_length=200)
    assert len(receipt["input_preview"]) == 200


def test_make_receipt_dict():
    data = {"temperature": 25, "city": "Paris"}
    receipt = make_receipt(data)
    assert len(receipt["input_hash"]) == 64
    assert "temperature" in receipt["input_preview"]


def test_make_receipt_bytes():
    data = b"binary response content"
    receipt = make_receipt(data)
    assert len(receipt["input_hash"]) == 64
    assert "binary response" in receipt["input_preview"]
