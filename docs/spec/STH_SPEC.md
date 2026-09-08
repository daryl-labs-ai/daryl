# STH_SPEC — Signed Tree Head (Checkpoint)

- **Status:** Proposed (P1, spec-only). No implementation here.
- **Date:** 2026-06-12
- **Normative deps:** [`MMR_SPEC.md`](./MMR_SPEC.md), [`BIND_PRIMITIVE.md`](./BIND_PRIMITIVE.md),
  [`WITNESS_SPEC.md`](./WITNESS_SPEC.md)

A Signed Tree Head (STH), a.k.a. *checkpoint*, is the operator's signed commitment
to the state of a shard's MMR at a point in time. It is the unit witnesses cosign
and anchoring pins on-chain. Format and discipline follow CT (RFC 6962 §3.5) and
the Sigsum / Go-checksum-database "note" model.

---

## 1. Contents

```
STH = {
    origin:     str,     # log + shard + algorithm namespace, e.g. "dsm.v2/<shard_id>/mmr-v1"
    tree_size:  uint64,  # number of leaves (= shard entry_count) committed
    root_hash:  bytes32, # MMR Root(tree_size) per MMR_SPEC §4
    timestamp:  str,     # RFC3339 UTC, issuance time (advisory; anchor is authoritative)
    key_id:     str,     # operator signing key identifier
}
signature = Ed25519 over bind("dsm.sth.v1", STH)   # see BIND_PRIMITIVE
```

- `origin` MUST encode the hashing version (`mmr-v1`) so a root is never
  interpreted under the wrong algorithm.
- `root_hash` is meaningless without `tree_size`; both are inside the signed body
  (and the root already binds size per `MMR_SPEC.md` §4).
- The STH is signed via the canonical `bind()` primitive — **the whole object** is
  covered, never a hand-picked subset (closes the H1–H4 class for checkpoints).

## 2. Origin / namespace

`origin = "dsm.v2/" + shard_id + "/mmr-v1"`. Witnesses and verifiers key their
state by `origin`, so two shards (or two algorithm versions) can never have their
checkpoints confused. Changing the MMR hashing or STH format MUST bump the suffix.

## 3. Issuance rules

The operator MUST:
1. Compute `Root(tree_size)` from the current MMR.
2. Never issue an STH whose `tree_size` is **less** than the largest previously
   issued STH for that `origin` (no rewind).
3. Never issue two STHs with the same `tree_size` and different `root_hash`
   (no equivocation). Doing so is detectable and is a transferable proof of
   misbehaviour (`WITNESS_SPEC.md` §5).
4. Issue checkpoints on a defined cadence (size- or time-triggered, e.g. every N
   appends or every T seconds) — see `MULTIVERSX_ANCHORING.md` §4 for how cadence
   interacts with anchoring cost.

## 4. Verification (by a verifier or witness)

Given `STH` + `signature`:
1. Recompute `bind("dsm.sth.v1", STH)` and verify the Ed25519 `signature` against
   the operator public key bound to `key_id` (via the P0 status-authenticated key
   history).
2. Reject if `key_id`'s key is revoked at `timestamp`.
3. For monotonicity/consistency, a verifier holding a previous `STH_prev` for the
   same `origin` MUST be able to obtain and verify a consistency proof
   `σ(STH_prev.tree_size, STH.tree_size)` (`MMR_SPEC.md` §6).

## 5. Serialization (canonical, human-inspectable)

STHs SHOULD serialize in the Sigsum/Go-note style — a small UTF-8 text block —
so they are greppable and diffable in logs and PRs:

```
dsm.v2/<shard_id>/mmr-v1
<tree_size>
<base64(root_hash)>
<rfc3339 timestamp>

— <key_id> <base64(signature)>
— <witness_id_1> <base64(cosig_1)>
— <witness_id_2> <base64(cosig_2)>
```

The bytes signed by `bind()` are the canonical-JSON encoding of the STH object
(deterministic per ADR-0002); the text block above is a transport/inspection
envelope, not the signed preimage. (Rationale: reuse the one canonicalisation we
already trust rather than introduce a second signed wire format.)

## 6. Storage & lifecycle

- STHs are appended to a dedicated, append-only `checkpoints` log per `origin`.
- The **latest witnessed+anchored** STH is the shard's public "tip of trust".
- An STH is never deleted; superseded STHs remain for consistency-proof chaining.

## 7. Test obligations

Signature coverage (every field), rewind rejection, equivocation detection, and
serialization round-trip are enumerated in [`P1_MODEL_TESTS.md`](../tests/P1_MODEL_TESTS.md) §3.
