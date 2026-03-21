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


# --- A→E Pillar enums ---


class IdentityRegistryStatus(str, Enum):
    """Status for identity registry operations (Module A)."""
    REGISTERED = "REGISTERED"
    REVOKED = "REVOKED"
    NOT_FOUND = "NOT_FOUND"
    DUPLICATE = "DUPLICATE"


class SovereigntyStatus(str, Enum):
    """Status for sovereignty enforcement (Module B)."""
    ALLOWED = "ALLOWED"
    DENIED = "DENIED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    NO_POLICY = "NO_POLICY"


class OrchestratorStatus(str, Enum):
    """Status for orchestrator admission decisions (Module C)."""
    ADMITTED = "ADMITTED"
    REJECTED = "REJECTED"
    CACHED = "CACHED"


class CollectiveStatus(str, Enum):
    """Status for collective sync operations (Module D)."""
    PUSHED = "PUSHED"
    PULLED = "PULLED"
    RECONCILED = "RECONCILED"
    REJECTED = "REJECTED"


class LifecycleStatus(str, Enum):
    """Status for shard lifecycle transitions (Module E)."""
    ACTIVE = "ACTIVE"
    DRAINING = "DRAINING"
    SEALED = "SEALED"
    ARCHIVED = "ARCHIVED"
    TRANSITION_DENIED = "TRANSITION_DENIED"
