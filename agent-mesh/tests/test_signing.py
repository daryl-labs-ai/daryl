"""Crypto tests for signing adapter."""
from __future__ import annotations

import json

import pytest

from agent_mesh.adapters.daryl_adapter.signing import (
    SigningAdapter,
    canonicalize_payload,
    compute_content_hash,
    generate_keypair,
    sign_bytes,
    sign_contribution,
    verify_bytes,
    verify_signed_contribution,
)


# ---------- canonicalize_payload ----------

def test_canonicalize_is_deterministic():
    a = {"b": 2, "a": 1}
    b = {"a": 1, "b": 2}
    assert canonicalize_payload(a) == canonicalize_payload(b)


def test_canonicalize_returns_bytes():
    assert isinstance(canonicalize_payload({"x": 1}), bytes)


def test_canonicalize_sorted_keys():
    out = canonicalize_payload({"z": 1, "a": 2}).decode()
    assert out.index('"a"') < out.index('"z"')


def test_canonicalize_no_spaces():
    out = canonicalize_payload({"a": 1, "b": 2}).decode()
    assert ", " not in out
    assert ": " not in out


def test_canonicalize_unicode():
    """Unicode strings are escaped (ensure_ascii=True per ADR-0002)."""
    result = canonicalize_payload({"name": "ünïcódé"})
    # ensure_ascii=True: non-ASCII chars are \uXXXX escaped
    assert b"\\u00fc" in result  # ü
    assert b"\\u00e9" in result  # é
    # Should NOT contain raw UTF-8 bytes anymore
    assert "ünïcódé".encode("utf-8") not in result


def test_canonicalize_nested():
    a = {"outer": {"b": 2, "a": 1}}
    b = {"outer": {"a": 1, "b": 2}}
    assert canonicalize_payload(a) == canonicalize_payload(b)


def test_canonicalize_empty():
    assert canonicalize_payload({}) == b"{}"


def test_canonicalize_list_values():
    assert canonicalize_payload({"l": [1, 2, 3]}) == b'{"l":[1,2,3]}'


# ---------- compute_content_hash ----------

def test_content_hash_prefix():
    h = compute_content_hash({"a": 1})
    assert h.startswith("v1:")


def test_content_hash_dict_deterministic():
    assert compute_content_hash({"a": 1, "b": 2}) == compute_content_hash({"b": 2, "a": 1})


def test_content_hash_dict_matches_canonical():
    """compute_content_hash output equals dsm_primitives.hash_canonical."""
    from dsm_primitives import hash_canonical
    payload = {"foo": "bar", "n": 42}
    expected = hash_canonical(payload)
    actual = compute_content_hash(payload)
    assert actual == expected
    assert actual.startswith("v1:")
    assert len(actual) == 67


def test_content_hash_different_inputs_differ():
    assert compute_content_hash({"a": 1}) != compute_content_hash({"a": 2})


def test_content_hash_hex_length():
    h = compute_content_hash({"x": 1})
    # "v1:" prefix (3 chars) + 64 hex chars = 67
    assert len(h) == 67


def test_compute_content_hash_rejects_non_dict():
    """Per ADR-0002 strict schema, only dict is accepted."""
    with pytest.raises(TypeError):
        compute_content_hash("a string")
    with pytest.raises(TypeError):
        compute_content_hash(b"bytes")
    with pytest.raises(TypeError):
        compute_content_hash(123)
    with pytest.raises(TypeError):
        compute_content_hash(None)


# ---------- generate_keypair ----------

def test_generate_keypair_returns_tuple():
    sk, pk = generate_keypair()
    assert isinstance(sk, str) and isinstance(pk, str)


def test_generate_keypair_distinct_pairs():
    sk1, pk1 = generate_keypair()
    sk2, pk2 = generate_keypair()
    assert sk1 != sk2
    assert pk1 != pk2


def test_generate_keypair_sk_not_pk():
    sk, pk = generate_keypair()
    assert sk != pk


def test_generate_keypair_base64_decodable():
    import base64
    sk, pk = generate_keypair()
    assert len(base64.b64decode(sk)) == 32
    assert len(base64.b64decode(pk)) == 32


# ---------- sign/verify_bytes ----------

def test_sign_verify_roundtrip():
    sk, pk = generate_keypair()
    data = b"message"
    sig = sign_bytes(data, sk)
    assert verify_bytes(data, sig, pk) is True


def test_sign_verify_empty_message():
    sk, pk = generate_keypair()
    sig = sign_bytes(b"", sk)
    assert verify_bytes(b"", sig, pk) is True


def test_verify_tampered_message_fails():
    sk, pk = generate_keypair()
    sig = sign_bytes(b"original", sk)
    assert verify_bytes(b"tampered", sig, pk) is False


def test_verify_wrong_key_fails():
    sk1, _ = generate_keypair()
    _, pk2 = generate_keypair()
    sig = sign_bytes(b"msg", sk1)
    assert verify_bytes(b"msg", sig, pk2) is False


def test_verify_invalid_signature_returns_false_not_raise():
    _, pk = generate_keypair()
    # garbage signature
    assert verify_bytes(b"m", "AAAA", pk) is False


def test_verify_invalid_key_returns_false_not_raise():
    sk, _ = generate_keypair()
    sig = sign_bytes(b"m", sk)
    assert verify_bytes(b"m", sig, "not-valid-base64!") is False


def test_sign_deterministic_for_same_input():
    sk, pk = generate_keypair()
    # Ed25519 is deterministic
    s1 = sign_bytes(b"msg", sk)
    s2 = sign_bytes(b"msg", sk)
    assert s1 == s2


def test_different_messages_different_signatures():
    sk, _ = generate_keypair()
    assert sign_bytes(b"a", sk) != sign_bytes(b"b", sk)


# ---------- sign_contribution / verify_signed_contribution ----------

def test_sign_contribution_roundtrip():
    sk, pk = generate_keypair()
    signed = sign_contribution(
        private_key_b64=sk,
        agent_id="a1",
        key_id="k1",
        mission_id="m1",
        task_id="t1",
        contribution_id="c1",
        contribution_type="task_result",
        content_hash="sha256:abc",
        created_at="2026-04-14T00:00:00Z",
    )
    assert verify_signed_contribution(signed, pk).valid is True


def test_signed_contribution_tampered_agent_id_fails():
    sk, pk = generate_keypair()
    signed = sign_contribution(sk, "a1", "k1", "m1", "t1", "c1", "task_result", "sha256:abc", "t0")
    signed.agent_id = "a2"
    assert verify_signed_contribution(signed, pk).valid is False


def test_signed_contribution_tampered_hash_fails():
    sk, pk = generate_keypair()
    signed = sign_contribution(sk, "a1", "k1", "m1", "t1", "c1", "task_result", "sha256:abc", "t0")
    signed.content_hash = "sha256:xyz"
    assert verify_signed_contribution(signed, pk).valid is False


def test_signed_contribution_wrong_key_fails():
    sk1, _ = generate_keypair()
    _, pk2 = generate_keypair()
    signed = sign_contribution(sk1, "a1", "k1", "m1", "t1", "c1", "task_result", "sha256:abc", "t0")
    assert verify_signed_contribution(signed, pk2).valid is False


def test_signed_contribution_reason_none_on_valid():
    sk, pk = generate_keypair()
    signed = sign_contribution(sk, "a1", "k1", "m1", "t1", "c1", "task_result", "sha256:abc", "t0")
    r = verify_signed_contribution(signed, pk)
    assert r.valid is True
    assert r.reason is None


def test_signed_contribution_reason_set_on_invalid():
    sk, pk = generate_keypair()
    signed = sign_contribution(sk, "a1", "k1", "m1", "t1", "c1", "task_result", "sha256:abc", "t0")
    signed.signature = "AAAA"
    r = verify_signed_contribution(signed, pk)
    assert r.valid is False
    assert r.reason == "signature_invalid"


# ---------- SigningAdapter ----------

def test_adapter_register_and_verify():
    sk, pk = generate_keypair()
    adapter = SigningAdapter()
    reg = adapter.register_agent_key("a1", pk)
    assert reg.agent_id == "a1"
    assert reg.key_id.startswith("key_")

    payload = {"x": 1, "y": 2}
    sig = sign_bytes(canonicalize_payload(payload), sk)
    assert adapter.verify_contribution("a1", payload, sig).valid is True


def test_adapter_register_duplicate_raises():
    _, pk = generate_keypair()
    adapter = SigningAdapter()
    adapter.register_agent_key("a1", pk)
    with pytest.raises(ValueError):
        adapter.register_agent_key("a1", pk)


def test_adapter_unknown_agent_returns_unknown():
    adapter = SigningAdapter()
    r = adapter.verify_contribution("ghost", {"a": 1}, "AAAA")
    assert r.valid is False
    assert r.reason == "agent_unknown"


def test_adapter_wrong_signature_invalid():
    sk, pk = generate_keypair()
    adapter = SigningAdapter()
    adapter.register_agent_key("a1", pk)
    # signed the wrong payload
    sig = sign_bytes(canonicalize_payload({"z": 1}), sk)
    r = adapter.verify_contribution("a1", {"z": 2}, sig)
    assert r.valid is False
    assert r.reason == "signature_invalid"


def test_adapter_rotate_key_changes_verification():
    sk1, pk1 = generate_keypair()
    sk2, pk2 = generate_keypair()
    adapter = SigningAdapter()
    adapter.register_agent_key("a1", pk1)
    rot = adapter.rotate_key("a1", pk2)
    assert rot.old_key_id != rot.new_key_id

    # signature from old key should now fail
    sig = sign_bytes(canonicalize_payload({"m": 1}), sk1)
    assert adapter.verify_contribution("a1", {"m": 1}, sig).valid is False

    # new key works
    sig2 = sign_bytes(canonicalize_payload({"m": 1}), sk2)
    assert adapter.verify_contribution("a1", {"m": 1}, sig2).valid is True


def test_adapter_rotate_unknown_raises():
    adapter = SigningAdapter()
    with pytest.raises(ValueError):
        adapter.rotate_key("nope", "pk")


def test_adapter_key_id_stable_for_same_pk():
    _, pk = generate_keypair()
    a1 = SigningAdapter()
    a2 = SigningAdapter()
    r1 = a1.register_agent_key("x", pk)
    r2 = a2.register_agent_key("y", pk)
    assert r1.key_id == r2.key_id


def test_adapter_key_id_differs_for_diff_pk():
    _, pk1 = generate_keypair()
    _, pk2 = generate_keypair()
    a = SigningAdapter()
    r1 = a.register_agent_key("x", pk1)
    r2 = a.register_agent_key("y", pk2)
    assert r1.key_id != r2.key_id


def test_adapter_stores_public_key():
    _, pk = generate_keypair()
    a = SigningAdapter()
    a.register_agent_key("a1", pk)
    assert a._keys["a1"] == pk


def test_adapter_stores_key_id():
    _, pk = generate_keypair()
    a = SigningAdapter()
    a.register_agent_key("a1", pk)
    assert a._key_ids["a1"].startswith("key_")


def test_canonical_ignores_key_order_roundtrip():
    sk, pk = generate_keypair()
    adapter = SigningAdapter()
    adapter.register_agent_key("a1", pk)
    payload1 = {"a": 1, "b": 2, "c": 3}
    sig = sign_bytes(canonicalize_payload(payload1), sk)
    payload2 = {"c": 3, "a": 1, "b": 2}
    assert adapter.verify_contribution("a1", payload2, sig).valid is True
