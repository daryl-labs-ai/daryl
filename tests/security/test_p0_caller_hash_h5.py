"""
P0 / H5 — Adversarial test: caller-supplied hash accepted on write.

Threat model: a malicious or buggy producer pre-sets entry.hash to an
arbitrary value. Before the fix, storage.append() only computes the hash
`if not entry.hash`, so the forged value is persisted verbatim and becomes
the prev_hash of the next entry.

After the fix, append() ALWAYS recomputes the canonical hash and ignores any
caller-supplied value.
"""

import uuid
from datetime import datetime, timezone

from dsm.core.storage import Storage, _compute_canonical_entry_hash
from dsm.core.models import Entry


def _forged_entry(content="x", shard="sessions") -> Entry:
    return Entry(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        session_id="h5",
        source="agent",
        content=content,
        shard=shard,
        hash="deadbeef" * 8,  # attacker-chosen, not the canonical hash
        prev_hash=None,
        metadata={},
        version="v2.0",
    )


def test_caller_supplied_hash_is_ignored(tmp_path):
    storage = Storage(data_dir=str(tmp_path))
    forged = _forged_entry()
    forged_value = forged.hash

    stored = storage.append(forged)

    expected = _compute_canonical_entry_hash(stored, stored.prev_hash)
    assert stored.hash == expected, "append did not recompute the canonical hash"
    assert stored.hash != forged_value, "append persisted the attacker-supplied hash"


def test_persisted_hash_matches_recomputation(tmp_path):
    storage = Storage(data_dir=str(tmp_path))
    storage.append(_forged_entry("a"))
    storage.append(_forged_entry("b"))

    # Re-read from disk and verify the chain validates end-to-end.
    from dsm.verify import verify_shard

    result = verify_shard(Storage(data_dir=str(tmp_path)), "sessions")
    assert getattr(result["status"], "value", str(result["status"])) == "OK"
    assert result["tampered"] == 0
