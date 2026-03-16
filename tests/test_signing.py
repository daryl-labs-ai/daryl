"""Tests for P9 — Entry Signing (AgentSigning, ed25519)."""

import tempfile
from pathlib import Path

import pytest

pytest.importorskip("nacl", reason="PyNaCl required for signing tests")

from dsm.signing import (
    AgentSigning,
    load_public_key,
    import_public_key,
)


@pytest.fixture
def keys_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


def test_generate_keypair_creates_files(keys_dir):
    """Generate creates .seed and .pub files in keys_dir."""
    sign = AgentSigning(keys_dir, "alice")
    result = sign.generate_keypair()
    assert result["created"] is True
    assert result["public_key"]
    assert len(result["public_key"]) == 64
    assert (Path(keys_dir) / "alice.seed").exists()
    assert (Path(keys_dir) / "alice.pub").exists()


def test_generate_keypair_idempotent(keys_dir):
    """Second call with force=False returns existing key."""
    sign = AgentSigning(keys_dir, "bob")
    r1 = sign.generate_keypair()
    r2 = sign.generate_keypair(force=False)
    assert r1["created"] is True
    assert r2["created"] is False
    assert r1["public_key"] == r2["public_key"]


def test_sign_entry_returns_valid_signature(keys_dir):
    """Signature is 128-char hex (64 bytes)."""
    sign = AgentSigning(keys_dir, "alice")
    sign.generate_keypair()
    sig = sign.sign_entry("abc123def456")
    assert len(sig) == 128
    assert all(c in "0123456789abcdef" for c in sig)


def test_verify_signature_valid(keys_dir):
    """verify_signature returns valid=True for correct key."""
    sign = AgentSigning(keys_dir, "alice")
    sign.generate_keypair()
    data_hash = "abc123"
    sig = sign.sign_entry(data_hash)
    pub = sign.get_public_key()
    result = sign.verify_signature(data_hash, sig, pub)
    assert result["valid"] is True


def test_verify_signature_wrong_key(keys_dir):
    """Returns valid=False with different public key."""
    sign = AgentSigning(keys_dir, "alice")
    sign.generate_keypair()
    sig = sign.sign_entry("abc123")
    wrong_pub = "0" * 64
    result = sign.verify_signature("abc123", sig, wrong_pub)
    assert result["valid"] is False


def test_verify_signature_tampered_hash(keys_dir):
    """Returns valid=False if hash is modified."""
    sign = AgentSigning(keys_dir, "alice")
    sign.generate_keypair()
    sig = sign.sign_entry("abc123")
    pub = sign.get_public_key()
    result = sign.verify_signature("abc124", sig, pub)
    assert result["valid"] is False


def test_sign_and_verify_receipt(keys_dir):
    """sign_receipt + verify_signature roundtrip."""
    sign = AgentSigning(keys_dir, "bob")
    sign.generate_keypair()
    receipt_hash = "f" * 64
    sig = sign.sign_receipt(receipt_hash)
    pub = sign.get_public_key()
    result = sign.verify_signature(receipt_hash, sig, pub)
    assert result["valid"] is True


def test_import_public_key_for_remote_agent(keys_dir):
    """Import key, verify signature from remote agent."""
    alice = AgentSigning(keys_dir, "alice")
    alice.generate_keypair()
    alice_pub = alice.get_public_key()
    data_hash = "xyz789"
    alice_sig = alice.sign_entry(data_hash)

    bob_dir = keys_dir + "_bob"
    Path(bob_dir).mkdir(parents=True, exist_ok=True)
    import_public_key(bob_dir, "alice", alice_pub)
    loaded = load_public_key(bob_dir, "alice")
    assert loaded == alice_pub

    bob = AgentSigning(bob_dir, "bob")
    result = bob.verify_signature(data_hash, alice_sig, alice_pub)
    assert result["valid"] is True
