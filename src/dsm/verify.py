"""
DSM hash-chain verification.

Uses storage.segment_manager.iter_shard_events() for chronological order
and storage._entry_from_event_data() + _compute_canonical_entry_hash from core.
"""

from typing import Dict, List, Any

from .core.storage import Storage, _compute_canonical_entry_hash


def verify_shard(storage: Storage, shard_id: str) -> Dict[str, Any]:
    """
    Verify hash chain integrity for a single shard.

    Reads all entries in chronological order via iter_shard_events,
    recomputes canonical hash per entry, checks prev_hash chain.

    Returns:
        dict: shard_id, total_entries, verified, tampered, chain_breaks, status.
        status is "OK" | "TAMPERED" | "CHAIN_BROKEN".
    """
    entries_chrono: List[Any] = []
    for event_data in storage.segment_manager.iter_shard_events(shard_id):
        try:
            entry = storage._entry_from_event_data(event_data)
            entries_chrono.append(entry)
        except (KeyError, TypeError, ValueError):
            continue

    total = len(entries_chrono)
    verified = 0
    tampered = 0
    chain_breaks = 0
    prev_hash = None

    for entry in entries_chrono:
        chain_ok = (prev_hash is None and entry.prev_hash is None) or (
            prev_hash is not None and entry.prev_hash == prev_hash
        )
        if prev_hash is not None and not chain_ok:
            chain_breaks += 1

        if not entry.hash:
            tampered += 1
            hash_ok = False
        else:
            try:
                recomputed = _compute_canonical_entry_hash(entry, entry.prev_hash)
                hash_ok = recomputed == entry.hash
                if not hash_ok:
                    tampered += 1
            except Exception:
                tampered += 1
                hash_ok = False

        if chain_ok and hash_ok:
            verified += 1

        prev_hash = entry.hash if entry.hash else prev_hash

    if tampered > 0:
        status = "TAMPERED"
    elif chain_breaks > 0:
        status = "CHAIN_BROKEN"
    else:
        status = "OK"

    return {
        "shard_id": shard_id,
        "total_entries": total,
        "verified": verified,
        "tampered": tampered,
        "chain_breaks": chain_breaks,
        "status": status,
    }


def verify_all(storage: Storage) -> List[Dict[str, Any]]:
    """
    Verify hash chain for all shards returned by storage.list_shards().

    Returns:
        List of results from verify_shard() per shard.
    """
    shards = storage.list_shards()
    return [verify_shard(storage, s.shard_id) for s in shards]
