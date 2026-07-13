# BIND_PRIMITIVE — Canonical Whole-Object Binding

- **Status:** Proposed (P1, spec-only). No implementation here.
- **Date:** 2026-06-12
- **Normative deps:** ADR-0002 (canonical hashing v1)
- **Eliminates:** audit findings H1–H4 (security fields left outside the hash/sig),
  by construction.

The audit's H1–H4 all share one root cause: each construct hashed/signed a
**hand-picked concatenation of fields**, and the security-relevant field
(key-history `status`, attestation `dispatch_hash`, dispatch agent IDs, seal
contents) was simply not in the list. `bind()` removes the list: it signs the
**entire canonical object minus the signature envelope**, with domain separation.

---

## 1. Definition

```
bind(domain: str, obj: Mapping) -> Bound

# 1. strip the signature envelope fields from obj
core      = { k: v for k, v in obj if k not in SIGNATURE_FIELDS }
# 2. canonicalise the WHOLE remaining object (ADR-0002: sorted keys, UTF-8,
#    separators (",",":"), no NaN/Inf) — recursively, nested maps included
canonical = canonical_json(core)                      # bytes
# 3. domain-separate and hash
preimage  = domain_utf8 || 0x00 || canonical
digest    = SHA-256(preimage)                          # bytes32
# 4. sign
signature = Ed25519(signing_key, digest)
return Bound(domain, digest_hex, signature, public_key)

SIGNATURE_FIELDS = { "signature", "public_key", "cosignatures", "bound_hash" }
```

## 2. Rules (normative)

- **R1 — whole object.** Every field of `core` is covered. There is no per-call
  allowlist of "fields to hash". Adding a field to a record automatically puts it
  under the signature; forgetting it is impossible.
- **R2 — domain separation.** `domain` (e.g. `"dsm.sth.v1"`, `"dsm.attestation.v1"`,
  `"dsm.dispatch.v1"`, `"dsm.keyhistory.v1"`, `"dsm.seal.v1"`) is prepended with a
  `0x00` separator so a signature for one record type can never be replayed as
  another. Variable-length `domain` + `0x00` delimiter prevents the L1
  concatenation-collision class.
- **R3 — one canonicaliser.** Uses the existing ADR-0002 `canonical_json`. No
  second wire format is introduced for signing (text envelopes are transport only).
- **R4 — verification recomputes over the full object.** `verify_bound(obj, bound)`
  recomputes `bind(bound.domain, obj)` and checks equality + Ed25519. A verifier
  cannot be tricked into checking a subset.
- **R5 — versioned domains.** Any change to a record's schema bumps its domain
  suffix (`...v1` → `...v2`); old records verify under the old domain (read-only).

## 3. Migration of the H1–H4 constructs (target end-state, P2)

| Construct | P0/audit state | P1 target via `bind()` |
|---|---|---|
| Key history entry | `status` hashed as literal `"active"` (H1) | `bind("dsm.keyhistory.v1", entry)` covers real `status`, `retired_at`, `reason` |
| Attestation | `dispatch_hash`/`entry_hash` excluded (H2) | `bind("dsm.attestation.v1", att)` covers all fields incl. causal pointers |
| Dispatch | agent IDs excluded (H3) | `bind("dsm.dispatch.v1", rec)` covers dispatcher/target IDs |
| Seal | unsigned SHA of public values (H4) | `bind("dsm.seal.v1", seal)` → **signed** seal; `verify` checks signature |

These rewrites are **P2 implementation work**, listed here only to show the
primitive discharges the whole class. No code is changed in P1.

## 4. Properties (P-BIND)

- **Coverage:** for any record `r` and any field `f ∈ core(r)`, flipping `f`
  changes `digest`, hence breaks the signature.
- **Non-malleability:** Ed25519 over a fixed 32-byte digest; combined-message form
  per existing DSM signing.
- **Cross-type safety:** domain separation makes `verify_bound` reject a signature
  minted for a different `domain`.

## 5. Test obligations

Coverage (every field matters), domain-separation cross-type rejection, nested-map
canonicalisation, and signature-field-stripping are enumerated in
[`P1_MODEL_TESTS.md`](../tests/P1_MODEL_TESTS.md) §6.
