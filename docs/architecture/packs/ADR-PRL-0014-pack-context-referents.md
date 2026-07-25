# ADR-PRL-0014 — Pack Context Referents (`domain`, `pack_id`, `pack_version`, `jurisdiction`)

**Status:** Proposed — **awaiting human ratification** · **Version:** v0.1 · **Date:** 2026-07-25 · **Regime:** `declared`
**Depends on:** ADR-PRL-0001 (Constitution), 0002 (Registry architecture), 0004 (Protocols/MEF), 0009 (Structured attribution), **0010 (Organization referent — cited, not redefined)**
**Axis:** context / identity contract. **Nature:** defines **a contract, not an implementation.** No data-model
placement, no schema decision, no permissions mechanism, **no kernel change**.

> **What an organization does is not who it is, nor where it works.** A business domain, a knowledge pack,
> a pack version and a regulatory jurisdiction are **declared referents** — never inferred from the
> project, the path, the storage, the model, or the file the pack happened to be read from.

## Why now

Daryl is converging on a single installable product whose sector intelligence is loaded as **versioned
packs** rather than forked per vertical (see `ADR-PACK-0001`). That composition is only governable if the
context it composes over is *named*, and named the way Daryl already names identity.

Grounding of the current tree finds **no `domain`, no `pack_id`, no `pack_version`, no `jurisdiction`
referent anywhere** in the governed layer. The one adjacent field — `Skill.domain` in
`src/dsm/skills/models.py` — is a free string on a v0 placeholder registry with no versioning, no
namespace, and no governance; it is *not* a referent and this ADR does not promote it into one.

Meanwhile the two questions packs must answer are already unanswerable:

1. **Which rules governed this decision?** Today a receipt can cite the agent, the carrier, the org and the
   claim — but not the *body of rules* that was in force. A wrong regulatory rule shipped in a versioned
   pack engages the professional liability of the firm using it; without a referent, it cannot be traced.
2. **Same domain, different regulator.** Accounting in MA and in FR are not the same governed reading. With
   no jurisdiction referent, the difference can only be encoded by forking the domain — the exact
   duplication the platform exists to avoid.

The referents are therefore *conceptually necessary* and must be fixed as a **contract** before any design.

## Decision (the rule)

> Daryl has **four pack-context referents** — `domain`, `pack_id`, `pack_version`, `jurisdiction` — each a
> **declared, carrier-independent** identity. None is ever derived from `project_id`, `root_path`,
> `storage_dir`, `shard`, `deployment`, `provider`, `model`, or the filename a pack was loaded from.
> **`org_id` is not defined here**: it is ADR-PRL-0010's referent, **cited and reused unchanged**.

## The load-bearing invariant

> **A referent is never its carrier — and context is never its container.** `domain` is not the pack file
> that carries it, `pack_id` is not the path it was read from, `jurisdiction` is not the deployment region,
> and `org_id` is not the project. This ADR adds the *context* leg to the same discipline already carried by
> `claim_id` ∉ storage (0001), `agent_id` ≠ `model_id` (0009), and `org_id` ≠ project/carrier (0010).

## The rules (minimal, contract-level)

1. **`domain` is business-logical.** It names *a body of professional thinking* (candidate convention
   `domain.<name>`, e.g. `domain.fiduciaire`), not a task type, not a capability, not a shard family, not an
   agent role. It is never derived from what a pack file is called or where it sits.

2. **`pack_id` is the stable logical identity of a knowledge pack.** It is not the file, not the repository,
   not the directory, not the storage location. Two deployments loading the same pack from different paths
   carry the **same** `pack_id`.

3. **`pack_version` makes the citable unit.** The citable unit of governed rules is the pair
   **`(pack_id, pack_version)`**, written `pack_id@pack_version`. A pack is **immutable at a version**:
   changing any governed content requires a new version. Version strings are semver
   (`MAJOR.MINOR.PATCH`); ordering semantics are fixed by `ADR-PACK-0001`, not here.

4. **`jurisdiction` is a regulatory space, not a place.** Candidate convention: ISO 3166-1 alpha-2 upper
   (`MA`, `FR`), optionally `XX-REGION`. It is **distinct from `domain`** (what kind of work), **distinct
   from `org_id`** (whose work), and explicitly **not** the deployment region, the data-residency zone, or
   the user's locale.

5. **No inference (mirror 0009/0010).** An absent referent reads as **unknown** — never fabricated, never
   back-derived from a carrier, never guessed by a model. A pack that does not declare its jurisdiction is
   jurisdiction-*unknown*, which is not the same as jurisdiction-*universal*.

6. **`org_id` is reused, not redefined.** ADR-PRL-0010 is Accepted and remains the sole definition of the
   organization referent. This ADR **cites** it as the fifth context referent and adds nothing to it —
   no restatement, no extension, no narrowing. Any future change to `org_id` amends 0010, never 0014.

7. **Context is not epistemic.** Like `org_id` (0010 §5) and unlike `agent_id`, these referents concern
   *which rules were in force*, not *who said what with what confidence*. Their placement is therefore
   **deliberately left open** and they may *not* live in the MEF. Placement is a later design.

8. **The referents are orthogonal.** `domain × jurisdiction × org_id` is a **product, not a hierarchy**. A
   pack tree that renders them as nesting is a display convenience; the governed model composes them by the
   precedence rules of `ADR-PACK-0001`, which are declared per field and never positional.

## Non-goals (hard scope fence)

No data-model placement. No storage decision. No schema binding of these referents into `Entry`, `MEF`, or
any existing model. **No kernel change** (`src/dsm/core/` is frozen — untouched by this ADR). No permissions,
tenancy or isolation mechanism. No promotion of the `src/dsm/skills/` v0 registry. No engine, no interpreter,
no MCP exposure. No claim about retrieval performance. `claim_id` / `agent_id` / `org_id` minting untouched.

## Known prerequisites, not delivered by this ADR

Recording these referents is one thing; **querying by them is another**, and the second is not free today.

- **RR index on `metadata`.** The extension promoting `metadata["action_name"]` to a first-class Read Relay
  index key is validated on the proto branch `proto/phase-7a-rr-action-name-index` (commit `58d7789`,
  navigator fix `e570841`) and is a **Phase 7b prerequisite not merged into `main`** (see
  `ARCHITECTURE.md` §Canonical Consumption Path). Until it lands, "retrieval-first on pack referents" has
  **no index to be first on**. This ADR declares referents; it does not deliver their retrieval.
- **Signature path.** See `ADR-PACK-0001` §Known prerequisites — Ed25519 exists in `dsm-primitives` but is
  **not wired into the append path**, which matters for pack authority, not for the referents themselves.

## Governance

Establishing an identity contract is itself a **governed decision** (0010 precedent). This ADR is
**Proposed** and must be **human-ratified** before any design or implementation depends on it. It was drafted
by an agent; drafting is a proposal, never a ratification — an agent cannot move its own ADR to Accepted.

## Future proof gate (defined, not executed)

The context leg is considered established when, in runtime:

1. the **same `domain`** composed against **two different `jurisdiction`s** yields **two different governed
   readings** of the same input, each receipt-backed; and
2. **one decision receipt cites the exact `(pack_id, pack_version)` set** that governed it, and that set is
   verifiable — i.e. a rule can be traced from a decision back to the versioned pack that carried it and the
   authority that signed it.

Only then does the context leg earn promotion, per the `CAPABILITY_REGISTER` ladder (🔵 → 🟢 requires a real
transcript, not a passing test).

## Consequences & sequence

- This is a **contract**, not a build: it fixes *what* these referents are, not *how* they are stored.
- **Ratification first.** Then a **placement design** (`Entry.metadata` vs a pack-context block vs a
  `project → pack` binding), then implementation, then the proof gate above.
- `ADR-PACK-0001` consumes these referents to define composition; it depends on this ADR and does not
  redefine any referent it uses.
- A `PROOF_LOG.md` entry only on real proof. A `CAPABILITY_REGISTER` row moves only on the same discipline
  as every other row.
