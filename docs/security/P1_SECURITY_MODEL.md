# P1 Security Model — DSM Transparency Log

- **Status:** Proposed (P1, spec-only)
- **Date:** 2026-06-12
- **Companion to:** [ADR-0003](../adr/ADR-0003-transparency-log.md) and the `docs/spec/*` documents
- **Purpose:** state precisely *what DSM v2 proves, to whom, and under which
  assumptions* — and what it still does not prove. This is the document a CISO,
  auditor, or regulator should read first.

---

## 1. Actors

| Actor | Role | Trust |
|---|---|---|
| **Producer (agent)** | appends entries; signs its own contributions | untrusted for completeness; trusted only to sign its own key material |
| **Log operator (DSM)** | maintains the MMR, issues STHs | **honest-but-curious to actively-malicious** — must not be able to hide a rewind/equivocation |
| **Witnesses** | independent parties that co-sign STHs after checking consistency | k-of-n assumed honest; diversity is the security parameter |
| **Anchor chain (MultiversX)** | public ledger holding STH roots | trusted for availability + immutability + ordering, not for content correctness |
| **Verifier (third party)** | checks a receipt/proof | trusts none of producer/operator individually; trusts the *witness quorum* + chain |

## 2. Adversary classes (and which mechanism stops each)

| # | Adversary capability | P0 result | P1 mechanism that discharges it |
|---|---|---|---|
| A1 | Edit a field in a stored entry | detected (hash mismatch) | MMR leaf hash (unchanged guarantee) |
| A2 | Reorder / insert entries | detected (chain break) | MMR structure + consistency proof |
| A3 | **Truncate** the tail of a shard | detected vs local pin | **STH `tree_size` monotonicity + consistency proof** (now provable to a third party, not just locally) |
| A4 | Rewrite shard **and** local pin together | **NOT** stopped in P0 | **Witness-cosigned STH** — the operator cannot get a quorum to cosign a tree that is not consistent with the previously cosigned one |
| A5 | **Equivocate** — show verifier X tree T and verifier Y a divergent tree T′ | not addressed | **Witness cosigning + anchoring** — a single honest witness (or the chain) exposes two STHs of the same size with different roots |
| A6 | Forge the issuance time of a checkpoint | not addressed | **MultiversX anchoring** — the on-chain inclusion block provides an independent upper-bound timestamp |
| A7 | Leave a security field outside a signature (H1–H4) | present | **`bind()`** — the whole canonical object is signed; no hand-maintained field list |
| A8 | Compromise the operator signing key | catastrophic | mitigated by **HSM/KMS custody + witness quorum** — a forged STH still fails witness consistency checks; key rotation via the (P0-fixed, status-authenticated) key history |

## 3. Properties guaranteed (stated as checkable claims)

Let `STH_n = {size=n, root=R_n, t}` be a witnessed, anchored checkpoint.

- **P-INCLUSION.** Given an entry `e`, an inclusion proof `π`, and `STH_n`, a
  verifier accepts iff `e` is the leaf at some index `< n` committed by `R_n`.
  (`MMR_SPEC.md` §5)
- **P-CONSISTENCY.** Given `STH_m` and `STH_n` with `m ≤ n`, a consistency proof
  `σ` proves the size-`m` tree is a **prefix** of the size-`n` tree. If no such
  `σ` exists, the operator rewound or rewrote history. (`MMR_SPEC.md` §6)
- **P-MONOTONICITY.** Witnesses only cosign `STH_n` if `n ≥ n_prev` for the last
  STH they cosigned **and** `σ(prev, n)` verifies. (`WITNESS_SPEC.md` §4)
- **P-NON-EQUIVOCATION.** Two validly witnessed STHs with the same `size` but
  different `root` are a transferable proof of operator misbehaviour. With anchoring,
  at most one root per size can be the canonical on-chain one. (`WITNESS_SPEC.md` §5)
- **P-TIMESTAMP.** An anchored `STH_n` existed no later than the block that
  included it. (`MULTIVERSX_ANCHORING.md` §3)
- **P-BIND.** For any signed DSM record, every security-relevant field is inside
  the signature; verification recomputes over the full canonical object.
  (`BIND_PRIMITIVE.md` §3)

## 4. Trust-boundary table (what reduces each assumption)

| Component | Assumption if used alone | Mechanism that reduces it |
|---|---|---|
| Local storage | may truncate/rewrite | consistency proof vs witnessed STH |
| Operator | may rewind/equivocate | witness quorum (k-of-n) |
| Witnesses | k honest of n | organisational diversity; public witness keys |
| Clock | may be forged | on-chain anchor block time |
| Operator key | may be stolen | HSM/KMS + witness consistency gate |
| Per-record fields | may be excluded from sig | `bind()` whole-object signing |

## 5. The end-to-end verification a third party performs

1. Fetch the receipt: `{entry, inclusion_proof π, STH_n, witness_cosignatures, anchor_ref}`.
2. Verify `bind()` signature(s) on the entry/contribution.
3. Verify `π` against `R_n` (P-INCLUSION).
4. Verify ≥ k witness cosignatures over `STH_n` (P-NON-EQUIVOCATION basis).
5. Verify `anchor_ref` resolves on MultiversX to `R_n` at/after `t` (P-TIMESTAMP).
6. (Optional, stronger) fetch a later `STH_m`, verify consistency `σ(n, m)`
   (P-CONSISTENCY) to confirm the entry is still in the canonical history.

If all pass, the verifier accepts **without trusting the producer or the
operator**.

## 6. Residual risks (stated honestly)

- **Pre-genesis history.** Entries appended before the first anchored STH are only
  provable relative to that genesis anchor. DSM does **not** claim retroactive
  proof of pre-anchor history. This must be stated in any compliance narrative.
- **Witness collusion.** If more than `n − k` witnesses collude with the operator,
  equivocation can be hidden. Security scales with witness diversity, not code.
- **Anchor-chain liveness/reorg.** Between anchors there is an exposure window;
  before finality, an anchor can reorg. `MULTIVERSX_ANCHORING.md` §5 defines the
  finality depth and anchor cadence that bound this.
- **Data truthfulness & computation correctness.** Unchanged from P0: DSM proves
  *integrity and completeness of the record*, never that the recorded data was
  true or the agent's computation correct (that needs TEEs).
- **Key custody.** A stolen operator key plus a quorum of colluding witnesses
  breaks the model; neither alone does.
- **Availability ≠ integrity.** A withholding operator can deny service (refuse to
  produce proofs) without breaking integrity. Mitigation is operational
  (replication), not cryptographic.

## 7. Compliance positioning (defensible language)

DSM v2 provides a **witnessed, anchored, tamper-evident execution log** suitable
as a *building block* for traceability obligations (e.g. EU AI Act logging of
high-risk decisions). It is **not** a certification and **not** a substitute for a
legal compliance review. Admissibility depends on jurisdiction and process. Every
guarantee above is conditioned on its stated assumptions; claims that omit those
assumptions are not authorised.
