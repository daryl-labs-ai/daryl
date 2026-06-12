"""
P0 / C1 — Adversarial tests: trailing truncation of an append-only shard.

Threat model: an attacker with write access to the shard files deletes the
last N entries (typically the most incriminating recent decisions). The
DSM promise is "append-only / tamper-evident": verification MUST detect this.

Before the C1 fix these tests FAIL — verify_shard returns status OK and
reconcile_shard silently rewrites the integrity pin to match the truncated
tail. After the fix:
  * verify_shard reports the pin/tip mismatch (status != OK),
  * reconcile_shard refuses to shrink the pin in the default (safe) mode.
"""

from dsm.core.storage import Storage
from dsm.verify import verify_shard

from ._helpers import append_n, truncate_last_segment, read_pin


def _status(result) -> str:
    s = result["status"]
    return getattr(s, "value", str(s))


class TestC1TruncationDetection:
    def test_intact_shard_verifies_ok(self, tmp_path):
        storage = Storage(data_dir=str(tmp_path))
        append_n(storage, 10)
        result = verify_shard(storage, "sessions")
        assert _status(result) == "OK"
        assert result["total_entries"] == 10

    def test_trailing_truncation_is_detected(self, tmp_path):
        storage = Storage(data_dir=str(tmp_path))
        append_n(storage, 10)
        assert _status(verify_shard(storage, "sessions")) == "OK"

        before, after = truncate_last_segment(storage, "sessions", 4)
        assert (before, after) == (10, 6)

        # Fresh verifier (no in-memory state) — the only ground truth is on disk.
        result = verify_shard(Storage(data_dir=str(tmp_path)), "sessions")

        # The core guarantee: truncation must NOT verify as OK.
        assert _status(result) != "OK", (
            "C1: trailing truncation went undetected — verify returned OK"
        )
        # Structured evidence the fix must surface.
        assert result.get("entry_count_mismatch") is True
        assert result.get("expected_entry_count") == 10
        assert result.get("observed_entry_count") == 6
        assert result.get("mismatch_type") in ("TRUNCATION", "COUNT_MISMATCH", "TIP_MISMATCH")

    def test_unpinned_shard_is_not_silently_ok(self, tmp_path):
        """A shard with no integrity pin must be flagged UNPINNED, not silent OK."""
        storage = Storage(data_dir=str(tmp_path))
        append_n(storage, 5)
        # Remove the pin to simulate a historical/unpinned shard.
        pin = storage.integrity_dir / "sessions_last_hash.json"
        pin.unlink()

        result = verify_shard(Storage(data_dir=str(tmp_path)), "sessions")
        # Chain itself is intact, but absence of a pin must be explicit.
        assert result.get("pin_status") == "UNPINNED"


class TestReconcileDoesNotLaunderTruncation:
    def test_safe_reconcile_refuses_truncated_state(self, tmp_path):
        storage = Storage(data_dir=str(tmp_path))
        append_n(storage, 10)
        truncate_last_segment(storage, "sessions", 4)

        pin_before = read_pin(storage, "sessions")
        assert pin_before["entry_count"] == 10

        result = storage.reconcile_shard("sessions")  # default = safe

        # Must NOT reconcile a shrink, and must NOT touch the pin.
        assert result.get("reconciled") is False
        assert result.get("status") == "DIVERGENCE_REFUSED"
        pin_after = read_pin(storage, "sessions")
        assert pin_after["entry_count"] == 10, (
            "safe reconcile laundered a truncated state (pin shrank)"
        )
        assert pin_after["last_hash"] == pin_before["last_hash"]

    def test_recovery_mode_quarantines_old_tip(self, tmp_path):
        storage = Storage(data_dir=str(tmp_path))
        append_n(storage, 10)
        truncate_last_segment(storage, "sessions", 4)

        result = storage.reconcile_shard("sessions", allow_truncation=True)

        assert result.get("reconciled") is True
        assert result.get("entry_count") == 6
        # The previous (longer) tip must be preserved, not destroyed.
        quarantine = list(storage.integrity_dir.glob("sessions_last_hash.quarantine.*"))
        assert quarantine, "recovery mode must quarantine the superseded pin"

    def test_forward_crash_recovery_still_works(self, tmp_path):
        """Reconcile must still advance when the segment legitimately has MORE
        entries than the pin (K-2 crash window). This must not regress."""
        import json
        import os

        from dsm.core.storage import _compute_canonical_entry_hash
        from ._helpers import make_entry

        storage = Storage(data_dir=str(tmp_path))
        append_n(storage, 3)

        prev = storage._get_last_hash("sessions")
        orphan = make_entry("orphan", "sessions")
        orphan.prev_hash = prev
        orphan.hash = _compute_canonical_entry_hash(orphan, prev)
        seg = storage.segment_manager.get_active_segment("sessions")
        d = {
            "id": orphan.id, "timestamp": orphan.timestamp.isoformat(),
            "session_id": orphan.session_id, "source": orphan.source,
            "content": orphan.content, "shard": "sessions",
            "hash": orphan.hash, "prev_hash": orphan.prev_hash,
            "metadata": orphan.metadata, "version": orphan.version,
        }
        with open(seg, "a", encoding="utf-8") as f:
            f.write(json.dumps(d, sort_keys=True, separators=(",", ":")) + "\n")
            f.flush()
            os.fsync(f.fileno())

        result = storage.reconcile_shard("sessions")  # safe mode
        assert result.get("reconciled") is True
        assert result.get("entry_count") == 4
