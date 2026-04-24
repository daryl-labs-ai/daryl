# dsm-primitives

Shared canonical serialization, hashing, and signing primitives for 
`daryl-dsm` and `agent-mesh`.

Implementation of [ADR-0002](../../docs/architecture/ADR_0002_DSM_PRIMITIVES.md).

## Install (editable, from the daryl monorepo)

```bash
pip install -e packages/dsm-primitives
```

## Public API

```python
from dsm_primitives import (
    canonical_json,      # dict -> UTF-8 bytes
    hash_canonical,      # dict -> "v1:<hex>"
    verify_hash,         # (dict, stored) -> bool (supports v0 + v1)
    sign,                # (bytes, private_key) -> signature bytes
    verify_signature,    # (bytes, signature, public_key) -> bool
)
```

## Spec highlights

- **Canonical JSON**: `sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False`
- **Unicode**: callers MUST normalize strings to NFC before hashing
- **Hash format**: `v1:<64 hex chars>`, e.g. `v1:1ec0cecbe6bfb7e3...`
- **Legacy v0**: bare hex, read-only via `verify_hash`, never produced
- **Unknown prefixes**: `verify_hash` returns `False` (fail closed)
- **Unsupported types** (bytes, datetime, set, custom objects): `TypeError`

See ADR-0002 for the full specification.

## Development

```bash
pip install -e "packages/dsm-primitives[dev]"
pytest packages/dsm-primitives/tests/
```

Reference vectors in `tests/hash_vectors_v1.json` are **immutable**. 
Any change to the spec requires a new version (v2+) and a new vectors file.
