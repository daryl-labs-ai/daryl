"""
Tests for S-2 fix: key rotation and revocation for Ed25519 keypairs.
"""

import json
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("nacl", reason="PyNaCl required for signing tests")

from dsm.signing import AgentSigning, KeyHistory, _entry_hash, _is_valid_entry


@pytest.fixture
def keys_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


class TestKeyHistory:
    def test_empty_history_on_fresh_agent(self, keys_dir):
        """No history file → empty history."""
        kh = KeyHistory(Path(keys_dir), "alice")
        assert kh.entries == []
        assert kh.active_key() is None

    def test_record_key_creates_active_entry(self, keys_dir):
        """record_key adds an active entry and persists to disk."""
        kh = KeyHistory(Path(keys_dir), "alice")
        kh.record_key("aabb" * 8)
        assert len(kh.entries) == 1
        assert kh.entries[0]["status"] == "active"
        assert kh.entries[0]["public_key"] == "aabb" * 8
        assert kh.active_key() == "aabb" * 8
        path = Path(keys_dir) / "alice.keyhistory.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert len(data) == 1

    def test_record_key_retires_previous(self, keys_dir):
        """Recording a new key retires the old active one."""
        kh = KeyHistory(Path(keys_dir), "alice")
        kh.record_key("aaaa" * 8)
        kh.record_key("bbbb" * 8)
        assert len(kh.entries) == 2
        assert kh.entries[0]["status"] == "retired"
        assert kh.entries[0]["retired_at"] is not None
        assert kh.entries[1]["status"] == "active"
        assert kh.active_key() == "bbbb" * 8

    def test_record_key_idempotent(self, keys_dir):
        """Recording the same key twice does not duplicate."""
        kh = KeyHistory(Path(keys_dir), "alice")
        kh.record_key("aaaa" * 8)
        kh.record_key("aaaa" * 8)
        assert len(kh.entries) == 1

    def test_revoke_key(self, keys_dir):
        """Revoking a key marks it as revoked."""
        kh = KeyHistory(Path(keys_dir), "alice")
        kh.record_key("aaaa" * 8)
        result = kh.revoke_key("aaaa" * 8, reason="compromised")
        assert result is True
        assert kh.entries[0]["status"] == "revoked"
        assert kh.is_revoked("aaaa" * 8)

    def test_revoke_unknown_key(self, keys_dir):
        """Revoking an unknown key returns False."""
        kh = KeyHistory(Path(keys_dir), "alice")
        result = kh.revoke_key("dead" * 8)
        assert result is False

    def test_all_valid_keys_excludes_revoked(self, keys_dir):
        """all_valid_keys returns active + retired but not revoked."""
        kh = KeyHistory(Path(keys_dir), "alice")
        kh.record_key("aaaa" * 8)
        kh.record_key("bbbb" * 8)
        kh.record_key("cccc" * 8)
        kh.revoke_key("aaaa" * 8)
        valid = kh.all_valid_keys()
        assert "aaaa" * 8 not in valid
        assert "bbbb" * 8 in valid
        assert "cccc" * 8 in valid

    def test_history_survives_reload(self, keys_dir):
        """History persists across instances."""
        kh1 = KeyHistory(Path(keys_dir), "alice")
        kh1.record_key("aaaa" * 8)
        kh1.record_key("bbbb" * 8)
        kh2 = KeyHistory(Path(keys_dir), "alice")
        assert len(kh2.entries) == 2
        assert kh2.active_key() == "bbbb" * 8


class TestEntryValidation:
    def test_valid_entry(self):
        """A well-formed entry passes validation."""
        entry = {
            "public_key": "aabb" * 8,
            "created_at": "2026-03-17T00:00:00+00:00",
            "status": "active",
        }
        assert _is_valid_entry(entry) is True

    def test_missing_public_key(self):
        """Entry without public_key is invalid."""
        assert _is_valid_entry({"status": "active", "created_at": "2026-01-01"}) is False

    def test_invalid_status(self):
        """Entry with unknown status is invalid."""
        entry = {
            "public_key": "aa" * 16,
            "status": "unknown",
            "created_at": "2026-01-01",
        }
        assert _is_valid_entry(entry) is False

    def test_missing_created_at(self):
        """Entry without created_at is invalid."""
        assert _is_valid_entry({"public_key": "aa" * 16, "status": "active"}) is False

    def test_non_dict_entry(self):
        """Non-dict entry is invalid."""
        assert _is_valid_entry("not a dict") is False
        assert _is_valid_entry(42) is False
        assert _is_valid_entry(None) is False

    def test_corrupted_entries_skipped_on_load(self, keys_dir):
        """Invalid entries in the JSON file are skipped with a warning."""
        path = Path(keys_dir) / "alice.keyhistory.json"
        data = [
            {"public_key": "aaaa" * 8, "created_at": "2026-01-01", "status": "active"},
            {"garbage": True},
            "not a dict",
            {"public_key": "bbbb" * 8, "created_at": "2026-01-02", "status": "retired"},
        ]
        path.write_text(json.dumps(data))
        kh = KeyHistory(Path(keys_dir), "alice")
        assert len(kh.entries) == 2


class TestHistoryFilePermissions:
    def test_keyhistory_file_permissions(self, keys_dir):
        """Key history file should have restricted permissions (0o600)."""
        kh = KeyHistory(Path(keys_dir), "alice")
        kh.record_key("aaaa" * 8)
        path = Path(keys_dir) / "alice.keyhistory.json"
        mode = oct(path.stat().st_mode)[-3:]
        assert mode == "600", f"Key history file has permissions {mode}, expected 600"


class TestHashChain:
    def test_entries_have_hash_and_prev_hash(self, keys_dir):
        """Each recorded entry gets a hash and prev_hash."""
        kh = KeyHistory(Path(keys_dir), "alice")
        kh.record_key("aaaa" * 8)
        kh.record_key("bbbb" * 8)
        assert kh.entries[0]["prev_hash"] is None
        assert kh.entries[0]["hash"] is not None
        assert kh.entries[1]["prev_hash"] == kh.entries[0]["hash"]
        assert kh.entries[1]["hash"] is not None
        assert kh.entries[0]["hash"] != kh.entries[1]["hash"]

    def test_verify_chain_valid(self, keys_dir):
        """verify_chain returns valid=True for untampered history."""
        kh = KeyHistory(Path(keys_dir), "alice")
        kh.record_key("aaaa" * 8)
        kh.record_key("bbbb" * 8)
        kh.record_key("cccc" * 8)
        result = kh.verify_chain()
        assert result["valid"] is True
        assert result["entries_checked"] == 3

    def test_verify_chain_detects_tampered_hash(self, keys_dir):
        """Modifying a hash in the file is detected."""
        kh = KeyHistory(Path(keys_dir), "alice")
        kh.record_key("aaaa" * 8)
        kh.record_key("bbbb" * 8)
        kh._entries[0]["hash"] = "deadbeef" * 8
        kh._save()
        kh2 = KeyHistory(Path(keys_dir), "alice")
        result = kh2.verify_chain()
        assert result["valid"] is False
        assert "Hash mismatch" in result["error"]

    def test_verify_chain_detects_tampered_prev_hash(self, keys_dir):
        """Modifying prev_hash breaks chain verification."""
        kh = KeyHistory(Path(keys_dir), "alice")
        kh.record_key("aaaa" * 8)
        kh.record_key("bbbb" * 8)
        kh._entries[1]["prev_hash"] = "00" * 32
        kh._save()
        kh2 = KeyHistory(Path(keys_dir), "alice")
        result = kh2.verify_chain()
        assert result["valid"] is False

    def test_verify_chain_survives_status_change(self, keys_dir):
        """Retiring/revoking a key doesn't break the chain (hash uses initial status)."""
        kh = KeyHistory(Path(keys_dir), "alice")
        kh.record_key("aaaa" * 8)
        kh.record_key("bbbb" * 8)
        kh.revoke_key("aaaa" * 8)
        result = kh.verify_chain()
        assert result["valid"] is True

    def test_verify_chain_via_agent_signing(self, keys_dir):
        """verify_key_history_chain() on AgentSigning delegates correctly."""
        sign = AgentSigning(keys_dir, "alice")
        sign.generate_keypair()
        sign.rotate_key()
        result = sign.verify_key_history_chain()
        assert result["valid"] is True
        assert result["entries_checked"] == 2


class TestRotateKey:
    def test_rotate_creates_new_key(self, keys_dir):
        """rotate_key generates a new keypair and retires the old one."""
        sign = AgentSigning(keys_dir, "alice")
        sign.generate_keypair()
        old_pub = sign.get_public_key()

        result = sign.rotate_key(reason="test rotation")
        assert result["old_public_key"] == old_pub
        assert result["new_public_key"] != old_pub
        assert result["new_public_key"] == sign.get_public_key()

    def test_rotate_key_history_updated(self, keys_dir):
        """After rotation, history has two entries: retired + active."""
        sign = AgentSigning(keys_dir, "alice")
        sign.generate_keypair()
        sign.rotate_key()

        history = sign.key_history
        assert len(history) == 2
        assert history[0]["status"] == "retired"
        assert history[1]["status"] == "active"

    def test_rotate_preserves_old_signatures(self, keys_dir):
        """Signatures made with old key are still cryptographically verifiable."""
        sign = AgentSigning(keys_dir, "alice")
        sign.generate_keypair()
        old_pub = sign.get_public_key()
        old_sig = sign.sign_entry("important_data")

        sign.rotate_key()

        result = sign.verify_signature("important_data", old_sig, old_pub)
        assert result["valid"] is True

    def test_rotate_new_key_signs(self, keys_dir):
        """New key can sign and verify after rotation."""
        sign = AgentSigning(keys_dir, "alice")
        sign.generate_keypair()
        sign.rotate_key()

        new_sig = sign.sign_entry("new_data")
        new_pub = sign.get_public_key()
        result = sign.verify_signature("new_data", new_sig, new_pub)
        assert result["valid"] is True

    def test_multiple_rotations(self, keys_dir):
        """Three rotations produce correct history."""
        sign = AgentSigning(keys_dir, "alice")
        sign.generate_keypair()
        sign.rotate_key(reason="rotation 1")
        sign.rotate_key(reason="rotation 2")

        history = sign.key_history
        assert len(history) == 3
        assert history[0]["status"] == "retired"
        assert history[1]["status"] == "retired"
        assert history[2]["status"] == "active"
        keys = [e["public_key"] for e in history]
        assert len(set(keys)) == 3

    def test_rotate_reason_stored(self, keys_dir):
        """Rotation reason is stored in the retired entry."""
        sign = AgentSigning(keys_dir, "alice")
        sign.generate_keypair()
        sign.rotate_key(reason="quarterly renewal")

        history = sign.key_history
        assert history[0]["reason"] == "quarterly renewal"


class TestRevokeKey:
    def test_revoke_active_key(self, keys_dir):
        """Revoking the active key clears signing ability."""
        sign = AgentSigning(keys_dir, "alice")
        sign.generate_keypair()
        pub = sign.get_public_key()

        result = sign.revoke_key(pub, reason="key leaked")
        assert result is True

        with pytest.raises(ValueError, match="revoked"):
            sign.sign_entry("test")

    def test_revoke_prevents_signing_after_reload(self, keys_dir):
        """CRITICAL: sign_entry reloads keys from disk, so revocation
        must be checked even on a fresh instance that reloads _signing_key."""
        sign = AgentSigning(keys_dir, "alice")
        sign.generate_keypair()
        pub = sign.get_public_key()
        sign.revoke_key(pub, reason="compromised")

        sign2 = AgentSigning(keys_dir, "alice")
        with pytest.raises(ValueError, match="revoked"):
            sign2.sign_entry("should_fail")

    def test_revoke_retired_key(self, keys_dir):
        """Revoking a retired key marks it as revoked."""
        sign = AgentSigning(keys_dir, "alice")
        sign.generate_keypair()
        old_pub = sign.get_public_key()
        sign.rotate_key()

        result = sign.revoke_key(old_pub, reason="old key compromised")
        assert result is True

        history = sign.key_history
        revoked_entry = [e for e in history if e["public_key"] == old_pub][0]
        assert revoked_entry["status"] == "revoked"

    def test_revoke_unknown_key_returns_false(self, keys_dir):
        """Revoking a key not in history returns False."""
        sign = AgentSigning(keys_dir, "alice")
        sign.generate_keypair()
        result = sign.revoke_key("dead" * 16)
        assert result is False


class TestVerifyWithHistory:
    def test_verify_active_key(self, keys_dir):
        """Verify with active key returns valid + key_status=active."""
        sign = AgentSigning(keys_dir, "alice")
        sign.generate_keypair()
        pub = sign.get_public_key()
        sig = sign.sign_entry("data123")

        result = sign.verify_with_history("data123", sig, pub)
        assert result["valid"] is True
        assert result["crypto_valid"] is True
        assert result["revoked"] is False
        assert result["key_status"] == "active"

    def test_verify_retired_key(self, keys_dir):
        """Verify with retired key returns valid (retired ≠ revoked)."""
        sign = AgentSigning(keys_dir, "alice")
        sign.generate_keypair()
        old_pub = sign.get_public_key()
        old_sig = sign.sign_entry("old_data")
        sign.rotate_key()

        result = sign.verify_with_history("old_data", old_sig, old_pub)
        assert result["valid"] is True
        assert result["key_status"] == "retired"

    def test_verify_revoked_key(self, keys_dir):
        """Verify with revoked key returns valid=False even if crypto is OK."""
        sign = AgentSigning(keys_dir, "alice")
        sign.generate_keypair()
        pub = sign.get_public_key()
        sig = sign.sign_entry("data")
        sign.rotate_key()
        sign.revoke_key(pub, reason="compromised")

        result = sign.verify_with_history("data", sig, pub)
        assert result["valid"] is False
        assert result["crypto_valid"] is True
        assert result["revoked"] is True
        assert result["key_status"] == "revoked"

    def test_verify_unknown_key(self, keys_dir):
        """Verify with key not in history returns key_status=None."""
        sign = AgentSigning(keys_dir, "alice")
        sign.generate_keypair()
        sig = sign.sign_entry("data")
        pub = sign.get_public_key()

        sign2 = AgentSigning(keys_dir, "bob")
        result = sign2.verify_with_history("data", sig, pub)
        assert result["crypto_valid"] is True
        assert result["key_status"] is None


class TestBackwardCompatibility:
    def test_no_history_file_still_works(self, keys_dir):
        """Agent without keyhistory.json works exactly as before."""
        sign = AgentSigning(keys_dir, "legacy")
        sign.generate_keypair()
        pub = sign.get_public_key()
        sig = sign.sign_entry("test")
        result = sign.verify_signature("test", sig, pub)
        assert result["valid"] is True

    def test_generate_bootstraps_history(self, keys_dir):
        """First generate_keypair creates history with one entry."""
        sign = AgentSigning(keys_dir, "alice")
        sign.generate_keypair()
        assert len(sign.key_history) == 1
        assert sign.key_history[0]["status"] == "active"

    def test_existing_agent_gets_history_on_load(self, keys_dir):
        """Existing agent without history gets bootstrapped on generate(force=False)."""
        sign1 = AgentSigning(keys_dir, "old_agent")
        sign1.generate_keypair()
        history_path = Path(keys_dir) / "old_agent.keyhistory.json"
        if history_path.exists():
            history_path.unlink()

        sign2 = AgentSigning(keys_dir, "old_agent")
        sign2.generate_keypair(force=False)
        assert len(sign2.key_history) == 1
        assert sign2.key_history[0]["status"] == "active"
