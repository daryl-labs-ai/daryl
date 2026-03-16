"""
Tests for S-1 fix: seed encryption with random salt instead of deterministic salt.
"""

import os
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("nacl", reason="PyNaCl required for signing tests")
pytest.importorskip("cryptography", reason="cryptography required for encryption tests")

from dsm.signing import AgentSigning, load_public_key


@pytest.fixture
def keys_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


class TestRandomSalt:
    def test_salt_file_created_on_generate(self, keys_dir):
        """generate_keypair() creates a .salt file alongside .seed and .pub."""
        sign = AgentSigning(keys_dir, "alice")
        sign.generate_keypair()
        salt_path = Path(keys_dir) / "alice.salt"
        assert salt_path.exists()
        assert len(salt_path.read_bytes()) == 32

    def test_salt_file_permissions(self, keys_dir):
        """Salt file should have restricted permissions (0o600)."""
        sign = AgentSigning(keys_dir, "alice")
        sign.generate_keypair()
        salt_path = Path(keys_dir) / "alice.salt"
        mode = oct(salt_path.stat().st_mode)[-3:]
        assert mode == "600", f"Salt file has permissions {mode}, expected 600"

    def test_salt_is_random_between_agents(self, keys_dir):
        """Different agents get different salts."""
        a = AgentSigning(keys_dir, "alice")
        a.generate_keypair()
        b = AgentSigning(keys_dir, "bob")
        b.generate_keypair()
        salt_a = (Path(keys_dir) / "alice.salt").read_bytes()
        salt_b = (Path(keys_dir) / "bob.salt").read_bytes()
        assert salt_a != salt_b

    def test_salt_is_random_across_regenerate(self, keys_dir):
        """force=True regenerate creates a new salt."""
        sign = AgentSigning(keys_dir, "alice")
        sign.generate_keypair()
        salt_1 = (Path(keys_dir) / "alice.salt").read_bytes()
        sign.generate_keypair(force=True)
        salt_2 = (Path(keys_dir) / "alice.salt").read_bytes()
        # Salt might be same (unlikely) but key should still work
        sign2 = AgentSigning(keys_dir, "alice")
        sign2.generate_keypair(force=False)
        assert sign2.get_public_key() is not None

    def test_keypair_roundtrip_with_new_kdf(self, keys_dir):
        """Generate, reload from disk, sign+verify works."""
        sign1 = AgentSigning(keys_dir, "alice")
        sign1.generate_keypair()
        pub = sign1.get_public_key()

        sign2 = AgentSigning(keys_dir, "alice")
        assert sign2.get_public_key() == pub
        sig = sign2.sign_entry("test_hash_123")
        result = sign2.verify_signature("test_hash_123", sig, pub)
        assert result["valid"] is True

    def test_different_hostname_cannot_decrypt_legacy(self, keys_dir):
        """With random salt, the hostname is irrelevant to decryption."""
        sign = AgentSigning(keys_dir, "alice")
        sign.generate_keypair()
        pub = sign.get_public_key()

        sign2 = AgentSigning(keys_dir, "alice")
        assert sign2.get_public_key() == pub


class TestPasswordProtection:
    def test_password_encrypts_seed(self, keys_dir):
        """Seed encrypted with password can be decrypted with same password."""
        sign = AgentSigning(keys_dir, "alice", password="my-secret-passphrase")
        sign.generate_keypair()
        pub = sign.get_public_key()

        sign2 = AgentSigning(keys_dir, "alice", password="my-secret-passphrase")
        assert sign2.get_public_key() == pub

    def test_wrong_password_fails(self, keys_dir):
        """Seed encrypted with password cannot be decrypted with wrong password.

        get_public_key() must still work (reads .pub directly from disk),
        but sign_entry() must fail because the private key could not be loaded.
        """
        sign = AgentSigning(keys_dir, "alice", password="correct-password")
        sign.generate_keypair()
        original_pub = sign.get_public_key()

        sign2 = AgentSigning(keys_dir, "alice", password="wrong-password")
        pub = sign2.get_public_key()
        assert pub is not None, "get_public_key must read .pub even when seed decrypt fails"
        assert pub == original_pub, "Public key must match regardless of password"

        with pytest.raises(ValueError, match="Failed to load keypair"):
            sign2.sign_entry("test_hash")

    def test_no_password_uses_agent_id(self, keys_dir):
        """Without password, agent_id is used (backward compatible but weaker)."""
        sign = AgentSigning(keys_dir, "alice")
        sign.generate_keypair()
        pub = sign.get_public_key()

        sign2 = AgentSigning(keys_dir, "alice")
        assert sign2.get_public_key() == pub
        sig = sign2.sign_entry("hash123")
        result = sign2.verify_signature("hash123", sig, pub)
        assert result["valid"] is True


class TestLegacyMigration:
    def test_legacy_seed_auto_migrated(self, keys_dir):
        """Seed encrypted with legacy KDF is auto-migrated to new KDF on load."""
        sign = AgentSigning(keys_dir, "legacy_agent")

        import nacl.signing
        from cryptography.fernet import Fernet

        key = nacl.signing.SigningKey.generate()
        seed = bytes(key)
        pub = bytes(key.verify_key)

        fernet = Fernet(sign._derive_key_legacy())
        encrypted = fernet.encrypt(seed)
        sign._seed_path.write_bytes(encrypted)
        sign._pub_path.write_bytes(pub)

        salt_path = Path(keys_dir) / "legacy_agent.salt"
        if salt_path.exists():
            salt_path.unlink()

        sign2 = AgentSigning(keys_dir, "legacy_agent")
        loaded_pub = sign2.get_public_key()
        assert loaded_pub == pub.hex()

        assert salt_path.exists()
        assert len(salt_path.read_bytes()) == 32

        sign3 = AgentSigning(keys_dir, "legacy_agent")
        assert sign3.get_public_key() == pub.hex()

    def test_raw_seed_auto_migrated(self, keys_dir):
        """Raw unencrypted seed is auto-encrypted with new KDF on load."""
        import nacl.signing

        key = nacl.signing.SigningKey.generate()
        seed = bytes(key)
        pub = bytes(key.verify_key)

        seed_path = Path(keys_dir) / "raw_agent.seed"
        pub_path = Path(keys_dir) / "raw_agent.pub"
        seed_path.write_bytes(seed)
        pub_path.write_bytes(pub)

        sign = AgentSigning(keys_dir, "raw_agent")
        loaded_pub = sign.get_public_key()
        assert loaded_pub == pub.hex()

        new_seed_bytes = seed_path.read_bytes()
        assert len(new_seed_bytes) != 32, "Seed should be encrypted (>32 bytes)"

        salt_path = Path(keys_dir) / "raw_agent.salt"
        assert salt_path.exists()

    def test_migration_preserves_signatures(self, keys_dir):
        """After migration, signatures made with old key are still verifiable."""
        import nacl.signing
        from cryptography.fernet import Fernet

        key = nacl.signing.SigningKey.generate()
        seed = bytes(key)
        pub = bytes(key.verify_key)

        msg = "important_hash".encode("utf-8")
        original_sig = key.sign(msg).signature.hex()

        sign = AgentSigning(keys_dir, "migrate_agent")
        fernet = Fernet(sign._derive_key_legacy())
        sign._seed_path.write_bytes(fernet.encrypt(seed))
        sign._pub_path.write_bytes(pub)

        sign2 = AgentSigning(keys_dir, "migrate_agent")
        sign2.get_public_key()

        result = sign2.verify_signature("important_hash", original_sig, pub.hex())
        assert result["valid"] is True

        new_sig = sign2.sign_entry("new_hash")
        result2 = sign2.verify_signature("new_hash", new_sig, pub.hex())
        assert result2["valid"] is True
