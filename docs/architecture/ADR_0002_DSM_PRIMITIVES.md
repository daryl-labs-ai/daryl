# ADR-0002 : dsm-primitives — Shared canonical serialization, hashing and signing

**Status:** Proposed
**Date:** 2026-04-24
**Supersedes:** N/A
**Relates to:** ADR-0001 (RR as sole read path)

## Context

Two independent consumers produce cryptographic entries that must be verifiable
across systems:

- `daryl-dsm` (this repo) — hashes Entry records for the append-only chain in
  `src/dsm/core/storage.py:_compute_canonical_entry_hash`
- `agent-mesh` (sibling repo) — hashes payloads in
  `agent-mesh/src/agent_mesh/adapters/daryl_adapter/signing.py`

These implementations have **diverged byte-for-byte** on Unicode input.
Empirical reproduction (audit V4 §6.3):

```
payload = {"name": "café", "val": 1}
DSM:  b'{"name":"caf\\u00e9","val":1}'   hash: 1ec0cecbe6bfb7e3...
MESH: b'{"name":"caf\xc3\xa9","val":1}'  hash: 1cd4ebc93f5f4db1...
```

Root cause: `ensure_ascii=True` (DSM default) vs `ensure_ascii=False` (mesh).
Same logical input, different bytes, different hash. Any entry with non-ASCII
content (emoji, accented characters, non-Latin scripts) would be signed with
one hash in mesh and recorded with a different hash in DSM.

The repository currently has **6 duplicate sites** of canonical hash logic
(audit V4 §6.4). Beyond the agent-mesh divergence, internal DSM tracing/replay
paths also reimplement the same primitive.

## Decision

Create a new package `dsm-primitives` that becomes the **sole source of
canonical JSON serialization and cryptographic hashing** for both `daryl-dsm`
and `agent-mesh`.

### Location

`packages/dsm-primitives/` in the `daryl-labs-ai/daryl` monorepo.

Rationale: two independent consumers (daryl-dsm, agent-mesh) share this
package as a peer dependency. Placing it inside `src/dsm/` would force
agent-mesh to depend on the full daryl-dsm package, creating a hierarchical
coupling that contradicts the "protocol layer" purpose. Placing it in a
separate repository introduces publishing friction before the contract is
stable. Monorepo placement keeps iteration fast while making extraction to
a dedicated repo trivial when ready (`git filter-repo`).

### Public API

Five functions, exported from `dsm_primitives`:

```python
def canonical_json(data: dict) -> bytes:
    """Deterministic UTF-8 serialization of a dict for hashing."""

def hash_canonical(data: dict) -> str:
    """Compute v1 canonical hash. Returns 'v1:<hex>'."""

def verify_hash(data: dict, stored: str) -> bool:
    """Verify a stored hash against data. Supports v0 (legacy, no prefix)
    and v1 (current)."""

def sign(message: bytes, private_key: bytes) -> bytes:
    """Ed25519 signature."""

def verify_signature(message: bytes, signature: bytes, public_key: bytes) -> bool:
    """Ed25519 signature verification."""
```

No `generate_keypair` helper. Key generation and storage remain the
responsibility of the caller — keys are context-specific state, not primitives.

### Canonical JSON specification (v1)

```python
json.dumps(
    data,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=True,
    allow_nan=False,
).encode("utf-8")
```

Rationale for each flag:

- `sort_keys=True` — key ordering must be independent of dict construction order
- `separators=(",", ":")` — no whitespace, deterministic byte count
- `ensure_ascii=True` — all non-ASCII characters escaped to `\uXXXX`. Produces
  pure ASCII output, portable across any JSON parser or runtime. Eliminates
  the class of bugs that caused the DSM↔mesh divergence
- `allow_nan=False` — raises `ValueError` on NaN / Infinity / -Infinity.
  These values are not valid JSON (RFC 8259); allowing them produces output
  that non-Python parsers cannot read

### Unsupported types

Any value that is not natively serializable by Python's `json.dumps` with
the parameters defined above MUST raise a `TypeError`. No implicit coercion
is performed. Callers are responsible for converting such values to JSON-
native types (str, int, float, bool, None, list, dict) before invoking
`canonical_json` or `hash_canonical`.

Rationale: two independent implementations of a coercion rule will 
eventually diverge. Explicit conversion at the call site guarantees all
consumers produce byte-identical input.

### Unicode normalization

String values in input dicts MUST be Unicode-normalized to NFC (Canonical
Composition) before being passed to `canonical_json` or `hash_canonical`.
`dsm-primitives` does NOT perform normalization internally.

Rationale: the same visual character can have multiple valid Unicode
encodings (e.g., "é" as U+00E9 vs U+0065 + U+0301). Python's `json.dumps`
preserves whatever byte sequence is in the input string. Without 
normalization at the caller, two systems that intend to hash the same 
content will produce different hashes if they obtained the string from 
different sources (keyboard input, OS clipboard, external API, etc.).

Normalization is enforced at the caller because:
- `dsm-primitives` must not perform hidden transformations (see 
  "Unsupported types" for the same rationale)
- Most text pipelines already produce NFC (Web default, macOS since 
  10.4, Python `unicodedata.normalize`)
- Doing it centrally in primitives would silently correct non-conforming
  input and mask real schema problems

Consumers MAY normalize defensively with 
`unicodedata.normalize("NFC", s)` before passing data in, but are not 
required to do so if they already handle NFC upstream.

Reference vectors include a non-NFC variant of `"café"` (encoded as 
`"cafe\u0301"`) specifically to document that it produces a DIFFERENT 
hash than the NFC form. This is adversarial coverage — the non-NFC case 
is not supported input, the vector exists to make the consequence of 
non-compliance explicit and testable.

### Hash format

```
v1:<64 hex chars>
```

Example: `v1:1ec0cecbe6bfb7e3a8c9d2f1e0b5a6c7...`

The `v1:` prefix is part of the hash output and is included in chaining
(each entry's `prev_hash` field stores the full prefixed string). Rationale:
a cryptographic chain without version in its links is not self-descriptive,
forcing external inference of the format. Including the prefix (+3 bytes
per link) guarantees every link can route to the correct verification path
without global state.

### Legacy format (v0) — read-only

DSM entries created before this ADR exist in the form `<64 hex chars>` with
no prefix. These are called v0.

- `verify_hash(data, stored)` detects the absence of prefix and routes to the
  v0 verification path (bare sha256 over bytes produced by the pre-ADR
  canonical method — `ensure_ascii=True`)
- `hash_canonical(data)` **never produces v0**. Only v1. DSM legacy code that
  needs to produce v0 (during the transition window until all chains rotate)
  keeps its inline implementation; it does not call `dsm-primitives`

This asymmetry is intentional. It makes v0 a closing window — no code outside
DSM's legacy hash function produces v0, so v0 disappears naturally as new
chains are written.

### Entry schema (DSM-specific, documentary)

Consumers of `hash_canonical` pass a dict. For DSM Entry records, the dict
MUST contain exactly these keys in any order (sort_keys handles ordering):

```python
{
    "session_id": str,
    "source": str,
    "timestamp": str,        # ISO 8601 UTC
    "metadata": dict,
    "content": dict | str,
    "prev_hash": str | None,
}
```

Adding, removing, or renaming a field is a **breaking change**: it must bump
to a new hash version (v2) and cannot be done transparently. See "Breaking
change rule" below.

### Shared fixture and cross-package parity

`dsm-primitives` itself remains dependency-free and does not import its
consumers. It exposes:

- `packages/dsm-primitives/tests/hash_vectors_v1.json` — reference vectors
- `packages/dsm-primitives/tests/fixtures/canonical_entry.py` — 
  `CANONICAL_ENTRY_V1` constant, importable by consumers

Cross-package parity (DSM ↔ mesh ↔ primitives produce the same hash for 
the same Entry input) is enforced by an integration test that lives 
outside the package:

`tests/integration/test_hash_parity.py` (in `daryl-dsm` repo) imports:
- `dsm_primitives.hash_canonical`
- `dsm.core.storage._compute_canonical_entry_hash` (during transition) 
  or `dsm.core.storage.compute_entry_hash` (post-migration)
- `agent_mesh.adapters.daryl_adapter.signing.compute_content_hash` 
  (or its post-migration equivalent)

and asserts all three produce the same output for `CANONICAL_ENTRY_V1` 
and a set of additional fixtures. This test depends on all three 
packages being installed; it runs in the daryl-dsm CI.

If either consumer drifts from the spec or from the shared fixture, 
the integration test fails.

### Reference vectors

`packages/dsm-primitives/tests/hash_vectors_v1.json` contains committed
reference vectors: pairs of `(input_dict, expected_hash)` covering:

- Empty dict `{}`
- Single string ASCII: `{"s": "hello"}`
- Single string with accents (NFC): `{"s": "café"}` (U+00E9 for é)
- Single string with combining marks (non-NFC): `{"s": "cafe\u0301"}` 
  (must produce a DIFFERENT hash than the NFC form — documents the 
  normalization contract)
- Single string with emoji: `{"s": "🎉"}`
- String with JSON-sensitive Unicode: `{"s": "line1\u2028line2"}` 
  (U+2028 LINE SEPARATOR)
- Nested dicts: `{"a": {"b": {"c": 1}}}`
- Mixed types: `{"s": "x", "i": 1, "f": 1.5, "b": true, "n": null}`
- List of mixed types: `{"items": [1, "two", 3.0, null, false]}`
- Prev_hash = None: `{"prev_hash": null}`
- Prev_hash = v1 reference: `{"prev_hash": "v1:<64 hex>"}`

**Reference vectors are immutable.** Once this file is committed, its
contents MUST NEVER be modified. Any change to the canonical 
serialization or hash algorithm requires:
- Introduction of a new version (v2, v3, ...)
- Creation of a new vector file (`hash_vectors_v2.json`)
- v1 vectors remain valid for verifying v0/v1 entries forever

### Breaking change rule

Any of the following changes MUST be treated as a breaking change 
requiring a new hash version:

- Any modification to canonical JSON parameters (sort_keys, separators, 
  ensure_ascii, allow_nan)
- Any addition, removal, or renaming of a field in the DSM Entry schema
- Any change to Unicode normalization expectations
- Any change to hash algorithm (sha256 → blake3, etc.)

A new version (v2, v3, ...) means:
- New functions are not added to `dsm-primitives` (the API stays the 
  same: `hash_canonical` produces the current version's format)
- A new reference vector file is committed
- The prefix in hash output bumps (`v1:` → `v2:`)
- `verify_hash` gains a route for the new version while keeping v0/v1 
  routes functional

`hash_canonical` always produces the latest version (currently v1). 
Backward compatibility is ensured exclusively through `verify_hash`, 
which supports all previous versions. There is no `hash_canonical_v1` 
or version parameter — callers that want to hash never choose a version,
they always get the latest. Callers that want to verify always use 
`verify_hash`, which knows how to route.

This asymmetry is core to the design: new entries always use the 
current best algorithm; historical entries remain verifiable without 
special-casing in caller code.

Schema stability is a protocol-level guarantee, not an implementation 
detail.

## Consequences

### Positive

- One implementation of canonical JSON and hash, shared by DSM and mesh
- Unicode divergence bug eliminated
- Future algorithm migration (blake3, zk-friendly hashes) routed through
  version prefix without breaking historical chains
- API stability: function names don't embed the algorithm, survive all
  future version bumps

### Negative

- New package adds a dependency edge (daryl-dsm → dsm-primitives,
  agent-mesh → dsm-primitives)
- Agent-mesh loses its `"sha256:"` prefix convention (breaking change for
  any downstream that parses mesh signatures)
- DSM keeps a legacy v0 code path for historical chains — temporary debt
  that must eventually be removed (when all historical chains have rotated)

### Neutral

- The 5-function API is minimal by design. Future additions (e.g.,
  `generate_keypair`, streaming hashers) can be added without breaking
  existing callers

## Migration plan

Three successive PRs after this ADR is merged:

- **V4-A.1** — Create `packages/dsm-primitives/` with the 5-function API,
  tests, reference vectors, fixture. Does not touch DSM or mesh.
- **V4-A.2** — Migrate DSM: replace `_compute_canonical_entry_hash` in
  `src/dsm/core/storage.py` with `dsm_primitives.hash_canonical`. New
  entries produce v1 hashes. Existing chains remain v0 (read via
  `verify_hash`).
- **V4-A.3** — Migrate agent-mesh: replace `canonicalize_payload` and
  `compute_content_hash` with `dsm_primitives` calls. Cross-package
  parity test activates.

## Alternatives considered

1. **Keep duplicated implementations, document the divergence** — rejected.
   The Unicode divergence is an active bug. Leaving it is a choice to ship
   broken cross-system hashing.

2. **Single shared file copy-pasted into both repos** — rejected. Drift is
   inevitable. A test can detect it but fixing it requires two PRs each time.

3. **Domain-specific primitives (`hash_dsm_entry`, `hash_mesh_payload`)** —
   rejected. Mixes primitive crypto with domain schema. Moves the
   duplication problem from "how to hash" to "how to structure the dict
   before hashing". Keeping the primitive pure and documenting the expected
   dict schema separately is strictly better.

4. **Version prefix via function suffix (`hash_canonical_v1`)** — rejected.
   Pollutes API, requires introducing new function names on every algorithm
   change, breaks caller compatibility. Version-in-data is the standard
   approach (JWT alg header, multihash, TLS cipher suite negotiation).

5. **Versioning with `version="v0"` parameter** — rejected. Opens the door
   to accidentally producing v0 from new code paths. v0 must be a closing
   window, not an option.

6. **Location in `src/dsm/primitives/` (internal module)** — rejected. 
   Would force agent-mesh to depend on daryl-dsm, inverting the peer 
   relationship. Monorepo placement at `packages/` level keeps both 
   consumers as peers of the shared protocol layer.

## References

- RFC 8785 — JSON Canonicalization Scheme (JCS). Similar spirit, different
  choices on ensure_ascii. Not adopted because JCS specifies Number
  serialization rules that Python's `json.dumps` doesn't implement natively,
  and the incremental value over our spec is low for our use case
- [multihash](https://github.com/multiformats/multihash) — inspiration for
  version-in-data pattern
- ADR-0001 — establishes the pattern of enforcing architectural invariants
  via lint + spec. dsm-primitives follows the same pattern: spec figée here,
  cross-package parity test enforces conformance
