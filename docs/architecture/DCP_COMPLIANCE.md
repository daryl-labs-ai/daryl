# DCP v1.0 — Compliance Specification

**Status:** SPECIFICATION
**Date:** 2026-07-08
**Full name:** DSM Continuity Protocol, version 1.0
**Short name:** DCP v1.0

---

## What DCP is

DCP (DSM Continuity Protocol) defines the contract between a project's
shared memory and any tool that wants to participate in that project's
continuity.

DCP is not an LLM API. DCP does not standardize how to call a model.
DCP standardizes **how a project continues when the model working on it
changes**.

---

## Compliance levels

An implementation claiming DCP compliance MUST implement all Mandatory
primitives. It MAY implement any Optional primitives. The compliance
claim states the level achieved.

### Mandatory (DCP 1.0 Core)

A DCP 1.0-compliant Continuity Provider MUST implement:

| Primitive | Signature | Contract |
|-----------|-----------|----------|
| `catch_up` | `(project_id) → ContextBundle` | MUST be called before work. MUST refuse to continue if integrity ≠ OK. |
| `publish_receipt` | `(project_id, agent_id, task, result) → Receipt` | MUST be called after work. Receipt MUST be portable (JSON). |
| `verify` | `(project_id) → IntegrityReport` | MUST return status (OK/TAMPERED/TRUNCATED), entry count, chain continuity. |
| `project_context` | `(project_id) → ProvenanceBlock` | MUST return entry hashes, source shards, integrity, verification hint. |

If any of the four is missing, the implementation is **not** DCP 1.0
compliant.

### Optional (DCP 1.0 Extensions)

| Extension | What it adds |
|-----------|--------------|
| `replay_protection` | Rejects duplicate receipts (nonce/counter) |
| `remote_storage` | Backs the project shard to a remote/shared backend |
| `streaming_context` | `catch_up` streams large project state incrementally |
| `signatures` | Ed25519 signatures on every published receipt |
| `dispatch_binding` | Causal links between agents (dispatch_hash) |
| `offline_queue` | Queues publish_receipt calls when offline, syncs later |

An implementation MAY claim compliance with extensions:

> *"LM Studio Continuity Provider — DCP 1.0 Core compliant"*
> *"Claude Continuity Provider — DCP 1.0 Core + signatures + dispatch_binding"*

---

## Compliance claim format

A compliant implementation states:

```
<Tool Name> Continuity Provider
DCP Version: 1.0
Compliance: Core [+ <extensions>]
Method: <full | assisted | read-only>
```

Where `Method` indicates the automation level:

| Method | Meaning |
|--------|---------|
| **full** | All primitives automated; no human in the loop |
| **assisted** | Primitives work but require human bridge (clipboard, manual MCP config) |
| **read-only** | `catch_up` + `verify` + `project_context` only; no `publish_receipt` |

---

## Protocol invariants (binding)

These invariants hold for ALL DCP 1.0 implementations, regardless of
compliance level:

1. **Project-scoped.** All operations are namespaced by `project_id`.
2. **Agent-attributed.** Every receipt identifies its agent.
3. **Integrity-gated.** `catch_up` MUST verify integrity before returning
   context. Corrupted projects are never silently served.
4. **Receipt-portable.** Receipts are JSON-serialisable and verifiable
   outside the project, outside the tool, outside the machine.
5. **Model-agnostic.** The protocol records *what* and *who*, never
   *which inference engine*.

---

## The maturity progression

DCP is not yet a standard. It is a protocol with a specification. The
path to standard status:

| Level | What it means | Status |
|-------|---------------|--------|
| **1. Internal protocol** | Spec written, multiple implementations by the same team | **HERE** — Zcode + LM Studio + specification |
| **2. Open protocol** | Public docs, versioning, conformance tests, reference implementations | NOT YET |
| **3. Ecosystem standard** | Multiple independent teams implement providers | NOT YET |

Level 3 is when DCP becomes real infrastructure — when another team
writes a Continuity Provider without asking Daryl's team for help.

---

## Current compliance registry

| Provider | Core | Extensions | Method | Status |
|----------|------|------------|--------|--------|
| Zcode | ✓ | — | full | **DCP 1.0 compliant** (Hot Swap MVP) |
| LM Studio | ✓ | — | full | **DCP 1.0 compliant** (Hot Swap MVP) |
| Claude Desktop | ✓ (planned) | signatures, dispatch_binding (planned) | assisted | NOT YET IMPLEMENTED |
| ChatGPT Desktop | ✓ (planned) | — | assisted | NOT YET IMPLEMENTED |
| Cursor | ✓ (planned) | — | full | NOT YET IMPLEMENTED |
| GitHub Actions | catch_up + publish only | — | full | NOT YET IMPLEMENTED |

---

## The question that changed

For over a year, the question was:

> *Que doit contenir DSM ?*

From today, the question is:

> *Que doit implémenter un acteur pour participer à la continuité d'un projet ?*

The center is no longer DSM. The center is the **contract** between DSM
and the tools. DCP v1.0 is that contract.
