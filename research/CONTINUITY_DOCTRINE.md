# The Continuity Doctrine

**Status:** Frozen. This is the governing principle of the Daryl platform.
It does not change for at least several months. Every feature, adapter,
SDK method, and demo must be evaluated against it.

---

## The shift

Daryl is no longer evaluated as software. It is evaluated as
infrastructure.

The success metric inverts:

| Before (software) | After (infrastructure) |
|---|---|
| "Does DSM work?" | "How many tools can forget they use DSM?" |
| Tests, benchmarks, invariants | Transparent continuity across tool swaps |
| The user thinks: "I will use DSM" | The user thinks: "Nothing was lost when I switched tools" |

The best adapter is the one whose existence is invisible. The best SDK is
the one a developer never reads the docs for. The product is not the
kernel, the SDK, or the adapters.

**The product is continuity.**

---

## The equation

```
Agent Memory          →  what DSM started as (a memory for one agent)
Project Memory        →  what DSM became (shared memory for a project)
Project Continuity    →  what DSM is now (the project survives every change)
```

A memory can be replaced. Continuity becomes a property of the entire
platform. That is what the user buys.

---

## The two frozen sentences

These do not change. Every demo, adapter, and release reinforces them.

**For developers:**

> Change d'outil quand tu veux. Le projet n'oublie pas.

**For architects:**

> Daryl déplace la continuité du projet hors des outils qui le manipulent.

---

## The one governance question

Before any new feature, adapter, SDK method, or change is accepted:

> **Est-ce que cela augmente la continuité du projet lorsque les agents,
> les modèles, les IDE ou les applications changent ?**

- **YES** → it belongs in the platform vision.
- **NO** → it is questioned, even if technically interesting.

This is the single criterion that replaces 26 research documents as the
day-to-day steering instrument. The research reduced the uncertainty to
the point where one question suffices.

---

## Relationship to the frozen kernel

Two things are now frozen:

1. **The kernel** (DSM 1.0) — frozen since 2026-03-14. Evolves only when
   an adapter demonstrates a concrete limit.
2. **The message** (Continuity Doctrine) — frozen from this document.
   Evolves only after several months of platform validation prove a
   better framing.

Kernel + Message. The engine and the compass. Both stable. The work is
now in the connectors, not in either of these.
