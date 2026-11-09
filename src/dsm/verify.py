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
is shorter than the pin has been truncated and is reported as TAMPERED.

P1 fix: the pin lives next to the data, so deleting it erased the only
completeness proof and the shard verified OK. Now:
  * a NON-EMPTY shard with no pin and no client checkpoint returns
    status UNPINNED (not OK): the chain is consistent but completeness is
    unprovable;
  * verify_shard(checkpoint=...) checks the shard against a checkpoint held by
    the client (see dsm.checkpoint): truncation, deletion and prefix rewrite
    are detected even if the pin was removed or rewritten;
  * verify_shard(checkpoint=..., trusted_public_key=...) additionally requires
    the checkpoint to be signed by that key, which detects a coherent rewrite
    of the whole (unkeyed) chain by an attacker without the agent's key.
"""

import json
from typing import Dict, List, Any, Optional

from dsm_primitives import verify_hash

from .checkpoint import verify_checkpoint_signature
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


def _check_checkpoint(
    shard_id: str,
    hashes_chrono: List[Optional[str]],
    checkpoint: Dict[str, Any],
    trusted_public_key: Optional[str],
) -> str:
    """Compare the on-disk chain to a client-held checkpoint.

    Returns CHECKPOINT_OK or a failure code:
    MALFORMED | SHARD_MISMATCH | UNSIGNED | UNTRUSTED_KEY | SIGNATURE_INVALID |
    TRUNCATED | REWRITTEN
    """
    if not isinstance(checkpoint, dict):
        return "MALFORMED"
    count = checkpoint.get("entry_count")
    last_hash = checkpoint.get("last_hash")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        return "MALFORMED"
    if (count == 0) != (last_hash is None):
        return "MALFORMED"
    if checkpoint.get("shard_id") != shard_id:
        return "SHARD_MISMATCH"
    if trusted_public_key is not None:
        sig_problem = verify_checkpoint_signature(checkpoint, trusted_public_key)
        if sig_problem is not None:
            return sig_problem
    if len(hashes_chrono) < count:
        return "TRUNCATED"
    if count > 0 and hashes_chrono[count - 1] != last_hash:
        return "REWRITTEN"
    return "CHECKPOINT_OK"


def verify_shard(
    storage: Storage,
    shard_id: str,
    checkpoint: Optional[Dict[str, Any]] = None,
    trusted_public_key: Optional[str] = None,
) -> Dict[str, Any]:
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
        mismatch_type         None | "TRUNCATION" | "COUNT_MISMATCH" | "TIP_MISMATCH" |
                              "PREFIX_REWRITTEN" (longer than the pin, pinned tip gone)
        warnings              list[str]

        checkpoint_status     None (no checkpoint given) | "CHECKPOINT_OK" | failure
                              code from _check_checkpoint()

    status is VerifyStatus.OK | TAMPERED | CHAIN_BROKEN | UNPINNED.
    Truncation, tail tampering and any checkpoint failure map to TAMPERED.
    UNPINNED means: chain consistent, but the shard is non-empty and neither a
    pin nor a client checkpoint proves it is complete.

    checkpoint: a dict from dsm.checkpoint.make_checkpoint(), kept by the
        client outside the data directory.
    trusted_public_key: hex Ed25519 key the client trusts for this agent; when
        given, the checkpoint must carry a valid signature by that key.
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
        elif (
            expected_entry_count is not None
            and observed_entry_count > expected_entry_count
            and (
                expected_entry_count < 1
                or entries_chrono[expected_entry_count - 1].hash != expected_last_hash
            )
        ):
            # Longer than the pin, but the pinned tip is not where it should be:
            # the pinned prefix was rewritten, then extended. Growth is only
            # legitimate if it extends the pinned prefix unchanged.
            chain_tip_mismatch = True
            entry_count_mismatch = True
            mismatch_type = "PREFIX_REWRITTEN"
            pin_status = "TIP_MISMATCH"
        elif expected_entry_count is not None and observed_entry_count > expected_entry_count:
            # More on disk than pinned, and the pinned tip is intact at its
            # position → crash window / pin lag; recoverable via reconcile, not
            # a loss. Surface it, but do not fail verification.
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

    # ----- P1: client-held checkpoint (out-of-band completeness proof) -----
    checkpoint_status: Optional[str] = None
    if checkpoint is not None:
        checkpoint_status = _check_checkpoint(
            shard_id, [e.hash for e in entries_chrono], checkpoint, trusted_public_key
        )
        if checkpoint_status != "CHECKPOINT_OK":
            warnings.append(f"CHECKPOINT_FAILED: {checkpoint_status}")
    elif trusted_public_key is not None:
        checkpoint_status = "UNSIGNED"
        warnings.append("CHECKPOINT_FAILED: trusted_public_key given without a checkpoint")

    if tampered > 0:
        status = VerifyStatus.TAMPERED
    elif chain_breaks > 0:
        status = VerifyStatus.CHAIN_BROKEN
    elif pin_status == "TIP_MISMATCH":
        status = VerifyStatus.TAMPERED
    elif checkpoint_status is not None and checkpoint_status != "CHECKPOINT_OK":
        status = VerifyStatus.TAMPERED
    elif pin_status == "UNPINNED" and total > 0 and checkpoint_status is None:
        status = VerifyStatus.UNPINNED
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
        "checkpoint_status": checkpoint_status,
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


def pre_repair_check(storage: Storage) -> List[Dict[str, Any]]:
    """Verify every shard whose on-disk tip differs from its pin, BEFORE any
    repair touches the pin.

    The kernel's reconcile advances the pin on any FORWARD divergence
    (segment longer than the pin) and creates a pin for an unpinned shard.
    Done blindly, that launders a rewritten-then-extended chain or a
    truncated shard whose pin was deleted: afterwards everything verifies OK.
    Only a divergence that verify_shard() accepts (status OK, i.e. a genuine
    crash window extending the pinned prefix) may be repaired.

    Returns the verify_shard() results of the shards that must NOT be
    repaired (empty list = safe to reconcile). Shards whose tip already
    matches the pin are not re-read (O(1) per shard on the happy path).
    """
    blocked: List[Dict[str, Any]] = []
    for shard in storage.list_shards():
        shard_id = shard.shard_id
        try:
            tail = storage._read_last_segment_tail(shard_id)
        except Exception:
            tail = None
        if tail is None:
            continue  # empty shard: nothing to repair
        pin = _read_pin(storage, shard_id)
        if pin and pin.get("last_hash") and pin.get("last_hash") == tail.get("hash"):
            continue  # pin and tip agree: reconcile is a no-op
        result = verify_shard(storage, shard_id)
        if result["status"] != VerifyStatus.OK:
            blocked.append(result)
    return blocked


def guarded_startup_check(storage: Storage, full_verify: bool = False) -> Dict[str, Any]:
    """storage.startup_check() with verification BEFORE repair.

    If pre_repair_check() finds a divergence that does not verify, nothing is
    reconciled (no pin is moved or created) and the status is
    INTEGRITY_ERROR; the refused shards are listed under "repair_refused".
    Otherwise the kernel's startup_check runs unchanged.
    """
    blocked = pre_repair_check(storage)
    if blocked:
        return {
            "status": "INTEGRITY_ERROR",
            "shards_reconciled": 0,
            "reconciled": [],
            "repair_refused": blocked,
            "verified": blocked,
            "shards_with_errors": len(blocked),
        }
    return storage.startup_check(full_verify=full_verify)
