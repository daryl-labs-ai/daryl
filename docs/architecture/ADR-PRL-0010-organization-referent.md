# ADR-PRL-0010 — Organization Referent (`org_id` ≠ project / carrier)

**Status:** Accepted — ratified-by-Mohamed 2026-06-28 · **Version:** v1 · **Date:** 2026-06-28 · **Regime:** `declared`
**Depends on:** ADR-PRL-0001 (Constitution), 0002 (Citizens), 0004 (Messages/MEF), 0009 (Structured attribution)
**Axis:** ownership / identity contract. **Nature:** defines **a contract, not an implementation.** No
data-model placement, no schema, no kernel change, no permissions mechanism.

> **The project is not the unit of ownership.** Identity is never defined by its carrier — and an
> organization's identity must not be its project, its storage, its path, or its deployment.

## Why now
Grounding #5 found **no organization referent** in code; the cross-project study **validated A**: there
exist owner-scoped questions — org-wide governance, permissions, multi-tenant **isolation**, org-scoped
recall — that **`project_id` alone cannot express**. And `project_id = sha256(root_path)` is
**carrier-bound** (path/deployment), so it (or sets of it) cannot stand in for an owner without
inheriting a carrier dependency. The referent is therefore *conceptually necessary* and must be fixed
as a **contract** before any design.

## Decision (the rule)

> Daryl has an **organization referent** — `org_id` — the **stable logical identity of the owning
> organization / team**. The **project is not the unit of ownership** (one org owns many projects).
> `org_id` is **carrier-independent**: it is never equal to, nor derived from, `project_id`,
> `root_path`, `storage_dir`, `shard`, `deployment`, or `provider`.

## The load-bearing invariant

> **`org_id` is not its carrier.** It is an owner-logical identity, assigned independently of the
> project, the storage, the path, and the deployment — the candidate **third leg** of *"identity is
> never defined by its carrier"* (after `claim_id` ∉ storage and `agent_id` ≠ `model_id`).

## The rules (minimal, contract-level)
1. **`org_id` is owner-logical.** It names the organization/team that owns projects and knowledge
   (candidate convention `org.<name>`), not what is worked on.
2. **Distinct from the project.** `org_id` ≠ `project_id`; a project *belongs to* an org, it is not an
   org.
3. **Carrier-independent.** Never derived from path/storage/shard/deployment/provider.
4. **No inference (mirror 0009).** Absent ownership reads as **unknown**, never fabricated or
   back-derived. (The data shape that carries it is *not* decided here.)
5. **Ownership is not epistemic.** Unlike `agent_id`, `org_id` concerns governance/access, not "who
   said what with what confidence" — so its placement is **deliberately left open** (it may *not* live
   in the MEF).

## Non-goals (hard scope fence)
No data-model placement, no schema, no storage, **no kernel change**, **no #5b distributed
certification**, no permissions/isolation/tenancy mechanism, no implementation. `claim_id` /
`agent_id` minting untouched. Placement, assignment, and the `project → org` binding are **open design
questions** (see `IDENTITY_ORG_REFERENT_DESIGN_ISSUE.md`), settled in a later design — only after this
contract is ratified.

## Governance
Establishing an identity contract is itself a **governed decision**: this ADR must be **human-ratified**
before any design or implementation. (The project applies its own governance to its own model.)

## Future proof gate (defined, not executed)
The third leg of framing #8 is considered established when, in runtime: (1) **the same `org_id`** owns
two projects at **different carriers** (root_path / storage / deployment) with identical organization
identity, and (2) **one owner-scoped question** `project_id` alone cannot express becomes answerable via
`org_id`. Only then does framing #8 (`FABRIC_FRAMINGS_INCUBATING.md`) earn its third leg and become a
candidate for the manifesto.

## Consequences & sequence
- This is a **contract**, not a build: it fixes *what* `org_id` is, not *how* it is stored.
- **Ratification first.** Then a **placement design** (MEF vs ownership context vs project→org binding),
  then implementation, then the proof gate above.
- A `PROOF_LOG.md` entry only on real proof; a `FRAMING_DECISION_LOG.md` row if the transversal framing
  guided the call.
