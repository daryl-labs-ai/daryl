"""
Entry Signing (P9) — Ed25519 signing for DSM entries and receipts.

Proves authorship: only the agent with the private key can produce
a valid signature for an entry hash or receipt hash.
Composes with hash chain (integrity) and P4 (intent).
"""

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import nacl.signing
    import nacl.encoding
    NACL_AVAILABLE = True
except ImportError:
    NACL_AVAILABLE = False


class AgentSigning:
    """Ed25519 signing for DSM entries and receipts.

    Keypair is stored in keys_dir as {agent_id}.seed (32 bytes)
    and {agent_id}.pub (32 bytes). Generated once, reused forever.
    """

    def __init__(self, keys_dir: str, agent_id: str):
        self.keys_dir = Path(keys_dir)
        self.keys_dir.mkdir(parents=True, exist_ok=True)
        self.agent_id = agent_id
        self._seed_path = self.keys_dir / f"{agent_id}.seed"
        self._pub_path = self.keys_dir / f"{agent_id}.pub"
        self._signing_key = None
        self._verify_key = None

    def generate_keypair(self, force: bool = False) -> dict:
        """Generate ed25519 keypair for this agent."""
        if not NACL_AVAILABLE:
            raise RuntimeError("PyNaCl is required for signing. Install with: pip install PyNaCl")
        if self._seed_path.exists() and self._pub_path.exists() and not force:
            self._load_keypair()
            return {
                "agent_id": self.agent_id,
                "public_key": self.get_public_key(),
                "created": False,
            }
        key = nacl.signing.SigningKey.generate()
        seed = bytes(key)
        pub = bytes(key.verify_key)
        self._seed_path.write_bytes(seed)
        self._pub_path.write_bytes(pub)
        try:
            os.chmod(self._seed_path, 0o600)
        except OSError:
            pass
        self._signing_key = key
        self._verify_key = key.verify_key
        return {
            "agent_id": self.agent_id,
            "public_key": pub.hex(),
            "created": True,
        }

    def has_keypair(self) -> bool:
        """Check if this agent has a keypair on disk."""
        return self._seed_path.exists() and self._pub_path.exists()

    def get_public_key(self) -> Optional[str]:
        """Return hex-encoded public key, or None if no keypair exists."""
        if not self.has_keypair():
            return None
        if self._verify_key is None:
            self._load_keypair()
        if self._verify_key is None:
            return None
        return bytes(self._verify_key).hex()

    def _load_keypair(self) -> None:
        """Load keypair from disk into memory."""
        if not self._seed_path.exists():
            return
        seed = self._seed_path.read_bytes()
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
