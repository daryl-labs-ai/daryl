"""
Shard Families — cross-cutting classification utility.

Classifies shards into 5 families based on naming convention.
Pure functions, no state, no I/O, no kernel change.

Used by:
- B (Sovereignty) — policy-by-family
- D (Collective)  — read-by-family
- E (Lifecycle)   — retention-by-family
"""


class ShardFamily:
    """Shard family constants."""
    AGENT      = "agent"
    REGISTRY   = "registry"
    AUDIT      = "audit"
    COLLECTIVE = "collective"
    INFRA      = "infra"

    ALL = frozenset({"agent", "registry", "audit", "collective", "infra"})


# Naming convention → family mapping (explicit shards)
_FAMILY_MAP = {
    "sessions":              ShardFamily.AGENT,
    "identity":              ShardFamily.AGENT,
    "identity_registry":     ShardFamily.REGISTRY,
    "sovereignty_policies":  ShardFamily.REGISTRY,
    "lifecycle_registry":    ShardFamily.REGISTRY,
    "orchestrator_audit":    ShardFamily.AUDIT,
    "sync_log":              ShardFamily.INFRA,
    "receipts":              ShardFamily.INFRA,
}

_COLLECTIVE_PREFIX = "collective_"
_LANE_PREFIX = "collective_lane_"


def classify_shard(shard_id: str) -> str:
    """Classify a shard by family. Pure function, O(1).

    Returns the family string for a given shard_id.
    Unknown shards default to 'agent' (private).
    """
    if shard_id in _FAMILY_MAP:
        return _FAMILY_MAP[shard_id]
    if shard_id.startswith(_LANE_PREFIX):
        return ShardFamily.COLLECTIVE
    if shard_id.startswith(_COLLECTIVE_PREFIX):
        return ShardFamily.COLLECTIVE
    return ShardFamily.AGENT


def list_shards_by_family(storage, family: str) -> list:
    """List all shard IDs belonging to a family.

    Args:
        storage: DSM Storage instance (must have list_shards())
        family: One of ShardFamily constants

    Returns:
        List of shard_id strings matching the family.
    """
    return [
        s.shard_id
        for s in storage.list_shards()
        if classify_shard(s.shard_id) == family
    ]


# Default retention rules per family (used by Module E — Lifecycle)
FAMILY_RETENTION = {
    ShardFamily.AGENT:      {"max_age_days": 365,  "max_entries": 100_000},
    ShardFamily.REGISTRY:   {"max_age_days": None,  "max_entries": None},
    ShardFamily.AUDIT:      {"max_age_days": None,  "max_entries": None},
    ShardFamily.COLLECTIVE: {"max_age_days": 90,   "max_entries": 50_000},
    ShardFamily.INFRA:      {"max_age_days": 30,   "max_entries": 10_000},
}
