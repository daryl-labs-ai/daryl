# Daryl — Three Epochs

**Milestone date:** 2026-07-08 — Continuity Doctrine
**Status:** Architectural governance record. Not a research document.

---

## The three epochs

### Epoch 1 — "Memory"

**Question:** *Comment donner une mémoire aux agents ?*

This is where DSM was born. Append-only storage, hash chains, entries,
shards. The goal was simple: an agent that forgets nothing.

**Status:** Complete. The kernel (DSM 1.0) is its legacy.

---

### Epoch 2 — "Trust"

**Question:** *Comment rendre cette mémoire vérifiable ?*

This is where receipts, dispatch, attestation, provenance, identity, and
signatures arrived. The goal shifted from "remember" to "prove you
remember correctly".

The laboratory lived entirely in this epoch: 28 documents, 6 research
arcs, competitive studies, falsification tests, the Operational Envelope,
the Relational Trust Model.

**Status:** Closed 2026-07-08. The lab reduced the uncertainty to the
point where the remaining questions require real integrations, not more
hypotheses. The kernel is proven sufficient.

---

### Epoch 3 — "Continuity"

**Question:** *Comment un projet continue à vivre alors que tous ses
outils changent ?*

This is where Daryl stops being a memory product and becomes an
infrastructure. The competitor is no longer Mem0 or Letta or LangGraph.
The competitor is **the cost of changing tools** — the lost context, the
reconstruction effort, the broken handoff that happens today when a
developer switches from Claude to Cursor to GPT.

**Status:** Began 2026-07-08. Governed by the Continuity Doctrine.

---

## The milestone

**2026-07-08 — Continuity Doctrine**

From this date:
- The kernel is frozen (since 2026-03-14, reaffirmed).
- The doctrine is frozen (Continuity Doctrine, this date).
- Future evolutions must demonstrate they increase project continuity
  across agent/model/IDE/application changes.
- The laboratory is closed for speculation. It reopens only for facts.

---

## Laboratory reopening conditions

The laboratory does not reopen for ideas. It reopens only when a **new
fact** appears that the current architecture cannot handle:

| Trigger | Example |
|---------|---------|
| An adapter reveals a real kernel limit | catch_up() needs a primitive the kernel doesn't provide |
| The Hot Swap fails for an architectural reason | context reconstruction is impossible without kernel change |
| A public demo exposes an uncovered case | multi-machine requires remote storage primitives |
| A new paradigm challenges a fundamental assumption | a widely-adopted inter-agent protocol changes the trust model |

Until one of these occurs, the platform learns by usage, not by
speculation.

---

## The definition

> *Une infrastructure de continuité de projet permettant à des agents et
> des applications hétérogènes de partager une mémoire vérifiable sans
> que cette continuité dépende d'un outil particulier.*

This is more precise than "memory for agents". It reflects what the
research proved and what the platform now exists to demonstrate.

---

## What the three epochs look like as a trajectory

```
Epoch 1: Memory         "L'agent se souvient"
    ↓
Epoch 2: Trust          "L'agent prouve ce dont il se souvient"
    ↓
Epoch 3: Continuity     "Le projet continue quand l'agent change"
```

Each epoch subsumes the previous. Continuity requires trust (you can't
continue what you can't verify). Trust requires memory (you can't verify
what wasn't recorded). The kernel serves all three; the product is the
third.

---

## Governance summary

| Frozen | Since | Rule |
|--------|-------|------|
| **Kernel** (DSM 1.0) | 2026-03-14 | Evolves only on demonstrated adapter need |
| **Doctrine** (Continuity) | 2026-07-08 | Evolves only after months of platform validation |
| **Laboratory** | 2026-07-08 | Closed for speculation; reopens only on new facts |

Three things frozen. One question governing all future work:

> *Est-ce que cela augmente la continuité du projet lorsque les agents,
> les modèles, les IDE ou les applications changent ?*
