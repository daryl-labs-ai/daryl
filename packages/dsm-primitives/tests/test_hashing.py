"""Tests for dsm_primitives.hashing module."""

import hashlib

import pytest

from dsm_primitives import canonical_json, hash_canonical, verify_hash
from dsm_primitives.hashing import _hash_v0, _hash_v1


def test_hash_canonical_returns_v1_prefix():
    h = hash_canonical({"a": 1})
    assert h.startswith("v1:")


def test_hash_canonical_hex_length():
    h = hash_canonical({"a": 1})
    # "v1:" + 64 hex chars = 67 chars
    assert len(h) == 67
    hex_part = h[3:]
    assert len(hex_part) == 64
    int(hex_part, 16)  # must be valid hex


def test_hash_canonical_deterministic():
    h1 = hash_canonical({"a": 1, "b": 2})
    h2 = hash_canonical({"b": 2, "a": 1})
    assert h1 == h2


def test_hash_canonical_empty_dict():
    expected = "v1:" + hashlib.sha256(b"{}").hexdigest()
    assert hash_canonical({}) == expected


def test_hash_v0_no_prefix():
    h = _hash_v0({"a": 1})
    assert ":" not in h
    assert len(h) == 64
    int(h, 16)


def test_hash_v0_matches_direct_sha256():
    d = {"a": 1}
    expected = hashlib.sha256(canonical_json(d)).hexdigest()
    assert _hash_v0(d) == expected


def test_verify_hash_v1_roundtrip():
    d = {"foo": "bar", "n": 42}
    h = hash_canonical(d)
    assert verify_hash(d, h) is True


def test_verify_hash_v0_roundtrip():
    d = {"foo": "bar"}
    h = _hash_v0(d)
    assert verify_hash(d, h) is True


def test_verify_hash_wrong_data():
    h = hash_canonical({"a": 1})
    assert verify_hash({"a": 2}, h) is False


def test_verify_hash_wrong_v0():
    h = _hash_v0({"a": 1})
    assert verify_hash({"a": 2}, h) is False


def test_verify_hash_rejects_unknown_prefix():
    # future version v2: or foreign sha256: must be rejected
    assert verify_hash({"a": 1}, "v2:abc") is False
    assert verify_hash({"a": 1}, "sha256:abc") is False
    assert verify_hash({"a": 1}, "blake3:abc") is False


def test_verify_hash_rejects_non_string():
    assert verify_hash({"a": 1}, 12345) is False
    assert verify_hash({"a": 1}, None) is False
    assert verify_hash({"a": 1}, b"bytes") is False


def test_verify_hash_empty_string():
    # Empty string: no prefix, no colon -> treated as v0 with empty hex -> False
    assert verify_hash({"a": 1}, "") is False


def test_nfc_vs_non_nfc_produce_different_hashes():
    # Adversarial: "é" (U+00E9, NFC) vs "e\u0301" (U+0065+U+0301, NFD)
    # documents that caller MUST normalize (ADR-0002)
    h_nfc = hash_canonical({"s": "caf\u00e9"})
    h_nfd = hash_canonical({"s": "cafe\u0301"})
    assert h_nfc != h_nfd
