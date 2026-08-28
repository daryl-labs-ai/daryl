# ADR-HEXASHARD-0001 — HexaShard Repository Boundary and Extraction Triggers

**Status:** Accepted · **Version:** v1 · **Date:** 2026-08-28 · **Scope:** repository architecture
**Applies to:** `src/hexashard`, `src/hexashard_adapter`
**Enforced by:** `scripts/forbid_cross_boundary_imports.py`, `tests/test_forbid_cross_boundary_imports.py`
**Canonical main at ratification:** `975092f95116714eaf9066b35fe3e2e2c890152a`

> **HexaShard is an independent runtime temporarily co-located in DARYL.**
> **Co-location must not become accidental coupling.**

## Context

HexaShard entered this repository through two reviewed gates: Core v0.1 + Adapter
v0.1 (PR #137) and Product Seam v0.1.1 (PR #138). Along the way it acquired its
own frozen Core, its own tests, its own CLI, its own limitations document and its
own experimental roadmap — and it was deliberately excluded from the `daryl-dsm`
distribution.

That raises a question the code cannot answer on its own: does HexaShard belong
in this repository at all?

The distinction that settles it:

> HexaShard already has an independent **lifecycle**.
> HexaShard does not yet have an independent **consumer**.

A repository boundary exists to serve a consumption boundary. There is not one
yet.

## Decision

**Keep HexaShard in `daryl-labs-ai/daryl` for now. Split on a defined trigger,
not on taste.**

Three things follow, and they are the whole decision:

1. HexaShard stays, described accurately as an independent runtime that is
   temporarily co-located — not as a DARYL module.
2. A hard no-cross-import invariant is frozen and mechanically enforced, so the
   cost of extracting later does not quietly rise.
3. Four triggers are defined in advance. When the first one fires, the boundary
   is re-decided *before* the coupling lands.

## Current architecture

```
        daryl repository
  ┌──────────────────────────────────┐
  │  src/dsm ──► src/prl             │   daryl-dsm distribution
  │                                  │
  │  src/hexashard                   │   not distributed
  │  src/hexashard_adapter           │   source-only
  └──────────────────────────────────┘
             no imports either way
```

HexaShard is **not** a DSM module, **not** a PRL module, **not** part of the
`daryl-dsm` distribution, **not** dependent on DSM, and **not** consumed by DSM.

## Evidence

Verified against `main @ 975092f` when this ADR was written, not assumed:

| Fact | Verified |
|---|---|
| `hexashard`, `hexashard_adapter` → `dsm`, `prl` imports | **0** |
| `dsm`, `prl` → `hexashard`, `hexashard_adapter` imports | **0** |
| textual mentions of `hexashard` anywhere in `src/dsm`, `src/prl` | **0 files** |
| textual mentions of `dsm`/`prl` anywhere in the HexaShard trees | **0 files** |
| HexaShard in the `daryl-dsm` wheel | **no** — wheel is `dsm` + `prl`, 164 files |
| HexaShard Core | frozen v0.1, digest `5b6a78e5…`, byte-identical since PR #137 |
| Adapter, CLI (8 verbs), Product Seam v0.1.1 | present, merged |
| standalone HexaShard distribution / release / tag / repository | **none** |

The coupling is not merely low. It is **zero, in both directions, including in
prose.**

## Organizational context

`daryl-labs-ai` is not governed as a single universal monorepo. It currently
contains `daryl`, `daryl-mecalabs`, `dsm-claude-code`, `dsm-grounding` and
`dsm-unsloth`.

A future `daryl-hexashard` would therefore be architecturally consistent with how
this organization already works. **That consistency is not, by itself, a reason
to extract anything.**

## Alternatives considered

**A — Extract to `daryl-labs-ai/daryl-hexashard` now.** Rejected. It would solve
no observed problem while creating real machinery: a second CI setup, a second
review surface, a second dependency to keep in step. There is no external
consumer, no standalone package, no release, and no runtime dependency in either
direction. Extraction now would be organizational symmetry bought with
operational overhead.

**B — Declare HexaShard a permanent DARYL subsystem.** Rejected, and it is the
more dangerous option. It contradicts the evidence — the frozen Core, the
separate limitations, the packaging exclusion, the independent roadmap — and it
would license exactly the convenience imports that make extraction expensive
later. Calling something a module is how it becomes one.

**C — Keep temporarily, split on a defined trigger.** **Chosen.** It matches what
is actually true today, costs nothing, and converts a recurring judgement call
into a rule that can be checked.

## Why not split now

A standalone repository today would not solve an observed product or engineering
problem. There is currently:

- no external HexaShard consumer
- no standalone package or release
- no required git dependency
- no DARYL → HexaShard runtime dependency
- no HexaShard → DARYL runtime dependency

**Do not split merely for cleanliness or branding.**

## Why HexaShard is nevertheless independent

It has crossed lifecycle boundaries that a mere module does not: a frozen and
independently reproduced Core v0.1; an Adapter; live provider experiments; two
independent CLI dogfoods; independent Cursor and Claude reviews; Product Seam
v0.1.1 with its own authoring CLI and turn-atomicity semantics; its own
limitations; its own experimental roadmap; and deliberate exclusion from the
`daryl-dsm` distribution.

So the accurate description is **not** "HexaShard is just another DARYL module".
It is **"independent runtime, temporarily co-located"**.

## The no-cross-import invariant

**Frozen, hard, both directions:**

> `hexashard` / `hexashard_adapter` **must not** import `dsm` or `prl`.
> `dsm` / `prl` **must not** import `hexashard` or `hexashard_adapter`.

Not without a separate, explicit architecture decision that supersedes or amends
this ADR.

This exists to preserve independent runtime ownership, prevent accidental
coupling, keep future extraction cheap — and above all to stop a convenience
import from silently deciding the repository architecture.

Enforced by `scripts/forbid_cross_boundary_imports.py`, run in CI and covered by
`tests/test_forbid_cross_boundary_imports.py`. There is deliberately **no
allowlist and no per-line escape hatch**: an exception is a repository decision,
so it belongs in a new ADR, not in a list at the top of a lint. Type-only
`TYPE_CHECKING` imports are **not** exempt, because a type-only dependency still
means the package cannot travel to its own repository alone.

## Extraction triggers

HexaShard moves to `daryl-labs-ai/daryl-hexashard` when the **first** of these
occurs:

**Trigger 1 — external / independent consumer.** Someone needs to use HexaShard
without cloning the whole `daryl` repository.

**Trigger 2 — standalone distribution.** HexaShard needs any independent
distribution boundary: a package, a release or tag, a `git+https` dependency, or
an equivalent independently consumable artifact.

**Trigger 3 — cross-import pressure.** A legitimate PR requires a production
dependency between DSM/PRL and HexaShard in either direction. **The cross-import
is not merged first.** The proposal itself re-opens this decision.

**Trigger 4 — third provider.** HexaShard gains a provider beyond `mock` and
`ollama`, which is evidence that provider integration has become an independently
evolving lifecycle.

At the first trigger: **stop normal feature integration, open the
repository-extraction gate, and decide the boundary before introducing avoidable
coupling.**

## Not triggers

Continuing to develop HexaShard is not a trigger. None of these, alone, justifies
extraction: the historical-retrieval experiment; stale-pin UX work;
crash-consistency work; CLI improvements; further dogfooding; documentation; or
internal refactoring that preserves the boundary.

## Future repository

The destination is **`daryl-labs-ai/daryl-hexashard`** — *not* `dsm-hexashard`,
because HexaShard is not a DSM subsystem. It remains source-oriented on arrival.

Extraction does **not** authorize PyPI publication, a package release, a semantic
version, or a public launch. Those are separate decisions.

## Source of truth

If extraction happens there must be **exactly one canonical HexaShard source
tree**: `daryl-hexashard`. The production source is then **removed** from
`daryl`.

Explicitly rejected: manual mirrors, duplicated canonical trees, copy-and-sync
workflows, manually maintained vendored duplicates. `daryl/src/hexashard` and
`daryl-hexashard/src/hexashard` must never both be editable.

## Dependency direction

Default after extraction is **siblings with no dependency**:

```
   daryl  ⟷  (none)  ⟷  daryl-hexashard
```

Do not invent a dependency merely because extraction happened. If a real
integration later requires one, the permitted direction is **DARYL → HexaShard**.
Avoid **HexaShard → DSM**, and never introduce a bidirectional dependency.

## Distribution strategy

Today: source-only. At repository split: still source-only by default. Create a
standalone package only when there is evidence that someone needs to install
HexaShard without cloning its repository. **Repository boundary and package
boundary are separate decisions.**

## Migration principles

When extraction happens — *not now* — the expected split is:

**Moves:** Core, Adapter, CLI, HexaShard tests, architecture and limitations
docs, public API documentation, the fixtures the tests need, and a condensed
evidence summary.

**Stays or is archived in DARYL:** large research campaigns, historical dogfood
transcripts, unrelated DSM experiments, repository-wide review history, and old
experimental artifacts not required to operate HexaShard.

**Do not turn the product repository into a dump of the research history.**

Preserve meaningful git provenance where practical, but **history preservation
must never produce two canonical repositories**. Evaluate history filtering, a
clean extraction, or a provenance document pointing back at DARYL commits at that
time. The mechanism is deliberately not chosen here.

## Consequences

HexaShard keeps shared CI, a shared development environment, shared review
infrastructure and low operational overhead, while retaining runtime, import and
packaging independence.

The invariant is now mechanical rather than remembered, so it survives people
forgetting this document.

Extraction complexity today is **low–medium** — zero production cross-imports, no
packaging dependency, no runtime dependency. It stays low while the invariant
holds, and becomes **medium–high** if DSM/PRL and HexaShard ever couple in-tree.
That asymmetry is the entire reason the guard exists.

The cost is that a genuinely needed cross-import is now slower to land: it has to
go through an architecture decision first. That is the intended trade.

## Known risks

- **A dynamic import bypasses the guard.** `importlib.import_module("dsm...")`
  is not detected by AST inspection. Code review remains the backstop.
- **Coupling can occur without an import** — shared file formats, shared
  on-disk layout, shared conventions. The guard does not see these.
- **Triggers can be met without anyone noticing**, particularly Trigger 1. The
  triggers depend on human attention; only Trigger 3 is mechanically visible.
- **Delay has a cost too.** If several triggers fire at once, extraction happens
  under pressure rather than calmly.

## Revisit conditions

Revisit when any extraction trigger fires; when a cross-import is proposed; when
HexaShard gains an external consumer or a distribution boundary; or if the
premise that HexaShard has no independent consumer stops being true.

Until then, the sentence that must remain true is:

> **HexaShard is an independent runtime temporarily co-located in DARYL.**
