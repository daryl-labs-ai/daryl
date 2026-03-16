"""DSM status enums — single source of truth for all status strings."""

from enum import Enum


class VerifyStatus(str, Enum):
    """Status for hash chain verification (verify.py)."""
    OK = "OK"
    TAMPERED = "TAMPERED"
    CHAIN_BROKEN = "CHAIN_BROKEN"


class SealStatus(str, Enum):
    """Status for seal verification (seal.py)."""
    VALID = "VALID"
    HASH_MISMATCH = "HASH_MISMATCH"
    NOT_SEALED = "NOT_SEALED"


class ReceiptStatus(str, Enum):
    """Status for receipt verification (exchange.py)."""
    INTACT = "INTACT"
    TAMPERED = "TAMPERED"
    SIGNATURE_INVALID = "SIGNATURE_INVALID"


class WitnessStatus(str, Enum):
    """Status for witness verification (witness.py)."""
    OK = "OK"
    DIVERGED = "DIVERGED"
    NO_WITNESS = "NO_WITNESS"


class StorageReceiptStatus(str, Enum):
    """Status for receipt-against-storage verification."""
    CONFIRMED = "CONFIRMED"
    ENTRY_MISSING = "ENTRY_MISSING"
    HASH_MISMATCH = "HASH_MISMATCH"
    SHARD_MISSING = "SHARD_MISSING"


class SealStorageStatus(str, Enum):
    """Status for seal-against-storage verification."""
    MATCHES = "MATCHES"
    DIVERGED = "DIVERGED"
    SHARD_GONE = "SHARD_GONE"
    NOT_SEALED = "NOT_SEALED"
