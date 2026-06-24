# P1_MODEL_TESTS — Model & Property Test Plan (spec-only)

- **Status:** Proposed (P1, spec-only). **No test code here** — this enumerates the
  properties, vectors, and adversarial scenarios a P2 implementation MUST satisfy.
- **Date:** 2026-06-12
- **Covers:** MMR, STH, Witness, Anchoring, `bind()`.

Each item is written so it can later become an executable test (property-based
where noted, vector-based otherwise). "MUST pass" = acceptance gate for P2.

---

## 1. Conventions

- **Property test** = holds for randomized inputs (e.g. `hypothesis`): generate
  random append sequences, assert the property for all.
- **Vector test** = fixed known-answer inputs/outputs committed as fixtures.
- **Adversarial test** = construct the attack, assert detection (mirrors the P0
  red-before-green discipline).

## 2. MMR (`MMR_SPEC.md`)

- **2.1 Inclusion soundness (property).** For random `n` and every `i < n`, the
  inclusion proof verifies against `Root(n)`.
- **2.2 Inclusion completeness (adversarial).** Altering the entry, the index, or
  any path/peak hash makes verification fail.
- **2.3 Consistency soundness (property).** For random `m ≤ n`, `σ(m, n)` verifies
  and recomputes both `Root(m)` and `Root(n)`.
- **2.4 Anti-truncation (adversarial, the C1 successor).** Build size `n`, then
  present a size-`m < n` tree as "current"; `σ(n, m)` MUST be impossible to forge —
  no proof verifies — i.e. truncation is provably rejected to a third party.
- **2.5 Append immutability (property).** Appending leaf `n` does not change any
  `LeafHash(i)` or internal node for `i < n`.
- **2.6 Peak/bagging vectors.** Known-answer roots for `n ∈ {0,1,2,3,4,7,8,11,1000}`.
- **2.7 Second-preimage / domain separation (adversarial).** A crafted internal
  node MUST NOT be acceptable as a leaf (verifies the `0x00`/`0x01` prefixes).
- **2.8 Size binding.** Two trees with identical peak hashes but different
  `tree_size` produce different roots (the `0x02||size` wrapper).

## 3. STH (`STH_SPEC.md`)

- **3.1 Signature coverage (property).** Flipping any STH field
  (`origin/tree_size/root_hash/timestamp/key_id`) invalidates the signature.
- **3.2 Rewind rejection (adversarial).** Issuing `tree_size < last` for an
  `origin` is rejected by the issuance rule and by witnesses.
- **3.3 Equivocation detection (adversarial).** Two STHs, same `origin`+`tree_size`,
  different `root` → detected; the pair is a valid misbehaviour proof.
- **3.4 Serialization round-trip (vector).** The text envelope parses back to the
  exact canonical object that was signed.
- **3.5 Revoked-key rejection.** An STH signed by a key revoked at `timestamp` is
  rejected (depends on the P0 status-authenticated key history).

## 4. Witness (`WITNESS_SPEC.md`)

- **4.1 Cosign-only-on-consistency (property).** A witness emits a cosignature iff
  `σ(last, new)` verifies and `tree_size` is non-decreasing.
- **4.2 Rewind refusal (adversarial).** Presented a rewound/forked STH, the witness
  refuses and the refusal evidence is well-formed.
- **4.3 Quorum threshold (vector).** A receipt with `< k` valid cosignatures is
  "un-witnessed"; `≥ k` distinct valid → "witnessed". Duplicate-witness cosigs do
  not count twice.
- **4.4 Equivocation-proof construction (adversarial).** Given two conflicting
  witnessed STHs, the SDK produces a transferable proof any third party verifies.
- **4.5 No silent fallback.** When `< k` witnesses are reachable, the receipt is
  reported as un-witnessed, never silently upgraded.

## 5. Anchoring (`MULTIVERSX_ANCHORING.md`)

- **5.1 Commitment binding (vector).** `anchor_ref.sth_hash` equals
  `SHA-256(bind("dsm.sth.v1", STH))`; mismatched STH is rejected. Uses
  `tests/multiversx/fixtures` — **no live mainnet calls.**
- **5.2 Timestamp upper-bound.** Verification uses the including block time as
  "not-after"; the STH's own `timestamp` is not trusted over it.
- **5.3 Reorg re-anchor (model).** On a sub-finality reorg, the anchor reference is
  re-derived; the STH is unchanged.
- **5.4 Provisional vs final labelling.** Depth `< finality_depth` → `final=false`
  and surfaced as provisional.
- **5.5 Cadence reporting.** A stalled anchorer (age > expected cadence) is
  reported, never hidden.

## 6. `bind()` (`BIND_PRIMITIVE.md`)

- **6.1 Whole-object coverage (property).** For a random record and a random field,
  mutating that field breaks the signature (no field is "free").
- **6.2 Signature-field stripping (vector).** `signature/public_key/cosignatures`
  are excluded from the preimage; adding them back changes nothing.
- **6.3 Domain cross-type rejection (adversarial).** A `bind("dsm.dispatch.v1", …)`
  signature does not verify as `bind("dsm.attestation.v1", …)`.
- **6.4 Nested canonicalisation (property).** Reordering keys in a nested map does
  not change the digest (canonical form); changing a nested value does.
- **6.5 H1–H4 regression (adversarial).** Re-run the four audit attacks against the
  `bind()`-based constructs (revocation flip, dispatch-pointer swap, dispatch
  agent-id swap, seal forgery) — all MUST now fail.

## 7. Cross-cutting end-to-end (model)

- **7.1 Receipt verification happy path.** entry + inclusion proof + witnessed STH +
  final anchor → accepted without trusting producer or operator.
- **7.2 Truncation after issuance.** A receipt issued at size `n`, then the shard
  truncated to `m < n` → a later consistency check fails; the receipt's anchored
  STH still proves the entry existed at size `n`.
- **7.3 Pre-genesis honesty.** Entries before the genesis anchor are reported as
  "provable only relative to genesis", never as fully anchored.

## 8. Out of scope for P1

No runtime/integration tests are written in P1 (no `src/`, no `agent-mesh/`
changes). This document is the contract those P2 tests will implement.
