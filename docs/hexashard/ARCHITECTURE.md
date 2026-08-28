# HexaShard v0.1 — Architecture

Two layers, one direction of trust: **Core owns project truth; the Adapter and the
model do not.**

```
      user turn
          |
          v
+---------------------------+
|  Adapter                  |   assembles a bounded, model-visible working set
|  - provider boundary      |   never writes model prose back as a source
|  - context assembly       |   enforces the model-context budget
|  - session continuity     |
+------------+--------------+
             | retrieve / handle_turn
             v
+---------------------------+
|  Core (frozen v0.1)       |
|  Sources | Pins | Hexes   |
|  ActiveState | Epochs     |
|  Retriever | Trust        |
+------------+--------------+
             |
             v
      on-disk project
```

## Core

**Sources** are primary material and the only grounding authority. Each carries a
status (`CURRENT`, `SUPERSEDED`, `DRAFT`, `UNVERIFIED`), an optional `claim_key` it is
authoritative for, and content stored separately on disk. Supersession is explicit and
bidirectional: the old source keeps `SUPERSEDED` plus a `superseded_by` pointer, and
stays retrievable under an explicit status filter. History is never deleted.

**Pins** are invariants with a mandatory pointer to a grounding source, and a
lifecycle: `ACTIVE`, `STALE`, `NEEDS_REVIEW`, `BROKEN`, `SUPERSEDED`. Reconciliation
walks the supersession chain and adopts a new value **only** when the successor is
CURRENT and declares a matching claim. It never invents a value.

**Hexes** are addressable context units — `project.epoch.sequence`. They are not
agents, they hold no model, and they do not talk to each other. Relations between them
form a generic graph with no degree limit; there is no six-neighbour routing.

**ActiveState** is the bounded working set: mission, objective, summary, active pins,
open questions, recent decisions, hex references, retrieval hints. It is enforced
against a token budget with a defined drop order — retrieval hints first, then hex
refs, then decisions — so what is lost is what is cheapest to regenerate.

**Epochs** rotate when ActiveState saturates. Rotation carries a bounded handoff into
the new epoch and preserves critical pins. If rotating would carry the same oversized
core forward, Core reports `saturated` instead of churning epochs.

**Retrieval** combines structured filters, BM25 lexical search and pin lookup, under
its own token budget. Primary CURRENT sources win by default; superseded material
requires an explicit status filter and is returned labelled as history. Two CURRENT
sources sharing a `claim_key` are reported as a structural ambiguity rather than
silently ranked.

**Trust** is an interface with a null default. Nothing in Core depends on a trust log
or on DSM.

Persistence is atomic per file: temp file in the same directory, `fsync`, `os.replace`,
then a directory `fsync`.

## Adapter

The Adapter turns Core state into one model-visible turn and sends it to a provider.

**Context assembly** builds the block in priority order — critical pins, mission and
objective, retrieved source fragments, state, warnings — and drops from the bottom
against `model_context_budget`. If the protected part alone exceeds the budget it
raises rather than silently dropping a critical pin.

**The provider boundary** is a small protocol (`mock`, `ollama`) using only the
standard library. Endpoints are restricted to `http`/`https`. A reply that does not
match the expected shape raises `MalformedProviderResponse`.

**Model output is never a source.** The Adapter persists its own metrics and nothing
else. Project truth changes only through explicit `add_source`, `pin` and `supersede`
calls.

**Modes.** `NORMAL` calls `Core.handle_turn()`, which advances project state.
`READ_ONLY` is an Adapter-level wrapper over `Core.retrieve()` that mutates nothing and
writes nothing, and refuses write operations. It is not a Core mode.

**Session continuity** comes from the project on disk, not from a transcript. Closing
and reopening a project restores state, map, pins and cold sources; the visible chat
history is irrelevant to what the model is told.

## Repository status

HexaShard is an **independent runtime temporarily co-located in DARYL**. It is not
a DSM or PRL module: nothing here imports `dsm` or `prl`, nothing there imports
HexaShard, and HexaShard is deliberately excluded from the `daryl-dsm`
distribution.

That boundary is a hard invariant, enforced in CI by
`scripts/forbid_cross_boundary_imports.py`. The reasoning, the conditions under
which HexaShard moves to its own repository, and what happens when it does are
governed by
[ADR-HEXASHARD-0001](../architecture/ADR-HEXASHARD-0001-repository-boundary.md).

## The boundary rule

The Adapter holds no copy of project truth. Every fact it shows a model is read from
Core at turn time and cited by source id and status. This is what makes the Core
freeze meaningful: the Adapter can be rewritten without re-opening any Core evidence.

## What was tested and rejected

Recorded because the name and the history suggest otherwise:

| Rejected | Why |
|---|---|
| an agent per Hex | no measured benefit over summary + retrieval |
| six-neighbour routing | not supported by the evidence |
| packets as truth | grounding belongs to primary sources |
| spatial retrieval prior | harmful as a default retrieval filter |
| six named ports | not a Core requirement |
| DSM as working memory | pins + retrieval reproduce the operational benefit |

Direct global addressing and unrestricted logical relations were kept.
