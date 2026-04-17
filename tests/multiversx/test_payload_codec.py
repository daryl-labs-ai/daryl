"""
Tests for the DSM01 payload codec.

Backlog: V0-02.

Acceptance criteria (from BACKLOG.md):
    - encode(x) → decode(encode(x)) round-trips for 100 random inputs
      including edge cases (unicode shard_id, max-length fields).
    - MAGIC is checked on decode.
    - Payload length is bounded by MAX_PAYLOAD_BYTES.
"""
from __future__ import annotations

import random
import struct
import uuid

import pytest

from dsm.multiversx.errors import PayloadError
from dsm.multiversx.payload import (
    LAST_HASH_BYTES,
    MAGIC,
    MAX_PAYLOAD_BYTES,
    MIN_PAYLOAD_BYTES,
    SHARD_ID_MAX_BYTES,
    DecodedPayload,
    decode_payload,
    encode_payload,
    is_dsm_anchor_payload,
)
from dsm.multiversx.schemas import AnchorIntent, EpochRegime


def _make_intent(
    *,
    shard_id: str = "sessions",
    last_hash_hex: str = "0x" + "ab" * 32,
    entry_nonce: int = 42,
    intent_id: uuid.UUID | None = None,
    epoch_regime: EpochRegime = "supernova",
) -> AnchorIntent:
    return AnchorIntent(
        intent_id=intent_id or uuid.UUID("00000000-0000-4000-8000-000000000001"),
        shard_id=shard_id,
        last_hash=last_hash_hex,
        entry_nonce=entry_nonce,
        epoch_regime=epoch_regime,
    )


class TestEncodeDecodeRoundTrip:
    """Round-trip property: decode(encode(intent)) preserves all fields."""

    def test_happy_path_ascii_shard_id(self) -> None:
        """Basic ASCII shard_id, standard 32-byte hash, small entry_nonce."""
        intent = _make_intent(shard_id="sessions", entry_nonce=7)
        decoded = decode_payload(encode_payload(intent))
        assert decoded.shard_id == "sessions"
        assert decoded.entry_nonce == 7
        assert decoded.intent_id == intent.intent_id
        assert decoded.as_hex_last_hash() == intent.last_hash

    def test_unicode_shard_id(self) -> None:
        """Shard id with multi-byte UTF-8 characters (e.g. emoji, CJK)."""
        shard_id = "日本語-🌸"  # 14 UTF-8 bytes, 5 characters
        intent = _make_intent(shard_id=shard_id)
        decoded = decode_payload(encode_payload(intent))
        assert decoded.shard_id == shard_id

    def test_max_length_shard_id(self) -> None:
        """Shard id exactly at SHARD_ID_MAX_BYTES (64 bytes)."""
        shard_id = "a" * SHARD_ID_MAX_BYTES
        intent = _make_intent(shard_id=shard_id)
        encoded = encode_payload(intent)
        assert len(encoded) == MAX_PAYLOAD_BYTES
        decoded = decode_payload(encoded)
        assert decoded.shard_id == shard_id

    def test_large_entry_nonce(self) -> None:
        """entry_nonce at 2**63 - 1 and at 2**64 - 1."""
        for nonce in (2**63 - 1, 2**64 - 1):
            intent = _make_intent(entry_nonce=nonce)
            decoded = decode_payload(encode_payload(intent))
            assert decoded.entry_nonce == nonce

    def test_random_fuzz_100_rounds(self) -> None:
        """100 random inputs; encode→decode must round-trip for all."""
        rng = random.Random(0xD5E01)
        for _ in range(100):
            shard_len = rng.randint(1, 20)
            shard_id = "".join(rng.choice("abcdef0123456789-_") for _ in range(shard_len))
            last_hash = "0x" + "".join(rng.choice("0123456789abcdef") for _ in range(64))
            nonce = rng.randrange(0, 2**64)
            intent = _make_intent(
                shard_id=shard_id,
                last_hash_hex=last_hash,
                entry_nonce=nonce,
                intent_id=uuid.UUID(int=rng.randrange(0, 2**128)),
            )
            decoded = decode_payload(encode_payload(intent))
            assert decoded.shard_id == shard_id
            assert decoded.entry_nonce == nonce
            assert decoded.intent_id == intent.intent_id
            assert decoded.as_hex_last_hash() == last_hash


class TestDecodeRejection:
    """Corrupted payloads must raise PayloadError, never silently pass."""

    def _valid(self) -> bytes:
        return encode_payload(_make_intent())

    def test_wrong_magic(self) -> None:
        payload = bytearray(self._valid())
        payload[0:5] = b"DSM02"
        with pytest.raises(PayloadError, match="magic"):
            decode_payload(bytes(payload))

    def test_too_short(self) -> None:
        short = b"DSM01" + b"\x00" * (MIN_PAYLOAD_BYTES - len(MAGIC) - 2)
        with pytest.raises(PayloadError, match="MIN_PAYLOAD_BYTES"):
            decode_payload(short)

    def test_too_long(self) -> None:
        too_long = self._valid() + b"\x00" * (MAX_PAYLOAD_BYTES + 10 - MIN_PAYLOAD_BYTES)
        with pytest.raises(PayloadError, match="MAX_PAYLOAD_BYTES"):
            decode_payload(too_long)

    def test_shard_id_len_zero(self) -> None:
        payload = bytearray(self._valid())
        payload[len(MAGIC)] = 0
        with pytest.raises(PayloadError, match="shard_id_len"):
            decode_payload(bytes(payload))

    def test_shard_id_len_exceeds_max(self) -> None:
        payload = bytearray(self._valid())
        payload[len(MAGIC)] = SHARD_ID_MAX_BYTES + 1
        with pytest.raises(PayloadError, match="shard_id_len"):
            decode_payload(bytes(payload))

    def test_shard_id_invalid_utf8(self) -> None:
        # Build a payload where the shard_id bytes are invalid UTF-8 (lone 0xFF).
        shard_id_len = 2
        bad_shard = b"\xff\xfe"
        last_hash = b"\xab" * LAST_HASH_BYTES
        nonce = struct.pack(">Q", 1)
        intent_id_bytes = b"\x00" * 16
        payload = (
            MAGIC + bytes([shard_id_len]) + bad_shard + last_hash + nonce + intent_id_bytes
        )
        with pytest.raises(PayloadError, match="UTF-8"):
            decode_payload(payload)

    def test_truncated_last_hash(self) -> None:
        """Declared shard_id_len extends past available bytes before last_hash fits."""
        valid = self._valid()
        # Truncate one byte from last_hash region.
        truncated = valid[:-1]
        with pytest.raises(PayloadError):
            decode_payload(truncated)

    def test_trailing_garbage(self) -> None:
        """Shift shard_id_len down by 1 so declared payload ends before actual length."""
        valid = bytearray(self._valid())
        # Shrink shard_id_len by 1 so "expected total" < actual length by 1.
        valid[len(MAGIC)] = valid[len(MAGIC)] - 1
        # Still above MIN_PAYLOAD_BYTES since original shard was > 1 byte.
        with pytest.raises(PayloadError, match="inconsistent"):
            decode_payload(bytes(valid))


class TestIsDsmAnchorPayload:
    """Cheap-check helper used by the audit CLI."""

    def test_returns_true_for_valid_payload(self) -> None:
        assert is_dsm_anchor_payload(encode_payload(_make_intent())) is True

    def test_returns_false_for_non_bytes(self) -> None:
        assert is_dsm_anchor_payload("not bytes") is False  # type: ignore[arg-type]
        assert is_dsm_anchor_payload(None) is False  # type: ignore[arg-type]

    def test_returns_false_for_short_payload(self) -> None:
        assert is_dsm_anchor_payload(b"DSM01") is False
        assert is_dsm_anchor_payload(b"\x00" * (MIN_PAYLOAD_BYTES - 1)) is False

    def test_returns_false_for_wrong_magic(self) -> None:
        # Build minimal-length bytes with wrong magic.
        garbage = b"DSM02" + b"\x01" + b"x" + b"\x00" * (MIN_PAYLOAD_BYTES - 7)
        assert is_dsm_anchor_payload(garbage) is False

    def test_returns_false_for_zero_shard_id_len(self) -> None:
        payload = bytearray(encode_payload(_make_intent()))
        payload[len(MAGIC)] = 0
        assert is_dsm_anchor_payload(bytes(payload)) is False

    def test_returns_false_for_oversized_shard_id_len(self) -> None:
        payload = bytearray(encode_payload(_make_intent()))
        payload[len(MAGIC)] = SHARD_ID_MAX_BYTES + 1
        assert is_dsm_anchor_payload(bytes(payload)) is False
