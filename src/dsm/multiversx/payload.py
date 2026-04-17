"""
Payload codec for the DSM01 anchor transaction data field.

Backlog: V0-02.

Payload format (bytes, big-endian):

    MAGIC(5) | shard_id_len(1) | shard_id(UTF-8, var) | last_hash(32) |
    entry_nonce(8) | intent_id(16)

    MAGIC           : b"DSM01"
    shard_id_len    : 1 unsigned byte, value ∈ [1, 64]
    shard_id        : UTF-8 bytes, length = shard_id_len
    last_hash       : 32 raw bytes (not hex)
    entry_nonce     : 8 unsigned bytes, big-endian
    intent_id       : 16 raw bytes of the UUIDv7

Total size bound: 5 + 1 + 64 + 32 + 8 + 16 = 126 bytes maximum.

See SPEC §3 for rationale.

Invariants:
    - encode(x) and decode(encode(x)) MUST round-trip for all valid inputs.
    - Any corruption of the payload bytes MUST be detected by decode() and
      MUST NOT produce a silently-wrong DecodedPayload. Corrupted bytes must
      raise PayloadError.
    - The MAGIC is fixed. Future format revisions MUST use a new magic
      (DSM02, etc.) and be accompanied by a version bump in the adapter.

Failure modes (all raise PayloadError):
    - Magic mismatch.
    - shard_id_len of 0, or > 64, or inconsistent with remaining bytes.
    - Total length outside expected range.
    - UTF-8 decode error on shard_id.

Test file: tests/multiversx/test_payload_codec.py
"""
from __future__ import annotations

import struct
import uuid
from dataclasses import dataclass

from dsm.multiversx.errors import PayloadError
from dsm.multiversx.schemas import AnchorIntent

MAGIC: bytes = b"DSM01"
"""Magic bytes identifying the payload format. 5 bytes."""

SHARD_ID_MAX_BYTES: int = 64
LAST_HASH_BYTES: int = 32
ENTRY_NONCE_BYTES: int = 8
INTENT_ID_BYTES: int = 16
MIN_PAYLOAD_BYTES: int = (
    len(MAGIC) + 1 + 1 + LAST_HASH_BYTES + ENTRY_NONCE_BYTES + INTENT_ID_BYTES
)
MAX_PAYLOAD_BYTES: int = (
    len(MAGIC)
    + 1
    + SHARD_ID_MAX_BYTES
    + LAST_HASH_BYTES
    + ENTRY_NONCE_BYTES
    + INTENT_ID_BYTES
)

# Absolute ceiling — a design guard, not a format detail. Even if the
# MultiversX data field allows more, DSM01 MUST stay within one unsigned
# byte's worth of length (<=255) so any downstream code that assumes a
# single-byte length prefix cannot be tricked. If a future DSM02 format
# requires more, it MUST use a new magic and bump this constant explicitly.
ABSOLUTE_DATA_FIELD_CEILING: int = 255
assert MAX_PAYLOAD_BYTES <= ABSOLUTE_DATA_FIELD_CEILING, (
    f"DSM01 payload bound {MAX_PAYLOAD_BYTES} exceeds the absolute "
    f"255-byte ceiling. A new magic is required before this is allowed."
)


@dataclass(frozen=True)
class DecodedPayload:
    """Decoded DSM01 payload.

    All fields match the AnchorIntent fields of the same name, except
    `last_hash` which is raw bytes here (vs 0x-prefixed hex in AnchorIntent).
    """

    shard_id: str
    last_hash: bytes
    entry_nonce: int
    intent_id: uuid.UUID

    def as_hex_last_hash(self) -> str:
        """Return last_hash as a 0x-prefixed lowercase hex string.

        Matches the representation used in AnchorIntent.last_hash.
        """
        return "0x" + self.last_hash.hex()


def encode_payload(intent: AnchorIntent) -> bytes:
    """Encode an AnchorIntent into DSM01 binary payload.

    Args:
        intent: The AnchorIntent whose fields drive the encoding.

    Returns:
        A bytes object of length in [MIN_PAYLOAD_BYTES, MAX_PAYLOAD_BYTES].

    Raises:
        PayloadError: If any field cannot be encoded into the fixed format
            (e.g. shard_id > 64 bytes when UTF-8 encoded, last_hash not
            exactly 32 bytes after hex-decode).

    Invariants:
        - len(encode_payload(intent)) ≤ MAX_PAYLOAD_BYTES.
        - decode_payload(encode_payload(intent)) preserves shard_id,
          last_hash, entry_nonce, intent_id exactly.

    Test file: tests/multiversx/test_payload_codec.py
    """
    shard_id_bytes = intent.shard_id.encode("utf-8")
    if len(shard_id_bytes) == 0:
        raise PayloadError("shard_id is empty after UTF-8 encoding")
    if len(shard_id_bytes) > SHARD_ID_MAX_BYTES:
        raise PayloadError(
            f"shard_id UTF-8 length {len(shard_id_bytes)} exceeds "
            f"SHARD_ID_MAX_BYTES ({SHARD_ID_MAX_BYTES})"
        )

    last_hash_hex = intent.last_hash
    if last_hash_hex.startswith("0x") or last_hash_hex.startswith("0X"):
        last_hash_hex = last_hash_hex[2:]
    try:
        last_hash_bytes = bytes.fromhex(last_hash_hex)
    except ValueError as exc:
        raise PayloadError(f"last_hash is not valid hex: {exc}") from exc
    if len(last_hash_bytes) != LAST_HASH_BYTES:
        raise PayloadError(
            f"last_hash decoded to {len(last_hash_bytes)} bytes, "
            f"expected {LAST_HASH_BYTES}"
        )

    try:
        entry_nonce_bytes = struct.pack(">Q", intent.entry_nonce)
    except struct.error as exc:
        raise PayloadError(f"entry_nonce does not fit in unsigned 64 bits: {exc}") from exc

    intent_id_bytes = intent.intent_id.bytes
    if len(intent_id_bytes) != INTENT_ID_BYTES:
        raise PayloadError(
            f"intent_id.bytes is {len(intent_id_bytes)} bytes, expected {INTENT_ID_BYTES}"
        )

    result = (
        MAGIC
        + bytes([len(shard_id_bytes)])
        + shard_id_bytes
        + last_hash_bytes
        + entry_nonce_bytes
        + intent_id_bytes
    )
    if len(result) > ABSOLUTE_DATA_FIELD_CEILING:
        raise PayloadError(
            f"encoded payload {len(result)} exceeds ABSOLUTE_DATA_FIELD_CEILING "
            f"({ABSOLUTE_DATA_FIELD_CEILING}); a new magic is required"
        )
    return result


def decode_payload(data: bytes) -> DecodedPayload:
    """Decode DSM01 binary payload into a DecodedPayload.

    Args:
        data: Raw bytes read from a MultiversX transaction's data field.

    Returns:
        A DecodedPayload with all fields populated.

    Raises:
        PayloadError: If the magic is wrong, the length is inconsistent,
            the shard_id is not valid UTF-8, or any structural check fails.

    Invariants:
        - Pure function of `data`. No I/O, no globals read beyond constants.
        - Never returns a partially-populated DecodedPayload.

    Test file: tests/multiversx/test_payload_codec.py
    """
    if not isinstance(data, (bytes, bytearray)):
        raise PayloadError(f"expected bytes, got {type(data).__name__}")
    data = bytes(data)
    if len(data) < MIN_PAYLOAD_BYTES:
        raise PayloadError(
            f"payload length {len(data)} is below MIN_PAYLOAD_BYTES ({MIN_PAYLOAD_BYTES})"
        )
    if len(data) > MAX_PAYLOAD_BYTES:
        raise PayloadError(
            f"payload length {len(data)} exceeds MAX_PAYLOAD_BYTES ({MAX_PAYLOAD_BYTES})"
        )
    if data[: len(MAGIC)] != MAGIC:
        raise PayloadError(f"magic mismatch: expected {MAGIC!r}, got {data[: len(MAGIC)]!r}")

    shard_id_len = data[len(MAGIC)]
    if shard_id_len == 0 or shard_id_len > SHARD_ID_MAX_BYTES:
        raise PayloadError(
            f"shard_id_len {shard_id_len} out of range [1, {SHARD_ID_MAX_BYTES}]"
        )

    expected_total = (
        len(MAGIC) + 1 + shard_id_len + LAST_HASH_BYTES + ENTRY_NONCE_BYTES + INTENT_ID_BYTES
    )
    if len(data) != expected_total:
        raise PayloadError(
            f"payload length {len(data)} inconsistent with shard_id_len={shard_id_len} "
            f"(expected {expected_total})"
        )

    cursor = len(MAGIC) + 1
    shard_id_raw = data[cursor : cursor + shard_id_len]
    cursor += shard_id_len
    try:
        shard_id = shard_id_raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PayloadError(f"shard_id is not valid UTF-8: {exc}") from exc

    last_hash = data[cursor : cursor + LAST_HASH_BYTES]
    cursor += LAST_HASH_BYTES
    try:
        (entry_nonce,) = struct.unpack(">Q", data[cursor : cursor + ENTRY_NONCE_BYTES])
    except struct.error as exc:
        raise PayloadError(f"entry_nonce unpack failed: {exc}") from exc
    cursor += ENTRY_NONCE_BYTES

    intent_id_raw = data[cursor : cursor + INTENT_ID_BYTES]
    cursor += INTENT_ID_BYTES
    if cursor != len(data):
        raise PayloadError(
            f"trailing garbage after intent_id: {len(data) - cursor} extra byte(s)"
        )
    try:
        intent_id = uuid.UUID(bytes=intent_id_raw)
    except ValueError as exc:
        raise PayloadError(f"intent_id bytes are not a valid UUID: {exc}") from exc

    return DecodedPayload(
        shard_id=shard_id,
        last_hash=last_hash,
        entry_nonce=entry_nonce,
        intent_id=intent_id,
    )


def is_dsm_anchor_payload(data: bytes) -> bool:
    """Cheap check: does this tx data field look like a DSM01 anchor?

    Used by the audit CLI to filter transactions without full decode.
    Non-raising; returns False for any data that does not start with MAGIC.

    Args:
        data: Raw bytes from a transaction data field.

    Returns:
        True iff data starts with MAGIC and has plausible length.

    Test file: tests/multiversx/test_payload_codec.py
    """
    if not isinstance(data, (bytes, bytearray)):
        return False
    if len(data) < MIN_PAYLOAD_BYTES or len(data) > MAX_PAYLOAD_BYTES:
        return False
    if bytes(data[: len(MAGIC)]) != MAGIC:
        return False
    shard_id_len = data[len(MAGIC)]
    return 1 <= shard_id_len <= SHARD_ID_MAX_BYTES
