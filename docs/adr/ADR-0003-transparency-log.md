# ADR-0003 — DSM Proof Layer v2: a Transparency Log (MMR + STH + Witness + Anchoring)

- **Status:** Proposed (P1, spec-only)
- **Date:** 2026-06-12
- **Supersedes (partially):** the ad-hoc per-shard proof constructs audited in P0
- **Depends on:** ADR-0002 (dsm-primitives canonical hashing v1)
- **Scope of this ADR:** decision + architecture. Detailed mechanics live in the
  companion specs (`docs/spec/*`). This document contains **no code** and changes
  **no** `src/` or `agent-mesh/` file.

---

## 1. Context

The P0 institutional audit (see `docs/security/P0_REMEDIATION.md`) established two
facts about the DSM proof layer:

1. The per-entry hash chain proves *internal* ordering but not *completeness*.
   P0 added a pinned-tip check so trailing truncation is now **detected** — but
   the pin is a local file sharing the same trust boundary as the data it
   protects. A fully-privileged local adversary can still rewrite shard + pin
   together, and nothing prevents **equivocation** (showing different histories
   to different verifiers).

2. Several "binding" constructs (key-history `status`, attestation
   `dispatch_hash`, dispatch agent IDs, seal) left security-relevant fields
   **outside** the signed/hashed payload (audit H1–H4). These were hand-rolled,
   field-by-field hash concatenations.

The root cause is singular: **DSM reinvented, ad-hoc, a structure that already
exists in proven form — the transparency log** (RFC 6962 Certificate
Transparency; Go checksum database / `go.sum`; Sigsum; Trillian). The P1 decision
is to stop inventing and adopt that model, mapped onto DSM's existing
append-only, hash-chained entries.

## 2. Decision

Build the DSM proof layer v2 as a **transparency log** composed of five
cooperating mechanisms, each specified in its own document:

| Layer | Mechanism | Defeats | Spec |
|---|---|---|---|
| Structure | **Merkle Mountain Range (MMR)** over entry hashes | reorder, insertion, in-place edit, **truncation** (via consistency proofs) | [`MMR_SPEC.md`](../spec/MMR_SPEC.md) |
| Checkpoint | **Signed Tree Head (STH)** — Ed25519 over `{size, root, time}` | a log operator denying or rewinding its own state | [`STH_SPEC.md`](../spec/STH_SPEC.md) |
| Distribution | **Witness cosigning** (k-of-n, Sigsum-style) | **equivocation / split-view** | [`WITNESS_SPEC.md`](../spec/WITNESS_SPEC.md) |
| Anchoring | **MultiversX anchoring** of STH roots | local clock forgery; gives public, non-repudiable timestamp | [`MULTIVERSX_ANCHORING.md`](../spec/MULTIVERSX_ANCHORING.md) |
| Binding | **`bind()` primitive** — sign the whole canonical object | the H1–H4 "field left outside the hash" class, by construction | [`BIND_PRIMITIVE.md`](../spec/BIND_PRIMITIVE.md) |

The end state: a **TaskReceipt becomes a Merkle inclusion proof against a
witnessed, anchored STH** — verifiable by a third party who trusts neither the
agent nor the DSM operator. That is the guarantee DSM has always claimed; P1 is
what makes it true.

## 3. Why MMR rather than a classic RFC 6962 Merkle tree

Both give inclusion + consistency proofs. The differentiator is append cost and
operational simplicity for an **always-appending** agent log:

- A classic CT tree is defined over a fixed leaf set; incremental append requires
  careful tiling. MMRs (Grin, Beam, OpenZeppelin `MerkleTree`/MMR libraries) are
  *designed* for append-only growth: appending a leaf is **O(log n)** and touches
  only `O(log n)` "peak" nodes; nothing already written is rewritten.
- MMR state is a small set of **peaks** (one per set bit in `tree_size`), which is
  exactly what a checkpoint needs to commit to.
- Consistency and inclusion proofs are `O(log n)` and stateless to verify.

We adopt **RFC 6962 hashing discipline inside the MMR** (domain-separated leaf vs
internal node hashing) to retain its second-preimage resistance. Details in
`MMR_SPEC.md` §3.

## 4. Relationship to the existing kernel (compatibility)

- **Entries are not rewritten.** The MMR is layered *over* the existing
  append-only entries: MMR leaf `i` = the canonical entry hash already produced
  by `dsm-primitives` v1 (ADR-0002). The P0 hash chain and pinned tip remain as a
  cheap first-line integrity check.
- **Backfill, not migration of data.** An existing shard's MMR is computed from
  its existing entry hashes; a genesis STH is then anchored. (Honest limitation:
  history *before* the genesis anchor is only provable relative to that anchor —
  see `P1_SECURITY_MODEL.md` §6.)
- **Versioning.** New record types (STH, inclusion/consistency proof, anchored
  receipt) are `v2`. Legacy `v0/v1` records remain verifiable read-only. The proof
  layer ships behind a capability flag until parity is proven.

## 5. Consequences

**Positive**
- Truncation/equivocation become structurally impossible to hide, not merely
  detectable on one host.
- The `bind()` primitive eliminates an entire bug class (H1–H4) by removing the
  hand-maintained field list.
- MultiversX stops being dead weight and becomes the public-anchoring
  differentiator.
- Claims become defensible to a CISO/auditor/regulator because the design maps to
  a recognised standard (CT/Sigsum).

**Negative / costs**
- New operational dependencies: a signing key (HSM/KMS), one or more witnesses,
  and periodic on-chain transactions (gas, latency between anchors).
- Breaking changes to the receipt/verification format → a **v2.0.0** release with
  a migration window (`P1_TO_P2.md`).
- Verifier complexity rises (must check proofs); mitigated by shipping a tiny,
  portable verifier (`P1_TO_P2.md` §4).

## 6. Alternatives considered

- **Keep the P0 pinned tip only.** Rejected: does not defeat a privileged local
  adversary or equivocation; not third-party-verifiable.
- **Classic RFC 6962 tree.** Viable; rejected as primary for append ergonomics
  (§3). Hashing discipline borrowed from it regardless.
- **Anchor every entry on-chain.** Rejected: cost/latency prohibitive. We anchor
  STH roots periodically (batched), which amortises one transaction over many
  entries (`MULTIVERSX_ANCHORING.md` §4).
- **External SaaS transparency log (e.g. hosted Trillian).** Out of scope for the
  open-source core; the design stays operator-runnable and witness-checkable.

## 7. Acceptance criteria (model-level, P1)

P1 is "specified and modelled" when:
1. All seven companion specs are reviewed and internally consistent.
2. `P1_MODEL_TESTS.md` enumerates the property tests and test vectors an
   implementation MUST pass (inclusion, consistency, monotonicity,
   anti-truncation, anti-equivocation, bind-coverage).
3. `P1_SECURITY_MODEL.md` states each trust assumption and which mechanism
   discharges it, with residual risks made explicit.

Implementation (writing `src/` code) is **P2** and explicitly out of scope here.
