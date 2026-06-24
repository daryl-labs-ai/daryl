# WITNESS_SPEC — Witness Cosigning

- **Status:** Proposed (P1, spec-only). No implementation here.
- **Date:** 2026-06-12
- **Normative deps:** [`STH_SPEC.md`](./STH_SPEC.md), [`MMR_SPEC.md`](./MMR_SPEC.md)
- **Model:** Sigsum / CT witness cosigning ("gossip-less" non-equivocation).

A witness is an independent party that **verifies the consistency of each new STH
against the last one it cosigned, then adds its own signature**. The security
goal is **non-equivocation**: the operator cannot show two different histories to
two different verifiers, because a witness will not cosign a fork.

---

## 1. Why witnesses (what STH+anchoring alone miss)

An operator with its signing key can issue a perfectly valid STH for *any* tree,
including a forked or rewound one. Anchoring records *a* root on-chain but does not,
by itself, prevent the operator from privately serving a different consistent-looking
STH to a victim before the next anchor. Witnesses close this: a verifier requires a
**quorum (k-of-n)** of cosignatures, and each honest witness enforces append-only
progression. To equivocate, the operator would need `> n − k` witnesses to collude.

## 2. Witness responsibilities

A witness MUST, for each candidate `STH_new` under an `origin`:
1. Verify the operator signature on `STH_new` (`STH_SPEC.md` §4).
2. Retrieve the consistency proof `σ(STH_last, STH_new)` where `STH_last` is the
   most recent STH **this witness** cosigned for that `origin`.
3. Verify `σ` (`MMR_SPEC.md` §6) AND `STH_new.tree_size ≥ STH_last.tree_size`.
4. Only then emit `cosig = Ed25519(witness_key, bind("dsm.sth.v1", STH_new))` —
   the witness signs **the same canonical STH bytes** the operator signed.
5. Persist `STH_new` as its new `STH_last` for that `origin` (monotone state).

A witness MUST refuse (and SHOULD publish the refusal evidence) if step 2–3 fails:
that refusal is itself a signal of attempted rewind/fork.

## 3. Quorum policy

- A receipt/checkpoint is "**witnessed**" iff it carries ≥ `k` valid cosignatures
  from distinct witnesses in the configured witness set of size `n`.
- `k` and the witness public keys are part of the verifier's **trust policy**, not
  the log — verifiers MUST pin the witness set out-of-band (e.g. in the SDK or a
  signed policy file). Diversity (different orgs / jurisdictions / infra) is the
  real security parameter.
- Recommended starting policy: `n ≥ 3`, `k = 2` (tolerates one unavailable or one
  faulty witness). High-assurance deployments raise both.

## 4. Monotonicity enforcement (P-MONOTONICITY)

Each witness maintains, per `origin`, the last cosigned `(tree_size, root)`. It
cosigns `STH_new` only if `tree_size` does not decrease **and** consistency holds.
This makes a rewind require either (a) breaking a hash, or (b) corrupting the
witness's own state — neither available to the log operator.

## 5. Non-equivocation as transferable proof (P-NON-EQUIVOCATION)

If the operator ever gets two STHs cosigned for the same `origin` with the **same
`tree_size` but different `root_hash`**, those two witnessed STHs together are a
**self-contained, transferable proof of misbehaviour**: anyone can verify both
signatures and observe the contradiction, with no further trust. Witnesses that
follow §2 will not produce such a pair unless compromised; anchoring (§ below)
provides a second, public tiebreaker.

## 6. Interaction with anchoring

Witnessing and anchoring are complementary:
- **Witnesses** give *fast, online* non-equivocation between anchors.
- **MultiversX anchoring** gives a *public, permanent* record of the canonical
  root per size, resolving disputes even if witness availability lapses.
A fully-verified receipt SHOULD carry both ≥ k cosignatures and an anchor reference
(`P1_SECURITY_MODEL.md` §5).

## 7. Failure & availability

- Witness unavailability degrades to "fewer cosignatures"; if `< k` are reachable,
  the checkpoint is **un-witnessed** and verifiers treat it as lower assurance — it
  is never silently upgraded. (No silent caps: the SDK MUST report when a receipt
  fell back to un-witnessed.)
- Witnesses are stateless to bootstrap (they can start from any anchored STH as a
  trusted origin) but MUST be monotone thereafter.

## 8. Test obligations

Cosign-only-on-consistency, rewind refusal, equivocation-evidence construction,
quorum threshold, and diversity-policy enforcement are enumerated in
[`P1_MODEL_TESTS.md`](../tests/P1_MODEL_TESTS.md) §4.
