# MULTIVERSX_ANCHORING — On-chain Anchoring of STH Roots

- **Status:** Proposed (P1, spec-only). No implementation here.
- **Date:** 2026-06-12
- **Normative deps:** [`STH_SPEC.md`](./STH_SPEC.md), [`WITNESS_SPEC.md`](./WITNESS_SPEC.md)
- **Reuses:** the existing `src/dsm/multiversx/` client/backend (read-only from this
  spec's perspective — no code changes here).

Anchoring periodically commits an STH root to the MultiversX public ledger. This
gives a **public, immutable, independently-timestamped** record of the canonical
log state — the property that lets a verifier trust the timeline without trusting
the operator's clock, and that turns a receipt into something defensible to an
outside party.

---

## 1. What gets anchored

The minimal commitment: `{ origin, tree_size, root_hash, sth_hash }` where
`sth_hash = SHA-256(bind("dsm.sth.v1", STH))`. Anchoring `sth_hash` (not the raw
fields) keeps the on-chain payload tiny and fixed-size while still binding the full
checkpoint. The witnessed cosignatures are NOT put on-chain (cost); they travel in
the off-chain receipt.

## 2. Transaction shape

- A purpose-built anchoring transaction carries the commitment in its `data` field
  (or a minimal smart-contract call `anchor(origin_hash, tree_size, sth_hash)`).
- Sender: a dedicated DSM anchoring account (key in KMS/HSM, distinct from the STH
  signing key — compromise isolation).
- The mapping `origin → contract/account` MUST be published so any verifier can
  locate anchors independently.
- Reuses `src/dsm/multiversx` for submission/observation; **this document specifies
  the protocol, not the code**.

## 3. Timestamp semantics (P-TIMESTAMP)

An anchored STH "existed no later than" the **block timestamp** of the transaction
that included it. The chain provides the upper bound; the STH's own `timestamp`
field is advisory only. A verifier resolves the anchor, reads the including block's
time, and uses that as the authoritative "not-after" for the checkpoint.

## 4. Cadence & cost model

Anchoring every entry is prohibitively expensive; anchoring amortises one
transaction over many entries:

- **Trigger:** anchor when `tree_size` has advanced by ≥ `Δsize` **or** ≥ `Δtime`
  has elapsed since the last anchor, whichever first. Defaults (tunable):
  `Δsize = 1024` entries, `Δtime = 1 h`.
- **Cost:** one transaction per anchor → cost per entry ≈ `tx_cost / Δsize`. With
  `Δsize = 1024`, on-chain cost is amortised ~1000×.
- **Exposure window:** between two anchors, integrity rests on witnesses (§ WITNESS).
  The window is bounded by `min(Δsize entries, Δtime)`; deployments needing a
  tighter public bound lower `Δtime`.
- The cadence MUST be published so verifiers know the expected anchor frequency and
  can flag a stalled anchorer.

## 5. Finality & reorg handling

- An anchor is **provisional** until it reaches the configured finality depth
  (`finality_depth` blocks). Receipts referencing a not-yet-final anchor MUST be
  labelled provisional by the SDK.
- On a reorg shallower than `finality_depth`, the anchorer MUST re-submit the
  commitment and update the anchor reference. The STH itself is unchanged (it is
  already witness-cosigned); only its on-chain pointer moves.
- `finality_depth` is a published policy parameter (chain-dependent).

## 6. Anchor reference in a receipt

```
anchor_ref = {
    chain:        "multiversx-mainnet" | "multiversx-devnet",
    tx_hash:      str,
    block_nonce:  uint64,
    block_time:   rfc3339,
    sth_hash:     bytes32,   # MUST equal SHA-256(bind(...STH...)) in the receipt
    final:        bool,      # reached finality_depth
}
```

Verification: resolve `tx_hash` on the named chain, confirm it commits `sth_hash`
for the claimed `origin/tree_size`, and confirm `block` depth ≥ `finality_depth`
for `final = true`.

## 7. Failure modes

- **Anchorer offline:** new STHs remain witness-cosigned but un-anchored
  (provisional public timeline). The SDK MUST surface "last anchor age".
- **Chain congestion:** anchoring may lag; cadence guarantees become best-effort
  and MUST be reported, never silently relaxed.
- **Wrong-chain / replay:** `origin` + `sth_hash` binding prevents an anchor from
  one shard/log being replayed as another's.

## 8. Test obligations

Anchor commitment binding, timestamp-upper-bound semantics, reorg re-anchor,
provisional-vs-final labelling, and cadence reporting are enumerated in
[`P1_MODEL_TESTS.md`](../tests/P1_MODEL_TESTS.md) §5. (Model/contract-level; no live
mainnet calls in the test suite — fixtures reuse `tests/multiversx/fixtures`.)
