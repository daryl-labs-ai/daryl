# ADR-0000 — Daryl Platform Doctrine

**Status:** ACCEPTED — Frozen
**Date:** 2026-07-08
**Type:** Governance / Platform Doctrine
**Supersedes:** Nothing. This is the root.

---

## Context

After 6 research arcs, 29 documents, 5 inter-agent validation boucles, and 6 competitive product studies, the project's center of gravity has shifted from the kernel to the connectors. The kernel (DSM 1.0) is proven sufficient for its role. The open questions now concern integration, adoption, and the user-perceived value of project continuity across changing tools.

This ADR exists to ensure that future contributors — who will not have read the 29 research documents — can immediately understand why a PR is accepted or rejected, why a feature is prioritized or deferred, and what Daryl is fundamentally for.

---

## Decision

The following seven invariants govern the Daryl platform. They are the operational expression of the Continuity Doctrine. They do not change without an explicit superseding ADR.

### Invariant 1 — The Product is Continuity

> Le produit n'est pas le kernel. Le produit est la continuité du projet.

The user does not buy a memory engine, a hash chain, or a receipt protocol. The user buys the assurance that their project continues — decisions, evidence, context, history — when they change tools, models, or agents. Everything Daryl builds serves this outcome.

### Invariant 2 — Kernel is Infrastructure, Adapters are the Product

> Le kernel est une infrastructure. Les adaptateurs sont le produit visible.

The kernel (DSM 1.0) is stable, frozen, and proven. It is the engine. The adapters (Claude, Cursor, GPT, Goose, GitHub, MCP) are the visible product surface. Development priority follows visibility: adapters and SDK before kernel enhancements.

### Invariant 3 — The Hot Swap is the Acceptance Test

> Le Hot Swap est le test d'acceptation de toute nouvelle fonctionnalité. Une fonctionnalité qui n'améliore pas le Hot Swap doit être explicitement justifiée.

The Hot Swap — *change d'outil quand tu veux, le projet n'oublie pas* — is not one demo among demos. It is the acceptance criterion for the entire platform. Every SDK method, every adapter, every kernel evolution must answer: *"Does this make the Hot Swap work, or work better?"* If the answer is no, the feature is questioned, even if technically interesting.

### Invariant 4 — Kernel Evolves Only on Demonstrated Need

> Le kernel n'évolue que lorsqu'un adaptateur démontre une limite réelle.

The kernel is frozen (DSM 1.0, since 2026-03-14). It does not reopen for improvements, optimizations, or nice-to-haves. It reopens only when:
1. An adapter hits a concrete limit that cannot be worked around at the SDK or adapter layer, AND
2. The limit is demonstrated (not hypothesised), AND
3. The fix is scoped to the minimal change that unblocks the adapter.

### Invariant 5 — Agents are Replaceable, the Project is Not

> Les agents sont remplaçables. Le projet ne l'est pas.

Individual agents (Claude, Cursor, GPT, custom) come and go. They may be upgraded, swapped, or abandoned. The project's memory, decisions, evidence, and continuity must survive every such change. This is the property Daryl exists to guarantee.

### Invariant 6 — Continuity Belongs to the Project, Never to the Tool

> La continuité appartient au projet. Jamais à l'outil.

No tool owns the project's history. No tool is the canonical source of decisions. The canonical source is the DSM shard — shared, verifiable, and independent of whichever tool last wrote to it. A tool that leaves takes nothing with it; a tool that arrives receives everything that came before.

### Invariant 7 — Daryl Preserves Continuity, It Does Not Own Agents

> Daryl ne cherche pas à posséder les agents. Il cherche à préserver la continuité lorsqu'ils changent.

Daryl is not an agent runtime. It is not a workflow orchestrator. It is not a model provider. It is the substrate that makes agents interchangeable by preserving what matters: the project's verifiable continuity. Daryl succeeds when it is invisible — when the developer changes tools and nothing is lost, without thinking about Daryl at all.

---

## The One Question

Every contribution to Daryl — every PR, every adapter, every SDK method, every demo — must answer this question before being accepted:

> **Est-ce que cela augmente la continuité du projet lorsque les agents, les modèles, les IDE ou les applications changent ?**

- **YES** → it belongs in the platform.
- **NO** → it is questioned, even if technically interesting.

This single criterion replaces 29 research documents as the day-to-day steering instrument. The research reduced the uncertainty to the point where one question suffices.

---

## Consequences

### Positive

- Any contributor can evaluate a PR against 7 invariants + 1 question.
- Product, architecture, and governance share a single criterion.
- The kernel is protected from scope creep by a freeze with explicit reopening conditions.
- The platform's value proposition is explainable in one sentence.

### Negative

- Features that are technically interesting but don't serve continuity will be rejected. This may frustrate contributors who don't understand the doctrine.
- The kernel freeze means some optimizations will be deferred until an adapter demonstrates they are needed. This requires patience.

### Neutral

- This ADR does not prescribe implementation details. It prescribes decision criteria. The implementation is free to evolve within these invariants.

---

## What this ADR replaces

This ADR supersedes all informal positioning. From this date forward:

- The two frozen sentences (developer pitch + architect description) are the canonical message.
- The Continuity Doctrine (`research/CONTINUITY_DOCTRINE.md`) is the operational expression.
- This ADR-0000 is the governance root.
- The 29 research documents are an archive, not steering instruments.

---

## Amendment rule

This ADR is amended only by a superseding ADR (ADR-0001+), which must:
1. Reference the specific invariant(s) being changed.
2. Provide evidence (not opinion) that the invariant no longer holds.
3. Be reviewed under the same governance process as any architectural change.

---

## References

- `research/CONTINUITY_DOCTRINE.md` — the operational doctrine
- `research/EPOCHS.md` — the three-epoch trajectory
- `research/DARYL_PLATFORM_ROADMAP.md` — the phased plan (Hot Swap → SDK → adapters)
- `src/dsm/core/KERNEL_VERSION` — kernel freeze record (DSM 1.0, 2026-03-14)
- `research/` — the 29-document research archive that reduced the uncertainty to this doctrine
