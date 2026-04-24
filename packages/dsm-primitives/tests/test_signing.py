"""Tests for dsm_primitives.signing module."""

import os

import pytest
from nacl.signing import SigningKey

from dsm_primitives import sign, verify_signature


@pytest.fixture
def keypair():
    """Generate a test keypair."""
    seed = os.urandom(32)
    signer = SigningKey(seed)
    return {
        "private": bytes(seed),
        "public": bytes(signer.verify_key),
    }


def test_sign_produces_64_byte_signature(keypair):
    sig = sign(b"message", keypair["private"])
    assert len(sig) == 64


def test_sign_verify_roundtrip(keypair):
    msg = b"hello world"
    sig = sign(msg, keypair["private"])
    assert verify_signature(msg, sig, keypair["public"]) is True


def test_verify_rejects_wrong_message(keypair):
    sig = sign(b"message", keypair["private"])
    assert verify_signature(b"different", sig, keypair["public"]) is False


def test_verify_rejects_wrong_signature(keypair):
    fake_sig = b"\x00" * 64
    assert verify_signature(b"msg", fake_sig, keypair["public"]) is False


def test_verify_rejects_wrong_key(keypair):
    sig = sign(b"msg", keypair["private"])
    other = bytes(SigningKey(os.urandom(32)).verify_key)
    assert verify_signature(b"msg", sig, other) is False


def test_sign_rejects_wrong_key_length():
    with pytest.raises(ValueError):
        sign(b"msg", b"\x00" * 16)


def test_verify_rejects_wrong_public_key_length():
    assert verify_signature(b"msg", b"\x00" * 64, b"\x00" * 16) is False


def test_verify_rejects_wrong_signature_length(keypair):
    assert verify_signature(b"msg", b"\x00" * 32, keypair["public"]) is False
