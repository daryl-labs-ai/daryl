"""
Entry Signing (P9) — Ed25519 signing for DSM entries and receipts.

Proves authorship: only the agent with the private key can produce
a valid signature for an entry hash or receipt hash.
Composes with hash chain (integrity) and P4 (intent).
"""

import hashlib as _hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import nacl.signing
    import nacl.encoding
    NACL_AVAILABLE = True
except ImportError:
    NACL_AVAILABLE = False

try:
    from cryptography.fernet import Fernet
    FERNET_AVAILABLE = True
except ImportError:
    FERNET_AVAILABLE = False

# S-1: 2026 comfort-level iterations; legacy KDF uses 100_000 for migration
PBKDF2_ITERATIONS = 300_000

_VALID_STATUSES = {"active", "retired", "revoked"}


def _entry_hash(
    public_key: str, created_at: str, status: str, prev_hash: Optional[str]
) -> str:
    """Compute SHA-256 hash for a key history entry (chain link).

    Uses the initial status ('active') for hashing — status transitions
    (retired, revoked) do NOT rehash, so the chain verifies creation order.
    """
    payload = f"{public_key}:{created_at}:{status}:{prev_hash}"
    return _hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_valid_entry(entry: object) -> bool:
    """Validate that a key history entry has the required fields and types."""
    if not isinstance(entry, dict):
        return False
    if not isinstance(entry.get("public_key"), str):
        return False
    if entry.get("status") not in _VALID_STATUSES:
        return False
    if not isinstance(entry.get("created_at"), str):
        return False
    return True


class KeyHistory:
    """Manages the history of Ed25519 keys for an agent.

    S-2 fix: tracks key rotation and revocation. Each agent can have
    multiple keys over time. The history records which keys were active
    when, and whether they were retired (replaced) or revoked (compromised).

    The history is a hash-chained JSON array — each entry contains a hash
    and prev_hash, making the creation sequence tamper-evident (same
    principle as the DSM append-only log).
    """

    def __init__(self, keys_dir: Path, agent_id: str):
        self._path = keys_dir / f"{agent_id}.keyhistory.json"
        self._entries: list = []
        self._load()

    def _load(self) -> None:
        """Load key history from disk, validating each entry's schema."""
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    valid = []
                    for entry in data:
                        if _is_valid_entry(entry):
                            valid.append(entry)
                        else:
                            logger.warning(
                                "Skipping invalid key history entry: %s",
                                repr(entry)[:120],
                            )
                    self._entries = valid
                else:
                    logger.warning(
                        "Key history at %s is not a list, starting fresh", self._path
                    )
                    self._entries = []
            except (json.JSONDecodeError, OSError):
                logger.warning(
                    "Corrupted key history at %s, starting fresh", self._path
                )
                self._entries = []

    def _save(self) -> None:
        """Persist key history to disk (atomic write + chmod 0o600)."""
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(self._entries, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp, self._path)
        try:
            os.chmod(self._path, 0o600)
        except OSError:
            pass

    @property
    def entries(self) -> list:
        """Return a copy of all history entries."""
        return list(self._entries)

    def _last_hash(self) -> Optional[str]:
        """Return the hash of the last entry, or None if empty."""
        if self._entries:
            return self._entries[-1].get("hash")
        return None

    def active_key(self) -> Optional[str]:
        """Return the public_key hex of the current active key, or None."""
        for entry in reversed(self._entries):
            if entry.get("status") == "active":
                return entry["public_key"]
        return None

    def record_key(
        self, public_key: str, retire_reason: Optional[str] = None
    ) -> None:
        """Record a new active key. If another key was active, retire it.

        Called by generate_keypair() and rotate_key().
        Does NOT record if this public_key is already the active key.

        Args:
            public_key: Hex-encoded Ed25519 public key.
            retire_reason: Reason for retiring the previous active key.
                Defaults to "replaced by rotation".
        """
        if self.active_key() == public_key:
            return
        now = datetime.now(timezone.utc).isoformat()
        for entry in self._entries:
            if entry.get("status") == "active":
                entry["status"] = "retired"
                entry["retired_at"] = now
                entry["reason"] = retire_reason or "replaced by rotation"
        prev = self._last_hash()
        h = _entry_hash(public_key, now, "active", prev)
        self._entries.append({
            "public_key": public_key,
            "created_at": now,
            "status": "active",
            "retired_at": None,
            "reason": None,
            "prev_hash": prev,
            "hash": h,
        })
        self._save()

    def revoke_key(self, public_key: str, reason: str = "compromised") -> bool:
        """Mark a key as revoked. Returns True if key was found."""
        found = False
        now = datetime.now(timezone.utc).isoformat()
        for entry in self._entries:
            if entry["public_key"] == public_key:
                entry["status"] = "revoked"
                entry["retired_at"] = now
                entry["reason"] = reason
                found = True
        if found:
            self._save()
        return found

    def is_revoked(self, public_key: str) -> bool:
        """Check if a public key has been revoked."""
        for entry in self._entries:
            if (
                entry["public_key"] == public_key
                and entry.get("status") == "revoked"
            ):
                return True
        return False

    def all_valid_keys(self) -> list:
        """Return public_key hex of all non-revoked keys (active + retired)."""
        return [
            e["public_key"]
            for e in self._entries
            if e.get("status") in ("active", "retired")
        ]

    def verify_chain(self) -> dict:
        """Verify the hash chain integrity of the key history.

        Returns:
            {"valid": bool, "entries_checked": int, "error": str|None}
        """
        prev = None
        for i, entry in enumerate(self._entries):
            expected_hash = _entry_hash(
                entry["public_key"],
                entry["created_at"],
                "active",
                prev,
            )
            stored_hash = entry.get("hash")
            if stored_hash is None:
                prev = None
                continue
            if stored_hash != expected_hash:
                return {
                    "valid": False,
                    "entries_checked": i + 1,
                    "error": (
                        f"Hash mismatch at entry {i}: expected "
                        f"{expected_hash[:16]}..., got {stored_hash[:16]}..."
                    ),
                }
            stored_prev = entry.get("prev_hash")
            if stored_prev != prev:
                return {
                    "valid": False,
                    "entries_checked": i + 1,
                    "error": f"prev_hash mismatch at entry {i}",
                }
            prev = stored_hash
        return {
            "valid": True,
            "entries_checked": len(self._entries),
            "error": None,
        }


class AgentSigning:
    """Ed25519 signing for DSM entries and receipts.

    Keypair is stored in keys_dir as {agent_id}.seed (32 bytes)
    and {agent_id}.pub (32 bytes). Generated once, reused forever.
    """

    def __init__(self, keys_dir: str, agent_id: str, password: Optional[str] = None):
        self.keys_dir = Path(keys_dir)
        self.keys_dir.mkdir(parents=True, exist_ok=True)
        self.agent_id = agent_id
        self._password = password
        self._seed_path = self.keys_dir / f"{agent_id}.seed"
        self._pub_path = self.keys_dir / f"{agent_id}.pub"
        self._signing_key = None
        self._verify_key = None
        self._key_history = KeyHistory(self.keys_dir, agent_id)

    def _get_or_create_salt(self) -> bytes:
        """Read or create the persistent random salt for this agent's seed encryption.

        Validates that the salt is exactly 32 bytes. If the file is corrupted
        (wrong length), it is regenerated with a warning.
        Uses atomic write (tmp + os.replace) for consistency with _migrate_seed.
        """
        salt_path = self.keys_dir / f"{self.agent_id}.salt"
        if salt_path.exists():
            salt = salt_path.read_bytes()
            if len(salt) == 32:
                return salt
            logger.warning(
                "Salt file for '%s' has invalid length %d (expected 32), regenerating",
                self.agent_id,
                len(salt),
            )
        salt = os.urandom(32)
        if len(salt) != 32:
            raise RuntimeError("os.urandom failed to produce 32 bytes")
        tmp_path = salt_path.with_suffix(".salt.tmp")
        tmp_path.write_bytes(salt)
        os.replace(tmp_path, salt_path)
        try:
            os.chmod(salt_path, 0o600)
        except OSError:
            pass
        return salt

    def _derive_key(self, password: Optional[str] = None) -> bytes:
        """Derive Fernet key using PBKDF2 with a persistent random salt.

        S-1 fix: uses os.urandom(32) salt stored in {agent_id}.salt instead of
        the deterministic platform.node():path salt. If no password is provided,
        falls back to agent_id (weaker but backward-compatible).

        Uses PBKDF2_ITERATIONS (300K). The random salt ensures that even if
        agent_id is known, the encryption key cannot be derived without access
        to the salt file on disk.
        """
        import base64
        import hashlib

        salt = self._get_or_create_salt()
        pwd = (password or self.agent_id).encode("utf-8")
        raw = hashlib.pbkdf2_hmac("sha256", pwd, salt, PBKDF2_ITERATIONS)
        return base64.urlsafe_b64encode(raw)

    def _derive_key_legacy(self) -> bytes:
        """Legacy KDF using platform.node():path as salt + 100K iterations.

        Kept for migration only — allows decrypting seeds encrypted with the
        old deterministic salt. Must NOT be changed (would break migration).
        """
        import base64
        import hashlib
        import platform

        salt = f"{platform.node()}:{os.path.abspath(self.keys_dir)}"
        raw = hashlib.pbkdf2_hmac(
            "sha256", self.agent_id.encode(), salt.encode(), 100_000
        )
        return base64.urlsafe_b64encode(raw)

    def _migrate_seed(self, seed: bytes) -> None:
        """Re-encrypt seed with new random-salt KDF. Creates .salt file if needed."""
        if not FERNET_AVAILABLE:
            return
        try:
            fernet = Fernet(self._derive_key(self._password))
            encrypted = fernet.encrypt(seed)
            tmp_path = self._seed_path.with_suffix(".seed.tmp")
            tmp_path.write_bytes(encrypted)
            os.replace(tmp_path, self._seed_path)
            try:
                os.chmod(self._seed_path, 0o600)
            except OSError:
                pass
        except Exception as e:
            logger.warning("failed to migrate seed for '%s': %s", self.agent_id, e)

    def generate_keypair(self, force: bool = False) -> dict:
        """Generate ed25519 keypair for this agent."""
        if not NACL_AVAILABLE:
            raise RuntimeError("PyNaCl is required for signing. Install with: pip install PyNaCl")
        if self._seed_path.exists() and self._pub_path.exists() and not force:
            self._load_keypair()
            pub = self.get_public_key()
            if pub:
                self._key_history.record_key(
                    pub, retire_reason=getattr(self, "_rotate_reason", None)
                )
            return {
                "agent_id": self.agent_id,
                "public_key": pub,
                "created": False,
            }
        key = nacl.signing.SigningKey.generate()
        seed = bytes(key)
        pub = bytes(key.verify_key)
        if FERNET_AVAILABLE:
            fernet = Fernet(self._derive_key(self._password))
            encrypted = fernet.encrypt(seed)
            self._seed_path.write_bytes(encrypted)
        else:
            logger.warning(
                "cryptography not installed; seed file stored unencrypted. "
                "Install with: pip install cryptography"
            )
            self._seed_path.write_bytes(seed)
        self._pub_path.write_bytes(pub)
        try:
            os.chmod(self._seed_path, 0o600)
        except OSError as e:
            logger.debug("keypair file not found: %s", e)
        self._signing_key = key
        self._verify_key = key.verify_key
        pub_hex = pub.hex()
        self._key_history.record_key(
            pub_hex, retire_reason=getattr(self, "_rotate_reason", None)
        )
        return {
            "agent_id": self.agent_id,
            "public_key": pub_hex,
            "created": True,
        }

    def has_keypair(self) -> bool:
        """Check if this agent has a keypair on disk."""
        return self._seed_path.exists() and self._pub_path.exists()

    def get_public_key(self) -> Optional[str]:
        """Return hex-encoded public key, or None if no keypair exists.

        Reads the .pub file directly if _verify_key is not loaded in memory.
        The .pub file is never encrypted, so this works even when the seed
        cannot be decrypted (e.g. wrong password).
        """
        if not self.has_keypair():
            return None
        if self._verify_key is None:
            self._load_keypair()
        if self._verify_key is not None:
            return bytes(self._verify_key).hex()
        try:
            pub_bytes = self._pub_path.read_bytes()
            if len(pub_bytes) == 32:
                return pub_bytes.hex()
        except OSError:
            pass
        return None

    def _load_keypair(self) -> None:
        """Load keypair from disk into memory (decrypt seed if encrypted).

        Supports three formats:
        1. New format: Fernet with random salt (.salt file exists)
        2. Legacy format: Fernet with deterministic salt (platform.node():path)
        3. Raw format: unencrypted 32-byte seed (auto-encrypts with new KDF)
        """
        if not self._seed_path.exists():
            return
        encrypted = self._seed_path.read_bytes()
        seed = None

        if FERNET_AVAILABLE:
            salt_path = self.keys_dir / f"{self.agent_id}.salt"
            if salt_path.exists():
                try:
                    fernet = Fernet(self._derive_key(self._password))
                    seed = fernet.decrypt(encrypted)
                except Exception:
                    pass
            if seed is None:
                try:
                    fernet_legacy = Fernet(self._derive_key_legacy())
                    seed = fernet_legacy.decrypt(encrypted)
                    logger.info(
                        "Migrating seed for agent '%s' from legacy to random-salt KDF",
                        self.agent_id,
                    )
                    self._migrate_seed(seed)
                except Exception:
                    pass

        if seed is None:
            if len(encrypted) == 32:
                seed = encrypted
                if FERNET_AVAILABLE:
                    logger.info(
                        "Encrypting raw seed for agent '%s' with random-salt KDF",
                        self.agent_id,
                    )
                    self._migrate_seed(seed)
            else:
                return
        if len(seed) != 32:
            return
        try:
            self._signing_key = nacl.signing.SigningKey(seed)
            self._verify_key = self._signing_key.verify_key
        except Exception:
            self._signing_key = None
            self._verify_key = None

    def sign_entry(self, entry_hash: str) -> str:
        """Sign an entry's hash with this agent's private key."""
        if not NACL_AVAILABLE:
            raise RuntimeError("PyNaCl is required for signing")
        if not self.has_keypair():
            raise ValueError("No keypair exists; call generate_keypair() first")
        if self._signing_key is None:
            self._load_keypair()
        if self._signing_key is None:
            raise ValueError("Failed to load keypair")
        current_pub = (
            bytes(self._verify_key).hex() if self._verify_key else None
        )
        if current_pub and self._key_history.is_revoked(current_pub):
            raise ValueError("Active key is revoked; generate a new keypair")
        msg = entry_hash.encode("utf-8")
        sig = self._signing_key.sign(msg)
        return sig.signature.hex()

    def sign_receipt(self, receipt_hash: str) -> str:
        """Sign a TaskReceipt's hash. Same as sign_entry."""
        return self.sign_entry(receipt_hash)

    def verify_signature(self, data_hash: str, signature: str, public_key: str) -> dict:
        """Verify an ed25519 signature against a public key."""
        if not NACL_AVAILABLE:
            raise RuntimeError("PyNaCl is required for verification")
        try:
            pub_bytes = bytes.fromhex(public_key)
            sig_bytes = bytes.fromhex(signature)
        except ValueError:
            return {"valid": False, "public_key": public_key, "data_hash": data_hash}
        if len(pub_bytes) != 32 or len(sig_bytes) != 64:
            return {"valid": False, "public_key": public_key, "data_hash": data_hash}
        try:
            vk = nacl.signing.VerifyKey(pub_bytes)
            msg = data_hash.encode("utf-8")
            signed = sig_bytes + msg
            vk.verify(signed)
            return {"valid": True, "public_key": public_key, "data_hash": data_hash}
        except Exception:
            return {"valid": False, "public_key": public_key, "data_hash": data_hash}

    def rotate_key(self, reason: str = "routine rotation") -> dict:
        """Generate a new keypair, retiring the old one.

        S-2 fix: the old key is recorded as 'retired' in the key history.
        Old signatures remain verifiable via verify_with_history().
        The old seed is securely overwritten.

        Args:
            reason: Human-readable reason for rotation (stored in history).

        Returns:
            Dict with agent_id, old_public_key, new_public_key.
        """
        if not NACL_AVAILABLE:
            raise RuntimeError("PyNaCl is required for signing")
        old_pub = self.get_public_key()
        self._rotate_reason = reason
        result = self.generate_keypair(force=True)
        self._rotate_reason = None
        return {
            "agent_id": self.agent_id,
            "old_public_key": old_pub,
            "new_public_key": result["public_key"],
            "reason": reason,
        }

    def revoke_key(self, public_key: str, reason: str = "compromised") -> bool:
        """Revoke a public key. Signatures with this key should no longer be trusted.

        S-2 fix: marks the key as 'revoked' in the key history.
        If the revoked key is the current active key, a new key must be generated
        afterwards (this method does NOT auto-generate a replacement).

        Returns:
            True if the key was found and revoked, False if not found.
        """
        revoked = self._key_history.revoke_key(public_key, reason)
        if revoked:
            if (
                self._verify_key is not None
                and bytes(self._verify_key).hex() == public_key
            ):
                self._signing_key = None
                self._verify_key = None
            logger.info(
                "Revoked key %s... for agent '%s': %s",
                public_key[:16],
                self.agent_id,
                reason,
            )
        return revoked

    def verify_with_history(
        self, data_hash: str, signature: str, public_key: str
    ) -> dict:
        """Verify a signature, checking revocation status from key history.

        Returns:
            valid (crypto and not revoked), crypto_valid, revoked, key_status, ...
        """
        crypto_result = self.verify_signature(data_hash, signature, public_key)
        revoked = self._key_history.is_revoked(public_key)
        key_status = None
        for entry in self._key_history.entries:
            if entry["public_key"] == public_key:
                key_status = entry.get("status")
                break
        return {
            "valid": crypto_result["valid"] and not revoked,
            "crypto_valid": crypto_result["valid"],
            "revoked": revoked,
            "key_status": key_status,
            "public_key": public_key,
            "data_hash": data_hash,
        }

    @property
    def key_history(self) -> list:
        """Return the key history entries (read-only copy)."""
        return self._key_history.entries

    def verify_key_history_chain(self) -> dict:
        """Verify the hash chain integrity of this agent's key history."""
        return self._key_history.verify_chain()


def load_public_key(keys_dir: str, agent_id: str) -> Optional[str]:
    """Load an agent's public key from disk without loading the private key."""
    path = Path(keys_dir) / f"{agent_id}.pub"
    if not path.exists():
        return None
    try:
        pub = path.read_bytes()
        return pub.hex() if len(pub) == 32 else None
    except Exception:
        return None


def import_public_key(keys_dir: str, agent_id: str, public_key_hex: str) -> str:
    """Import another agent's public key for verification. Writes {agent_id}.pub."""
    keys_path = Path(keys_dir)
    keys_path.mkdir(parents=True, exist_ok=True)
    try:
        raw = bytes.fromhex(public_key_hex)
    except ValueError:
        raise ValueError("public_key_hex must be 64 hex chars (32 bytes)")
    if len(raw) != 32:
        raise ValueError("public_key_hex must be 32 bytes (64 hex chars)")
    out = keys_path / f"{agent_id}.pub"
    out.write_bytes(raw)
    return str(out)
