# MMR_SPEC — Merkle Mountain Range for DSM

- **Status:** Proposed (P1, spec-only). No implementation here.
- **Date:** 2026-06-12
- **Normative deps:** ADR-0002 (canonical hashing v1), RFC 6962 §2 (hashing
  discipline), [`STH_SPEC.md`](./STH_SPEC.md)
- **Hash function:** SHA-256 (matches `dsm-primitives` v1). All hashes are 32 bytes.

Keywords MUST/SHOULD/MAY per RFC 2119.

---

## 1. Why an MMR

A Merkle Mountain Range is an append-only authenticated data structure. Appending
a leaf is `O(log n)` and never rewrites existing nodes; the structure commits to
all leaves via a small set of **peaks**. It yields `O(log n)` **inclusion** proofs
(leaf ∈ tree of size n) and `O(log n)` **consistency** proofs (tree of size m is a
prefix of tree of size n). These two proofs are the cryptographic core of the DSM
transparency guarantee.

## 2. Leaf assignment

- The MMR is maintained **per logical shard** (one MMR per shard id).
- Leaf `i` (0-indexed, in append order) commits to **the canonical entry hash of
  entry `i`**, i.e. the `v1:` hash already produced by `dsm-primitives`
  (`_build_canonical_entry` → `hash_canonical`). The MMR therefore layers over the
  existing kernel without re-canonicalising entries.
- Leaf count `= shard entry_count`. This binds the MMR to the same count the P0
  pinned tip tracks, so the two integrity layers cross-check.

## 3. Node hashing (domain-separated, RFC 6962-style)

Let `EH(i)` be the canonical entry hash bytes of entry `i` (the 32 bytes after the
`v1:` prefix). Define:

```
LeafHash(i)      = SHA-256( 0x00 || EH(i) )
NodeHash(L, R)   = SHA-256( 0x01 || L || R )
```

- The `0x00` / `0x01` domain-separation prefixes are REQUIRED; they prevent
  second-preimage attacks that confuse a leaf with an internal node (RFC 6962 §2.1).
- `L`, `R` are the 32-byte child hashes in left-to-right order.
- This hashing is **versioned** as MMR-v1. Any change is a new version requiring a
  new STH `origin` string (`STH_SPEC.md` §2).

## 4. Structure: positions, peaks, bagging

We use the standard (Grin/`mmr`) position numbering.

- Nodes are numbered `1..N` in **post-order** of insertion. Appending leaf `i` adds
  the leaf node, then merges equal-height siblings upward, adding one parent per
  merge — `O(log n)` nodes total, amortised `O(1)`.
- A **peak** is a node with no parent. After `n` leaves, the peaks correspond
  exactly to the **set bits of `n`**: a shard of `n = 11 = 0b1011` leaves has peaks
  of sizes `8, 2, 1`. There are `popcount(n)` peaks, at most `⌈log2 n⌉`.
- The **MMR root** for size `n` is computed by **bagging the peaks** right-to-left:

```
BagPeaks([p_1, ..., p_k]) =        # p_1 is the leftmost (largest) peak
    acc = p_k
    for p in reversed(p_1 .. p_{k-1}):
        acc = NodeHash(p, acc)
    return acc
Root(n) = SHA-256( 0x02 || n_be64 || BagPeaks(peaks(n)) )
```

- The outer `SHA-256(0x02 || n || ...)` binds the **size** into the root, so a root
  is meaningless without its declared size (defends against size-confusion between
  two trees that share a peak structure). `n_be64` = big-endian uint64.
- `Root(0)` (empty shard) is defined as `SHA-256(0x02 || 0x0000000000000000)`.

## 5. Inclusion proof

**Goal:** prove leaf `i` is committed by `Root(n)` for some `n > i`.

An inclusion proof is the ordered list of sibling hashes from leaf `i` up to its
peak, followed by the **other peaks** needed to recompute the bagging.

```
InclusionProof(i, n) = {
    leaf_index: i,
    tree_size:  n,
    merkle_path: [ (sibling_hash, side) ... ],   # within i's mountain, bottom-up
    peak_frame:  [ peak_hash ... ],              # the other peaks, left-to-right
}
```

**Verification** (`O(log n)`, stateless):
1. `h = LeafHash(i)` — recompute from the entry the verifier already holds.
2. For each `(sib, side)` in `merkle_path`: `h = NodeHash(sib, h)` if `side=left`
   else `NodeHash(h, sib)`. After the loop `h` is `i`'s peak.
3. Insert `h` into `peak_frame` at `i`'s peak position; `BagPeaks(...)` the full
   peak list; wrap with `SHA-256(0x02 || n || ...)`.
4. Accept iff the result equals `Root(n)` from the STH.

## 6. Consistency proof (the anti-truncation core)

**Goal:** prove the size-`m` tree is a **prefix** of the size-`n` tree (`m ≤ n`),
i.e. the first `m` leaves are unchanged and only appends happened.

A consistency proof supplies the minimal node set that lets a verifier recompute
**both** `Root(m)` and `Root(n)` from shared material:

```
ConsistencyProof(m, n) = {
    old_size: m, new_size: n,
    nodes: [ hash ... ],   # peaks of m that are not peaks of n, plus the path
                           # nodes needed to re-derive Root(n)
}
```

**Verification** (`O(log n)`):
1. From `nodes`, reconstruct the peaks of the size-`m` tree → recompute `Root(m)`;
   MUST equal the `root` in `STH_m`.
2. Extend with the remaining `nodes` to reconstruct the peaks of the size-`n`
   tree → recompute `Root(n)`; MUST equal the `root` in `STH_n`.
3. Accept iff both match. Failure ⇒ the operator did not simply append (rewind,
   truncation, or rewrite). This is the property that makes truncation provable to
   a **third party**, not merely detectable locally as in P0.

## 7. Operational notes (non-normative)

- **Persistence.** The MMR node store is append-only and recomputable from entry
  hashes; loss of the node store is recoverable by replaying entries. It is a cache
  of `EH(i)` and internal nodes, not a second source of truth.
- **Crash safety.** MMR append MUST be committed within the existing shard lock and
  be idempotent on replay (re-appending the same leaf hash at index `i` is a no-op).
  Interaction with the P0 pinned tip and `reconcile` is specified in `P1_TO_P2.md` §3.
- **Proof size.** Inclusion and consistency proofs are `O(log n)` hashes — e.g. a
  shard of 1e6 entries yields proofs of ≤ ~20 sibling hashes (~640 B).
- **No entry rewrite.** Nothing in this spec modifies stored entries or the v1
  entry hash; the MMR strictly *reads* `EH(i)`.

## 8. Test obligations

Inclusion correctness, consistency correctness, anti-truncation, peak/bagging
vectors, and second-preimage (domain-separation) checks are enumerated in
[`P1_MODEL_TESTS.md`](../tests/P1_MODEL_TESTS.md) §2.
