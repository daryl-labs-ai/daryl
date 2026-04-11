"""Provenance builder (daryl port of ``dsm_v0.provenance.builder``).

Responsibility split — same contract as dsm_v0:

- This module owns ``trust_level``, ``integrity``, ``verification_hint``,
  ``broken_chains``, and the strict promotion rule for
  ``verified_claims``.
- ``dsm.recall`` and ``dsm.context`` delegate to :func:`build_provenance`
  rather than rebuilding their own provenance blocks.

API contract (identical to dsm_v0)
----------------------------------
- ``entry_hashes``            list[str]    — deduplicated, order preserved
- ``source_shards``           list[str]    — sorted unique **daryl shard ids**
- ``integrity``               str          — ``OK`` / ``not_verified`` / ``broken``
- ``verification_hint``       str | None   — shell command or None
- ``record_count``            int
- ``trust_level``             str          — ``verified`` / ``partial`` / ``unverified``
- ``broken_chains``           int          — shards that failed verification
- ``oldest_entry_age_days``   float | None

When ``verify=True``, additionally:
- ``verified_shards``         list[str]
- ``broken_shard_details``    list[dict]   — ``{shard_id, status, tampered, chain_breaks}``
- ``promotable_hashes``       list[str]

Promotion rule (strict V0) — unchanged:
  1. Item's source shard verified end-to-end (``status == OK``).
  2. Item's ``type`` is ``historical_decision``.
  3. Item's ``time_status`` is ``still_relevant``.
"""

from __future__ import annotations

import time
from typing import Any, Iterable, Optional

from ..core.models import Entry
from ..core.storage import Storage
from ..status import VerifyStatus
from ..verify import verify_shard

__all__ = [
    "build_provenance",
    "promote_to_verified_claims",
    "INTEGRITY_OK",
    "INTEGRITY_NOT_VERIFIED",
    "INTEGRITY_BROKEN",
    "TRUST_VERIFIED",
    "TRUST_PARTIAL",
    "TRUST_UNVERIFIED",
]


# Stable literal constants — same strings as dsm_v0.
TRUST_VERIFIED = "verified"
TRUST_PARTIAL = "partial"
TRUST_UNVERIFIED = "unverified"

INTEGRITY_OK = "OK"
INTEGRITY_NOT_VERIFIED = "not_verified"
INTEGRITY_BROKEN = "broken"

# Promotion rule constants — duplicated here intentionally to avoid a
# top-level import cycle with :mod:`dsm.recall`. Test
# ``test_enum_parity`` ensures they stay in sync with recall's values.
_PROMOTABLE_TYPES = frozenset({"historical_decision"})
_STATUS_STILL_RELEVANT = "still_relevant"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dedupe_preserve_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _default_hint(integrity: str, shards: list[str]) -> Optional[str]:
    """Return a non-null hint when verification would add value.

    - OK        → None (already verified)
    - broken / not_verified → CLI command targeting one of the shards
    """
    if integrity == INTEGRITY_OK:
        return None
    if not shards:
        return "dsm verify <shard_id>"
    first = shards[0]
    if len(shards) == 1:
        return f"dsm verify {first}"
    return f"dsm verify {first}  # + {len(shards) - 1} more shard(s)"


def _ts_to_seconds(ts: Any) -> float:
    """Normalize a timestamp (datetime / float / None) to unix seconds."""
    if ts is None:
        return 0.0
    if isinstance(ts, (int, float)):
        return float(ts)
    if hasattr(ts, "timestamp"):
        try:
            return float(ts.timestamp())
        except (TypeError, ValueError):
            return 0.0
    try:
        return float(ts)
    except (TypeError, ValueError):
        return 0.0


def _item_shard(item: dict[str, Any]) -> str:
    """Return the daryl shard id stored on a recall item.

    Recall items produced by ``dsm.recall`` in daryl carry the daryl
    ``shard`` alongside the ``session_id``. When absent, fall back to
    ``session_id`` — this makes the builder usable with items from a
    dsm_v0-shaped corpus (where session == shard).
    """
    return str(item.get("source_shard_id") or item.get("shard") or item.get("session_id") or "")


def _resolve_items_from_hashes(
    entry_hashes: list[str],
    storage: Storage,
) -> list[dict[str, Any]]:
    """Locate entries in daryl storage by hash.

    O(shards × events). Acceptable for V0 — a hash index would replace
    this in V1. Scans every shard returned by ``storage.list_shards()``.
    """
    wanted = {h for h in entry_hashes if h}
    if not wanted:
        return []
    found: list[dict[str, Any]] = []
    for shard_meta in storage.list_shards():
        sid = shard_meta.shard_id
        # large limit — V0 simplification; replace with a cursor in V1.
        try:
            entries = storage.read(sid, limit=100_000)
        except Exception:
            continue
        for entry in entries:
            if entry.hash in wanted:
                found.append({
                    "session_id": entry.session_id,
                    "source_shard_id": entry.shard,
                    "entry_hash": entry.hash,
                    "timestamp": _ts_to_seconds(entry.timestamp),
                    "event_type": (entry.metadata or {}).get("event_type", ""),
                    # type / time_status unknown without recall's
                    # classification pass; items forgo promotion.
                    "type": None,
                    "time_status": None,
                })
                if len(found) >= len(wanted):
                    return found
    return found


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------


def build_provenance(
    items: Optional[list[dict[str, Any]]] = None,
    entry_hashes: Optional[list[str]] = None,
    storage: Optional[Storage] = None,
    data_dir: str = "data",
    verify: bool = False,
    include_verification_hint: bool = True,
    now: Optional[float] = None,
) -> dict[str, Any]:
    """Return a provenance block for a set of recall items (daryl backend).

    Parameters
    ----------
    items:
        Match dicts as produced by :func:`dsm.recall.search_memory`.
        Each item should carry at least ``entry_hash``, ``timestamp``,
        ``session_id``, and ideally ``source_shard_id`` (the daryl
        physical shard). When ``source_shard_id`` is missing, the
        helper falls back to ``session_id``.
    entry_hashes:
        Alternative input — resolved via ``storage.read()``. Items
        obtained this way cannot be promoted (no type/status).
    storage:
        daryl :class:`Storage` instance. Created from ``data_dir`` when
        None.
    data_dir:
        Used only when ``storage`` is None.
    verify:
        When True, walk each source shard's chain via
        :func:`dsm.verify.verify_shard`. Upgrades integrity/trust and
        populates verify-mode fields.
    include_verification_hint:
        When False, forces ``verification_hint`` to None regardless of
        integrity.
    now:
        Clock override for deterministic tests.
    """
    now_seconds = float(now) if now is not None else time.time()

    # Lazy storage creation — mirrors daryl's RR convention.
    if storage is None:
        storage = Storage(data_dir=data_dir)

    if items is None:
        items = []
    if entry_hashes and not items:
        items = _resolve_items_from_hashes(entry_hashes, storage)

    if not items:
        block: dict[str, Any] = {
            "entry_hashes": [],
            "source_shards": [],
            "integrity": INTEGRITY_NOT_VERIFIED,
            "verification_hint": None,
            "record_count": 0,
            "trust_level": TRUST_PARTIAL,
            "broken_chains": 0,
            "oldest_entry_age_days": None,
        }
        if verify:
            block["verified_shards"] = []
            block["broken_shard_details"] = []
            block["promotable_hashes"] = []
        return block

    # Aggregate.
    hashes = _dedupe_preserve_order(
        [str(m.get("entry_hash") or "") for m in items if m.get("entry_hash")]
    )
    shards = sorted({_item_shard(m) for m in items if _item_shard(m)})

    oldest: Optional[float] = None
    for m in items:
        ts = _ts_to_seconds(m.get("timestamp"))
        if ts <= 0:
            continue
        age = (now_seconds - ts) / 86400.0
        if oldest is None or age > oldest:
            oldest = age

    if not verify:
        integrity = INTEGRITY_NOT_VERIFIED
        trust = TRUST_PARTIAL
        hint = (
            _default_hint(integrity, shards)
            if include_verification_hint
            else None
        )
        return {
            "entry_hashes": hashes,
            "source_shards": shards,
            "integrity": integrity,
            "verification_hint": hint,
            "record_count": len(items),
            "trust_level": trust,
            "broken_chains": 0,
            "oldest_entry_age_days": (
                round(oldest, 3) if oldest is not None else None
            ),
        }

    # Slow path — re-verify each source shard.
    verified_shards: list[str] = []
    broken_details: list[dict[str, Any]] = []
    for sid in shards:
        try:
            verdict = verify_shard(storage, sid)
        except Exception as exc:
            broken_details.append({
                "shard_id": sid,
                "status": "error",
                "error": str(exc),
            })
            continue
        if verdict.get("status") == VerifyStatus.OK:
            verified_shards.append(sid)
        else:
            broken_details.append({
                "shard_id": sid,
                "status": str(verdict.get("status")),
                "tampered": verdict.get("tampered", 0),
                "chain_breaks": verdict.get("chain_breaks", 0),
            })

    broken_count = len(broken_details)
    if broken_count == 0:
        integrity = INTEGRITY_OK
        trust = TRUST_VERIFIED
    elif broken_count < len(shards):
        integrity = INTEGRITY_BROKEN
        trust = TRUST_PARTIAL
    else:
        integrity = INTEGRITY_BROKEN
        trust = TRUST_UNVERIFIED

    # Strict promotion rule.
    verified_set = set(verified_shards)
    promotable = [
        str(m.get("entry_hash") or "")
        for m in items
        if (_item_shard(m) in verified_set
            and m.get("type") in _PROMOTABLE_TYPES
            and m.get("time_status") == _STATUS_STILL_RELEVANT
            and m.get("entry_hash"))
    ]
    promotable_hashes = _dedupe_preserve_order(promotable)

    hint = (
        _default_hint(integrity, shards)
        if include_verification_hint
        else None
    )

    return {
        "entry_hashes": hashes,
        "source_shards": shards,
        "integrity": integrity,
        "verification_hint": hint,
        "record_count": len(items),
        "trust_level": trust,
        "broken_chains": broken_count,
        "oldest_entry_age_days": (
            round(oldest, 3) if oldest is not None else None
        ),
        "verified_shards": verified_shards,
        "broken_shard_details": broken_details,
        "promotable_hashes": promotable_hashes,
    }


def promote_to_verified_claims(
    items: list[dict[str, Any]],
    provenance_block: dict[str, Any],
) -> list[dict[str, Any]]:
    """Filter items down to those promoted by a provenance block.

    Same contract as :func:`dsm_v0.provenance.promote_to_verified_claims`.
    Returns a new list of items with ``type`` rewritten to
    ``verified_fact`` and original type preserved under ``promoted_from``.
    """
    promotable = set(provenance_block.get("promotable_hashes") or [])
    if not promotable:
        return []
    promoted: list[dict[str, Any]] = []
    for m in items:
        h = m.get("entry_hash") or ""
        if h in promotable:
            new = dict(m)
            new["promoted_from"] = new.get("type")
            new["type"] = "verified_fact"
            promoted.append(new)
    return promoted
