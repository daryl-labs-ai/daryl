"""
DSM hash-chain verification.

Uses storage.segment_manager.iter_shard_events() for chronological order
and storage._entry_from_event_data() + storage._build_canonical_entry
+ dsm_primitives.verify_hash for prefix-aware (v0/v1) hash routing.

C1 fix: the internal prev_hash chain only proves that whatever entries are
present form a valid sequence — it CANNOT detect deletion of a suffix (the
remaining prefix is still a valid chain). Completeness is therefore checked
against the pinned tip (integrity/{shard}_last_hash.json): the observed tip
hash and entry count are compared to the pinned values. A shard whose tail
is shorter than the pin has been truncated and is reported as TAMPERED. A
shard with no pin is reported as UNPINNED rather than a silent OK.
"""

import json
from typing import Dict, List, Any, Optional

from dsm_primitives import verify_hash

from .core.storage import Storage, _build_canonical_entry
from .status import VerifyStatus


def _read_pin(storage: Storage, shard_id: str) -> Optional[dict]:
    """Read the integrity pin ({shard}_last_hash.json), or None if absent/unreadable."""
    pin_file = storage.integrity_dir / f"{shard_id}_last_hash.json"
    if not pin_file.exists():
        return None
    try:
        with open(pin_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def verify_shard(storage: Storage, shard_id: str) -> Dict[str, Any]:
    """
    Verify hash chain integrity AND append-only completeness for a single shard.

    Reads all entries in chronological order via iter_shard_events, recomputes
    the canonical hash per entry, checks the prev_hash chain, then compares the
    observed tip/count against the pinned tip (C1).

    Returns the chain fields (total_entries, verified, tampered, chain_breaks,
    status) plus completeness fields:
        pin_status            "PINNED_OK" | "UNPINNED" | "TIP_MISMATCH" | "AHEAD_OF_PIN"
        expected_last_hash    pinned tip hash (None if unpinned)
        observed_last_hash    tip hash actually on disk
        expected_entry_count  pinned entry count (None if unknown)
        observed_entry_count  entry count actually on disk
        chain_tip_mismatch    bool
        entry_count_mismatch  bool
        truncation_detected   bool  (observed count < pinned count)
        mismatch_type         None | "TRUNCATION" | "COUNT_MISMATCH" | "TIP_MISMATCH"
        warnings              list[str]

    status is VerifyStatus.OK | VerifyStatus.TAMPERED | VerifyStatus.CHAIN_BROKEN.
    Truncation and tail tampering map to TAMPERED.
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
                canonical_entry = _build_canonical_entry(entry, entry.prev_hash)
                hash_ok = verify_hash(canonical_entry, entry.hash)
                if not hash_ok:
                    tampered += 1
            except Exception:
                tampered += 1
                hash_ok = False

        if chain_ok and hash_ok:
            verified += 1

        prev_hash = entry.hash if entry.hash else prev_hash

    # ----- C1: completeness check against the pinned tip -----
    observed_last_hash = entries_chrono[-1].hash if entries_chrono else None
    observed_entry_count = total
    warnings: List[str] = []

    pin = _read_pin(storage, shard_id)
    expected_last_hash = pin.get("last_hash") if pin else None
    expected_entry_count = pin.get("entry_count") if pin else None

    chain_tip_mismatch = False
    entry_count_mismatch = False
    truncation_detected = False
    mismatch_type: Optional[str] = None

    if not pin or not expected_last_hash:
        pin_status = "UNPINNED"
        warnings.append(
            "UNPINNED_SHARD: no integrity pin found; append-only completeness "
            "(truncation resistance) cannot be verified for this shard"
        )
    else:
        chain_tip_mismatch = observed_last_hash != expected_last_hash
        if expected_entry_count is not None:
            entry_count_mismatch = observed_entry_count != expected_entry_count

        if expected_entry_count is not None and observed_entry_count < expected_entry_count:
            # Entries lost relative to the pin → trailing truncation.
            truncation_detected = True
            mismatch_type = "TRUNCATION"
            pin_status = "TIP_MISMATCH"
        elif expected_entry_count is not None and observed_entry_count > expected_entry_count:
            # More on disk than pinned → crash window / pin lag; recoverable via
            # reconcile, not a loss. Surface it, but do not fail verification.
            pin_status = "AHEAD_OF_PIN"
            warnings.append(
                "AHEAD_OF_PIN: segment holds more entries than the pin; "
                "run reconcile_shard() to advance the pin"
            )
        elif chain_tip_mismatch:
            # Same (or unknown) count but a different tip → tail tampering.
            mismatch_type = "COUNT_MISMATCH" if entry_count_mismatch else "TIP_MISMATCH"
            pin_status = "TIP_MISMATCH"
        else:
            pin_status = "PINNED_OK"

    if tampered > 0:
        status = VerifyStatus.TAMPERED
    elif chain_breaks > 0:
        status = VerifyStatus.CHAIN_BROKEN
    elif pin_status == "TIP_MISMATCH":
        status = VerifyStatus.TAMPERED
    else:
        status = VerifyStatus.OK

    return {
        "shard_id": shard_id,
        "total_entries": total,
        "verified": verified,
        "tampered": tampered,
        "chain_breaks": chain_breaks,
        "status": status,
        "pin_status": pin_status,
        "expected_last_hash": expected_last_hash,
        "observed_last_hash": observed_last_hash,
        "expected_entry_count": expected_entry_count,
        "observed_entry_count": observed_entry_count,
        "chain_tip_mismatch": chain_tip_mismatch,
        "entry_count_mismatch": entry_count_mismatch,
        "truncation_detected": truncation_detected,
        "mismatch_type": mismatch_type,
        "warnings": warnings,
    }


def verify_all(storage: Storage) -> List[Dict[str, Any]]:
    """
    Verify hash chain for all shards returned by storage.list_shards().

    Returns:
        List of results from verify_shard() per shard.
    """
    shards = storage.list_shards()
    return [verify_shard(storage, s.shard_id) for s in shards]
