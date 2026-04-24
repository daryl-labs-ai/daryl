"""Ed25519 signing primitives (thin wrappers around PyNaCl).

Per ADR-0002:
  - sign / verify_signature are the only exposed functions
  - No generate_keypair helper (key lifecycle belongs to the caller)
"""

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey


def sign(message: bytes, private_key: bytes) -> bytes:
    """Sign a message with an Ed25519 private key seed.

    Args:
        message: Bytes to sign.
        private_key: 32-byte Ed25519 seed.

    Returns:
        64-byte signature.

    Raises:
        ValueError: if private_key is not 32 bytes.
    """
    if not isinstance(private_key, (bytes, bytearray)) or len(private_key) != 32:
        raise ValueError("private_key must be 32 bytes")
    signer = SigningKey(bytes(private_key))
    signed = signer.sign(message)
    return signed.signature


def verify_signature(message: bytes, signature: bytes, public_key: bytes) -> bool:
    """Verify an Ed25519 signature.

    Args:
        message: Bytes that were signed.
        signature: 64-byte signature.
        public_key: 32-byte Ed25519 public key.

    Returns:
        True if signature is valid for this message and key, else False.
    """
    if not isinstance(public_key, (bytes, bytearray)) or len(public_key) != 32:
        return False
    if not isinstance(signature, (bytes, bytearray)) or len(signature) != 64:
        return False
    try:
        verifier = VerifyKey(bytes(public_key))
        verifier.verify(message, bytes(signature))
        return True
    except BadSignatureError:
        return False
    except Exception:
        return False
