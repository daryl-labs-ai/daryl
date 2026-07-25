# Daryl Packs — contracts v0.1

**Status:** Proposed — **awaiting human ratification** · **Date:** 2026-07-25 · **Regime:** `declared`
**Nature:** documentary lot. **No code in `src/`. No kernel change. `src/dsm/core/` is frozen and untouched.**

Daryl converges on **one installable product** whose sector intelligence is loaded as **versioned packs**,
rather than forking into DARYL Compta, DARYL Assurance, DARYL Juridique as three applications. This directory
holds the first **falsifiable contracts** for that model — not a design note, not a roadmap: contracts that
can be *shown wrong* by running the vectors in this folder.

## Why a separate `ADR-PACK-*` series

This is the load-bearing editorial decision of the lot, so it is stated rather than assumed.

The `ADR-PRL-*` series is the law of the **Project Recall Layer**: what a claim is, what a standing is, who
contributed, how certification survives, which identities are declared and never inferred. It governs **the
epistemic substrate** — the machinery by which Daryl remembers and justifies. Its numbering is a single
chain because its subjects are a single chain: every one of 0001–0013 constrains how acts are recorded, read
or reconciled.

Pack composition is **a different governance domain**. It governs **which body of professional rules was in
force** when work was done — a question about *authority, versioning and derogation*, not about *memory,
provenance or standing*. Three concrete consequences make the separation structural rather than cosmetic:

1. **Different subject.** `ADR-PRL-*` constrains DSM and PRL. `ADR-PACK-*` constrains an artifact format and
   a resolution function that **sit above** them and write into them. A pack is *content* DSM records; it is
   not part of DSM.
2. **Different amendment surface.** A pack-composition rule can change — new merge semantics, new refusal
   codes, a fifth layer — **without touching a single PRL invariant**. Folding these into the PRL chain would
   make business-domain churn look like epistemic-substrate churn, and the register's whole value is that a
   move in the law means something.
3. **Different ratification stakes.** A wrong PRL rule corrupts the record. A wrong pack rule ships a wrong
   regulatory reading into a client's file and engages professional liability. These are not the same risk
   and should not queue behind one another.

**The boundary, stated as a fence:** `ADR-PACK-*` **may cite and depend on** `ADR-PRL-*`; it **may never
amend, narrow, extend or reinterpret** it. Where a pack rule appears to need a PRL change, the correct move
is a PRL amendment ADR — never a pack ADR that quietly does the work.

The one deliberate exception is the referents ADR. **`ADR-PRL-0014` lives in the PRL series on purpose**:
declaring `domain`, `pack_id`, `pack_version` and `jurisdiction` as *declared, carrier-independent referents*
is an identity statement, and identity is PRL law — the same law that carries `claim_id` ∉ storage (0001),
`agent_id` ≠ `model_id` (0009) and `org_id` ≠ carrier (0010). It is filed under `packs/` for proximity to the
lot it serves; its **series** is PRL because its **subject** is identity.

It **cites ADR-PRL-0010 for `org_id` and does not redefine it.** 0010 is Accepted and remains the sole
definition; any future change to `org_id` amends 0010, never 0014.

## What is in this lot

| File | What it fixes |
|---|---|
| `ADR-PRL-0014-pack-context-referents.md` | The four declared referents; cites 0010 for `org_id`. |
| `ADR-PACK-0001-composition-and-precedence.md` | The composition law: four layers, two control axes, ten typed refusals, permutation-invariance. |
| `pack.v0.1.schema.json` | The pack envelope — all 14 sections reserved, 2 in proof scope. |
| `pack-resolution.v0.1.schema.json` | The resolution result, trace and the three receipts. |
| `compatibility-matrix.example.yaml` | A worked, non-normative compatibility declaration. |
| `examples/` | Five fictional packs, including two peers built to collide and a derogation fixture. |
| `resolution-vectors.v0.1.json` | Canonical inputs → expected outcome, expected refusals, expected hash. |
| `tools/` | A **non-normative reference checker** that runs the vectors. |

## Running the checker

`python3 tools/check_vectors.py` (needs `jsonschema` and `pyyaml`; it does not care what directory you run it
from). It validates every pack against the schema — including the ones marked `schema_valid: false`, which it
asserts really do fail — recomputes every content hash, checks each embedded pack document still matches the
YAML example it was taken from, replays every vector under **every** permutation of its input order, rebuilds
the receipts, and proves the resolver imports no clock, no randomness and no frozen-kernel module.

The vectors were then audited by attacking them: twenty-one deliberate defects seeded one at a time — wrong
hashes, a tampered manifest value, a trace edited to hide that a derogation had been used, a truncated refusal
set, a reordered refusal set, four broken sort keys and a broken fold in the reference resolver — and each one
confirmed to turn the run red. Two rules survived that audit **unfalsified by anything in the file**; they are
now pinned by two vectors that exist for no other purpose. A green test file proves nothing until it has been
shown capable of going red.

## The three sentences that carry the model

**Derogation is not a layer.** The precedence chain is exactly `core < domain < jurisdiction < organization`.
Derogation is a field-level, signed, scoped, expiring permission effect evaluated *inside* composition. Drawn
as a fifth layer, it would silently make `forbidden` negotiable.

**A field's control is fixed by the layer that introduces it.** `merge` semantics (`replace`/`append`/
`union`/`intersect`) are immutable; `override` permission (`open`/`requires_derogation`/`forbidden`) may only
be **tightened**. `forbidden` is **absolute** — no derogation, no authority, no organization lifts it.

**Ambiguity is a refusal, never a winner.** Peers at equal precedence contributing non-commutative values
refuse (`peer_conflict`). No list order, import order or directory order may arbitrate anything.

## Acceptance criterion

> Two independent implementations receiving the same packs, **in any input order**, must either produce the
> **same effective manifest by value identity and the same canonical hash**, or produce the **same typed
> refusal**.

The hash is `dsm_primitives.hash_canonical` → `v1:<sha256>` over ADR-0002 canonical JSON. **No new hashing
law is introduced by this lot.**

`resolution-vectors.v0.1.json` makes this criterion falsifiable by a foreign implementer. It does **not**
constitute the proof: the vectors are one implementation checking itself. The proof requires a **second,
independent implementation** and a real transcript. Nothing in `CAPABILITY_REGISTER.md` moves on this lot.

## Known prerequisites, not delivered

1. **RR index on `metadata`** — validated on `proto/phase-7a-rr-action-name-index` (`58d7789`, navigator fix
   `e570841`), a **Phase 7b prerequisite not merged into `main`**. Receipts can *record* `(pack_id,
   pack_version)`; they cannot yet be *queried* by them at the sanctioned read path.
2. **Signature wiring** — Ed25519 exists in `dsm-primitives` but is **not wired into the governance path**.
   `requires_derogation` is therefore **procedurally enforced, not cryptographically enforced**. v0.1 checks
   that a signature is present and structurally complete; it never verifies it.

Neither is a footnote. Read together they mean: **this lot delivers a governable contract, not an enforced
control.**

## Status

Both ADRs are **Proposed**. They were drafted by an agent, and drafting is a proposal, never a ratification —
an agent cannot move its own ADR to Accepted. Nothing here is law until a human ratifies it.
