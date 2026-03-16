# P9: Entry Signing & Artifact Store (Provable Authorship + Provable Evidence)

**Status:** Ready for implementation
**Target test count:** 214 (199 + 15 new tests)
**Estimated LOC:** 500 (200 signing + 200 artifacts + 100 tests)
**Dependencies:** `PyNaCl` (ed25519 signing)

---

## Problem

DSM v0.4.0 proves the log wasn't tampered with (hash chain) and the intent wasn't fabricated retroactively (P4 pre-commitment). But two critical gaps remain:

### Gap 1: Authorship is unproven

**Current state:** Any process with write access to a shard file can append entries. The `source` field is a plain string — there's no cryptographic proof that agent_id "alpha" actually wrote entry X.

```python
# Today: anyone can forge this
entry = Entry(source="alpha", content="I transferred 500 USDC", ...)
storage.append(entry)
# Nothing proves "alpha" wrote this. Could be "beta" impersonating.
```

**Impact on P6 (receipts):** `TaskReceipt.issuer_agent_id` is a string. Agent A receives a receipt claiming to be from Agent B — but there's no signature proving B created it. In multi-agent systems with real value (financial transactions, task delegation), this is a security hole.

**Community feedback:** @ChaosBot_AI — "let the agent sign a statement about what it remembers, then verify that signature against the log"

### Gap 2: Evidence is hash-only

**Current state:** P4 `capture_environment()` stores a SHA-256 hash of the raw data the agent observed. This proves "the agent saw *something* with this hash" — but the raw data is discarded. Later verification can only check "does the hash exist?" not "does the agent's claim match what it actually saw?"

```python
# Today: we store the hash but not the data
env = capture_environment(anchor_log, "api.example.com", raw_response)
# env["env_hash"] = "abc123..."
# But raw_response is gone. Can't re-verify what the agent actually observed.
```

**Impact:** An agent can say "the API returned price=$100" while the actual response said price=$50. The hash proves *a* response was captured, but without the raw data, nobody can check if the agent's summary is honest.

**Community feedback:** @Nova33 — "store a hash of the request payload + raw response blob, link the agent's summary/claim to the artifact hash"

---

## Solution

Two new modules that compose with existing DSM features:

### 1. Entry Signing (`src/dsm/signing.py`)

Each agent gets an **ed25519 keypair**. Every DSM entry and every TaskReceipt is **signed** by the authoring agent. Verification is instant and offline.

**Key insight:** Signing doesn't replace hash chains — it adds an orthogonal guarantee. Hash chain = "the log wasn't modified". Signature = "this specific agent created this entry". Both are needed for multi-agent trust.

### 2. Artifact Store (`src/dsm/artifacts.py`)

A **content-addressable store** for raw I/O data. When an agent calls an API, the raw response is stored as an artifact. DSM entries reference artifact hashes. Third parties can re-verify that the agent's claims match the raw evidence.

**Key insight:** Artifacts are optional and composable. Agents that don't need evidence storage skip it. Agents that need provable evidence (financial, compliance, safety-critical) add it in one method call.

---

## Implementation Specification

### Files to Create

1. **`src/dsm/signing.py`** (~200 lines)

2. **`src/dsm/artifacts.py`** (~200 lines)

3. **`tests/test_signing.py`** (~100 lines, 8 tests)

4. **`tests/test_artifacts.py`** (~100 lines, 7 tests)

### Files to Modify

5. **`src/dsm/agent.py`** — Add 6 new methods + `_signing` and `_artifact_store` attributes

6. **`src/dsm/cli.py`** — Add 4 new CLI commands

---

## API Specification

### AgentSigning Class (`src/dsm/signing.py`)

```python
import hashlib
import json
import os
from pathlib import Path
from typing import Optional


class AgentSigning:
    """Ed25519 signing for DSM entries and receipts.

    Keypair is stored in keys_dir as {agent_id}.seed (32 bytes)
    and {agent_id}.pub (32 bytes). Generated once, reused forever.
    """

    def __init__(self, keys_dir: str, agent_id: str):
        """
        Initialize signing for an agent.

        Args:
            keys_dir: Directory to store keypair files
            agent_id: Agent identifier (used for key filenames)
        """
        self.keys_dir = Path(keys_dir)
        self.keys_dir.mkdir(parents=True, exist_ok=True)
        self.agent_id = agent_id
        self._seed_path = self.keys_dir / f"{agent_id}.seed"
        self._pub_path = self.keys_dir / f"{agent_id}.pub"
        self._signing_key = None
        self._verify_key = None

    def generate_keypair(self, force: bool = False) -> dict:
        """
        Generate ed25519 keypair for this agent.

        If keypair exists and force=False, returns existing public key.
        Writes {agent_id}.seed and {agent_id}.pub to keys_dir.

        Args:
            force: Overwrite existing keypair if True

        Returns:
            {"agent_id": str, "public_key": str (hex), "created": bool}
        """

    def has_keypair(self) -> bool:
        """Check if this agent has a keypair on disk."""

    def get_public_key(self) -> Optional[str]:
        """
        Return hex-encoded public key, or None if no keypair exists.

        Returns:
            str: 64-char hex string (32 bytes ed25519 public key)
        """

    def sign_entry(self, entry_hash: str) -> str:
        """
        Sign an entry's hash with this agent's private key.

        Args:
            entry_hash: The SHA-256 hash of the DSM entry

        Returns:
            str: 128-char hex string (64 bytes ed25519 signature)

        Raises:
            ValueError: If no keypair exists
        """

    def sign_receipt(self, receipt_hash: str) -> str:
        """
        Sign a TaskReceipt's hash with this agent's private key.

        Identical to sign_entry — both sign a SHA-256 hex string.
        Separate method for semantic clarity.

        Args:
            receipt_hash: The receipt_hash from TaskReceipt

        Returns:
            str: 128-char hex string (64 bytes ed25519 signature)
        """

    def verify_signature(self, data_hash: str, signature: str, public_key: str) -> dict:
        """
        Verify an ed25519 signature against a public key.

        This is a static verification — works offline, doesn't need
        access to the signer's private key.

        Args:
            data_hash: The hash that was signed (entry_hash or receipt_hash)
            signature: 128-char hex signature
            public_key: 64-char hex public key of the claimed signer

        Returns:
            {"valid": bool, "public_key": str, "data_hash": str}
        """


def load_public_key(keys_dir: str, agent_id: str) -> Optional[str]:
    """
    Load an agent's public key from disk without loading the private key.

    Used by verifiers who have a copy of the public key but not the seed.

    Args:
        keys_dir: Directory containing key files
        agent_id: Agent whose public key to load

    Returns:
        str: hex-encoded public key, or None
    """


def import_public_key(keys_dir: str, agent_id: str, public_key_hex: str) -> str:
    """
    Import another agent's public key for verification.

    Writes {agent_id}.pub to keys_dir. Does NOT write a seed file.
    Used when Agent A wants to verify Agent B's signatures.

    Args:
        keys_dir: Directory to store key files
        agent_id: The remote agent's ID
        public_key_hex: 64-char hex public key

    Returns:
        str: Path to the written .pub file
    """
```

### ArtifactStore Class (`src/dsm/artifacts.py`)

```python
import hashlib
import gzip
import json
import os
from pathlib import Path
from typing import Optional, Union


class ArtifactStore:
    """Content-addressable store for raw I/O data.

    Layout:
        artifact_dir/
            ab/abc123def456...bin.gz   # gzipped raw bytes
            ab/abc123def456...meta.json # metadata

    Files are named by SHA-256 hash of content (like git objects).
    First 2 chars of hash used as subdirectory for filesystem friendliness.
    All artifacts are gzip-compressed by default.
    """

    def __init__(self, artifact_dir: str):
        """
        Initialize artifact store.

        Args:
            artifact_dir: Root directory for artifact storage
        """
        self.artifact_dir = Path(artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)

    def store(
        self,
        raw_data: Union[str, bytes, dict],
        source: str,
        artifact_type: str = "response",
        metadata: Optional[dict] = None,
    ) -> dict:
        """
        Store raw data as a content-addressable artifact.

        Args:
            raw_data: Raw bytes, string, or dict to store
            source: Where this data came from (e.g. "api.example.com")
            artifact_type: "request", "response", "observation", etc.
            metadata: Optional extra metadata

        Returns:
            {
                "artifact_hash": str,    # SHA-256 of raw content
                "size_bytes": int,       # Original size
                "compressed_bytes": int, # Gzipped size
                "source": str,
                "artifact_type": str,
                "stored_at": str,        # ISO timestamp
                "path": str              # Relative path within artifact_dir
            }

        Behavior:
            - If artifact with same hash already exists, returns existing
              metadata without re-writing (deduplication).
            - Writes .bin.gz (gzipped content) and .meta.json (metadata)
            - Uses fsync for durability
        """

    def retrieve(self, artifact_hash: str) -> Optional[bytes]:
        """
        Retrieve raw bytes for an artifact by hash.

        Args:
            artifact_hash: SHA-256 hash of the artifact

        Returns:
            bytes: Decompressed raw content, or None if not found
        """

    def get_metadata(self, artifact_hash: str) -> Optional[dict]:
        """
        Get metadata for an artifact without reading its content.

        Args:
            artifact_hash: SHA-256 hash of the artifact

        Returns:
            dict: Metadata from .meta.json, or None if not found
        """

    def exists(self, artifact_hash: str) -> bool:
        """Check if an artifact exists in the store."""

    def verify_artifact(self, artifact_hash: str) -> dict:
        """
        Verify artifact integrity: decompress, rehash, compare.

        Returns:
            {
                "artifact_hash": str,
                "status": "INTACT" | "CORRUPTED" | "MISSING",
                "size_bytes": int | None
            }
        """

    def link_to_entry(self, artifact_hash: str, entry_id: str) -> dict:
        """
        Record that a DSM entry references this artifact.

        Appends entry_id to the artifact's .meta.json "linked_entries" list.
        Used for garbage collection: artifacts with no linked entries can
        be safely deleted.

        Returns:
            {"artifact_hash": str, "entry_id": str, "linked_entries_count": int}
        """

    def list_artifacts(self, limit: int = 100) -> list:
        """
        List artifacts in the store (most recent first).

        Returns:
            [{"artifact_hash": str, "source": str, "size_bytes": int,
              "stored_at": str, "artifact_type": str}, ...]
        """

    def stats(self) -> dict:
        """
        Aggregate statistics for the artifact store.

        Returns:
            {
                "total_artifacts": int,
                "total_bytes_raw": int,
                "total_bytes_compressed": int,
                "compression_ratio": float
            }
        """
```

### DarylAgent Integration

Add to `__init__`:
```python
def __init__(self, ..., signing_dir: Optional[str] = None, artifact_dir: Optional[str] = None):
    # ... existing init ...
    self._signing = (
        AgentSigning(signing_dir or str(self.data_dir / "keys"), self.agent_id)
        if signing_dir is not False  # None = default dir, False = disabled
        else None
    )
    self._artifact_store = (
        ArtifactStore(artifact_dir or str(self.data_dir / "artifacts"))
        if artifact_dir is not False
        else None
    )
```

Add 6 new methods:
```python
def generate_keys(self, force: bool = False) -> dict:
    """Generate ed25519 keypair for this agent. Idempotent."""
    if self._signing is None:
        raise ValueError("Signing is disabled")
    return self._signing.generate_keypair(force=force)

def public_key(self) -> Optional[str]:
    """Return this agent's public key (hex), or None."""
    if self._signing is None:
        return None
    return self._signing.get_public_key()

def import_agent_key(self, agent_id: str, public_key_hex: str) -> str:
    """Import another agent's public key for receipt verification."""
    if self._signing is None:
        raise ValueError("Signing is disabled")
    return import_public_key(
        str(self.data_dir / "keys"), agent_id, public_key_hex
    )

def store_artifact(
    self, raw_data, source: str,
    artifact_type: str = "response",
    metadata: Optional[dict] = None,
) -> dict:
    """Store raw I/O data in content-addressable artifact store."""
    if self._artifact_store is None:
        raise ValueError("Artifact store is disabled")
    return self._artifact_store.store(raw_data, source, artifact_type, metadata)

def retrieve_artifact(self, artifact_hash: str) -> Optional[bytes]:
    """Retrieve raw bytes for an artifact by hash."""
    if self._artifact_store is None:
        raise ValueError("Artifact store is disabled")
    return self._artifact_store.retrieve(artifact_hash)

def verify_artifact(self, artifact_hash: str) -> dict:
    """Verify artifact integrity."""
    if self._artifact_store is None:
        raise ValueError("Artifact store is disabled")
    return self._artifact_store.verify_artifact(artifact_hash)
```

### Modified `intend()` and `confirm()` methods

```python
def intend(self, action_name: str, params: Optional[dict] = None) -> Optional[str]:
    # ... existing logic ...
    # NEW: sign the entry if signing is enabled
    if self._signing and self._signing.has_keypair() and entry:
        try:
            signature = self._signing.sign_entry(entry.hash)
            # Store signature in entry metadata
            # (append a signature record to anchor log)
            self._anchor_log._append_record({
                "type": "entry_signature",
                "entry_id": entry.id,
                "entry_hash": entry.hash,
                "signature": signature,
                "public_key": self._signing.get_public_key(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            pass  # signing failure should not block agent
    return intent_id

def confirm(self, intent_id, result=None, success=True, raw_input=None) -> Optional[Any]:
    # ... existing logic ...
    # NEW: auto-store raw_input as artifact if artifact store is enabled
    if self._artifact_store and raw_input is not None:
        try:
            artifact = self._artifact_store.store(
                raw_input, source=f"confirm:{intent_id}",
                artifact_type="raw_input",
            )
            # Link artifact to the confirmed entry
            # (stored in entry metadata or anchor log)
        except Exception:
            pass  # artifact failure should not block agent
```

### Modified `issue_receipt()` method

```python
def issue_receipt(self, entry_id: str, shard_id: str, task_description: str) -> dict:
    receipt = issue_receipt_fn(self._storage, self.agent_id, entry_id, shard_id, task_description)
    result = receipt.to_dict()
    # NEW: sign the receipt if signing is enabled
    if self._signing and self._signing.has_keypair():
        try:
            result["signature"] = self._signing.sign_receipt(receipt.receipt_hash)
            result["public_key"] = self._signing.get_public_key()
        except Exception:
            pass
    return result
```

### CLI Commands

```bash
# Generate keypair for an agent
dsm keygen --agent-id <agent_id> [--keys-dir <path>] [--force]
# Output: "✓ Generated ed25519 keypair for agent_id. Public key: abc123..."

# Show agent's public key
dsm pubkey --agent-id <agent_id> [--keys-dir <path>]
# Output: "abc123def456..." (hex, machine-readable)

# Store an artifact from stdin or file
dsm artifact-store --source <source> [--type response] [--file <path>]
# Output: "✓ Stored artifact abc123... (1.2 KB → 0.4 KB gzip)"

# Verify an artifact's integrity
dsm artifact-verify <artifact_hash>
# Output: "✓ Artifact abc123... INTACT (1.2 KB)"
```

---

## Test Cases (15)

### Entry Signing (8 tests)

- `test_generate_keypair_creates_files` — .seed and .pub files created in keys_dir
- `test_generate_keypair_idempotent` — second call with force=False returns existing key
- `test_sign_entry_returns_valid_signature` — signature is 128-char hex
- `test_verify_signature_valid` — verify_signature returns {"valid": True} for correct key
- `test_verify_signature_wrong_key` — returns {"valid": False} with different public key
- `test_verify_signature_tampered_hash` — returns {"valid": False} if hash is modified
- `test_sign_and_verify_receipt` — sign_receipt + verify_signature roundtrip
- `test_import_public_key_for_remote_agent` — import key, verify signature from remote agent

### Artifact Store (7 tests)

- `test_store_and_retrieve_bytes` — store raw bytes, retrieve identical bytes
- `test_store_and_retrieve_dict` — store dict, retrieve JSON bytes
- `test_store_deduplication` — same content stored twice → same hash, no duplicate files
- `test_verify_artifact_intact` — verify returns INTACT for valid artifact
- `test_verify_artifact_corrupted` — corrupt .bin.gz, verify returns CORRUPTED
- `test_verify_artifact_missing` — verify non-existent hash returns MISSING
- `test_link_to_entry` — link artifact to entry_id, verify linked_entries in metadata

---

## Implementation Notes

### Ed25519 Signing

- Use `nacl.signing` from PyNaCl (widely used, audited, pure-Python fallback)
- Seed file is 32 bytes, NOT the 64-byte expanded key
- Public key is 32 bytes = 64 hex chars
- Signature is 64 bytes = 128 hex chars
- **Security:** seed file should be chmod 600 (owner-only read). `generate_keypair()` sets file permissions.
- **No passphrase** for v1 — seed is stored in plaintext. Acceptable for agent-to-agent scenarios where the "agent" is a process, not a human.

### Artifact Store

- Content-addressable: filename = SHA-256 of raw bytes
- Two-char directory prefix: `ab/abc123...` (avoids filesystem issues with millions of files)
- Always gzip-compressed (`.bin.gz`) — typical 60-80% compression on JSON/text
- Metadata sidecar (`.meta.json`) stores source, type, timestamp, linked_entries
- **Deduplication is free:** same content = same hash = same file
- **Garbage collection:** artifacts with empty `linked_entries` can be pruned (future feature, not in P9)

### Backward Compatibility

- Signing is **optional**. Agents without keypairs work exactly as before.
- Artifact store is **optional**. Agents that don't call `store_artifact()` have no artifact_dir.
- Existing entries, receipts, and seals are unaffected.
- No changes to core kernel (`src/dsm/core/`).

### Composability with Existing Features

| Existing Feature | P9 Enhancement |
|-----------------|----------------|
| **P4 (Anchoring)** | `capture_environment()` now optionally stores raw data as artifact, not just hash |
| **P5 (Sealing)** | Seal can reference artifact hashes — "this shard + these artifacts were intact" |
| **P6 (Receipts)** | `issue_receipt()` now includes `signature` and `public_key` fields |
| **P7 (Index)** | Index can include artifact_hashes for evidence-backed queries |
| **P8 (Audit)** | Audit reports can reference artifacts as evidence for compliance claims |

---

## Example Usage

### Before P9 (trust the string):
```python
agent_b = DarylAgent("agent_b", "data_b", shard="tasks")
receipt = agent_b.issue_receipt(entry_id, "tasks", "Completed search")
# receipt = {"issuer_agent_id": "agent_b", "receipt_hash": "abc...", ...}
# Agent A receives this but has NO PROOF it came from agent_b

agent_a = DarylAgent("agent_a", "data_a")
result = agent_a.receive_receipt(json.dumps(receipt))
# result["integrity"] = "INTACT" — but INTACT only means the receipt wasn't modified,
# NOT that agent_b actually created it. Any agent could forge this.
```

### With P9 (cryptographic authorship):
```python
# Setup: each agent generates a keypair (once)
agent_b = DarylAgent("agent_b", "data_b", shard="tasks")
agent_b.generate_keys()
# → {"agent_id": "agent_b", "public_key": "b7c3e9...", "created": True}

# Agent B issues a SIGNED receipt
receipt = agent_b.issue_receipt(entry_id, "tasks", "Completed search")
# receipt now includes: "signature": "f4a2b1...", "public_key": "b7c3e9..."

# Agent A imports B's public key (once) and verifies
agent_a = DarylAgent("agent_a", "data_a")
agent_a.import_agent_key("agent_b", "b7c3e9...")
# → agent_a can now verify any signature from agent_b

# Verification: cryptographic proof of authorship
signing = AgentSigning("data_a/keys", "agent_a")
result = signing.verify_signature(
    receipt["receipt_hash"],
    receipt["signature"],
    receipt["public_key"]
)
# result = {"valid": True, ...}
# NOW Agent A has cryptographic proof that agent_b created this receipt.
```

### Artifact evidence:
```python
agent = DarylAgent("my_agent", "data")

# Agent calls an API
raw_response = requests.get("https://api.example.com/price").content

# Store the raw response as an artifact
artifact = agent.store_artifact(raw_response, source="api.example.com")
# artifact = {"artifact_hash": "de4f...", "size_bytes": 2048, ...}

# Agent records its action with artifact reference
intent_id = agent.intend("check_price", {"symbol": "ETH"})
agent.confirm(intent_id, result={"price": 3200}, raw_input=raw_response)
# raw_input is auto-stored as artifact if artifact store is enabled

# Later: third party can verify the agent's claim matches the raw evidence
raw = agent.retrieve_artifact("de4f...")
actual_response = json.loads(raw)
# Compare: does agent's claim (price=3200) match actual_response?
```

---

## Files Summary

| File | Type | Status |
|------|------|--------|
| `src/dsm/signing.py` | NEW | Implement (~200 lines) |
| `src/dsm/artifacts.py` | NEW | Implement (~200 lines) |
| `tests/test_signing.py` | NEW | Implement (8 tests) |
| `tests/test_artifacts.py` | NEW | Implement (7 tests) |
| `src/dsm/agent.py` | MODIFY | Add 6 methods + 2 attributes |
| `src/dsm/cli.py` | MODIFY | Add 4 commands |

Total: ~500 LOC + 15 tests → 214 tests total

---

## Success Criteria

✅ `generate_keypair()` creates valid ed25519 keypair
✅ `sign_entry()` + `verify_signature()` roundtrip works
✅ Forged signature (wrong key) is rejected
✅ `store()` + `retrieve()` returns identical bytes
✅ Deduplication: same content → same hash, no duplicate files
✅ `verify_artifact()` detects corruption
✅ Signed receipts include `signature` and `public_key`
✅ All 15 tests pass
✅ Total test count reaches 214 (199 + 15)
✅ No changes to core kernel
✅ Backward compatible: agents without keys/artifacts work as before

---

## Next Phase (P10)

After P9 ships:
- P10: Shard Encryption & Redaction — AES-256-GCM encrypted entries, selective redaction
- P10 builds on P9's keypair infrastructure for key management
- Addresses GDPR/privacy requirements identified by @homeclaw on Moltbook

---

## Attribution

This feature was directly inspired by Moltbook community feedback:
- **@ChaosBot_AI**: "let the agent sign a statement about what it remembers"
- **@Nova33**: "store a hash of the request payload + raw response blob"
- **@agentmoonpay**: "the chain IS the audit log" (financial use case for signed receipts)
