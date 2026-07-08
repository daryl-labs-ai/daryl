# Capability Exposure — A product governance principle

**What this is:** a permanent rule, distilled from two product gap scans,
governing how Daryl's internal capacity becomes a user/agent-facing
surface. Not a target. A discipline.

**Origin:** the two scans in `research/memos/` measured that an agent
over MCP can invoke 7 % of Daryl's capacity while a human at the CLI
can invoke 50 %. That asymmetry is not itself the disease — it is the
symptom of building capacity faster than exposing it, with no rule to
force the question *"should this be reachable?"*

---

## The principle — Capability-first exposure

A capability is exposed only if **all four** conditions hold:

1. **It solves an observed friction.** Not "could be useful" — a named
   workflow where its absence blocks a user or agent today.
2. **It fits an identified product workflow.** It composes with other
   surfaces into a path a real consumer would walk.
3. **It has contracts and tests.** No exposing-by-experiment on the
   public surface. The method must already be stable above the kernel.
4. **It does not add unnecessary complexity to the public surface.** A
   tool count is a UX cost. Each new exposure must justify its weight.

If any one of the four fails, the capability stays internal until it
passes. There is no default to expose.

**The corollary, equally important:** a capability that is *hidden* must
have a reason. "Nobody got around to it" is not a reason — it is the
absence of a decision. The principle forces the decision either way.

---

## The metric — Capability Exposure Ratio

Tracked per release, for each surface:

```
                    capabilities exposed on that surface
    Ratio_S  =  ────────────────────────────────────────────
                    total capabilities (DarylAgent methods)

    S  ∈  { CLI, MCP, SDK (__init__) }
```

Measured at `DarylAgent` today (82 methods):

```
    CLI :  50 %    (41 / 82)
    MCP :   7 %    ( 6 / 82)
    SDK :   0 %    ( 0 / 82)   — DarylAgent not exported
```

### What the metric is for

- A **drift detector**. If the ratio falls between releases, capacity was
  added without exposure — ask why before it accumulates.
- A **deliberation prompt**. Each capability below 100 % total exposure
  must have an explicit reason: *agent-only, operator-only, internal-plumbing,
  deferred-until-usage, or pending-decision*.

### What the metric is NOT for

- **Not a target.** "Reach X %" is a misuse. It is entirely possible —
  likely — that ~25 % of methods cover ~95 % of real agent usage.
- **Not monotonic.** A surface can legitimately shrink if capabilities
  are merged or re-scoped.
- **Not a comparison between surfaces.** CLI and MCP serve different
  consumers; their ratios will differ by design. The asymmetry is
  informative, not a defect to "fix" by copying CLI to MCP.

The discipline is: **every capability has a labelled exposure decision.**
The ratio surfaces the unlabelled ones.

---

## Decision labels

Each capability carries exactly one label on each surface:

| Label | Meaning |
|-------|---------|
| `exposed` | reachable on this surface today |
| `agent-only` | intended for MCP exposure, not CLI |
| `operator-only` | intended for CLI, not MCP (e.g. shard lifecycle, sovereignty policy) |
| `internal` | facade plumbing (`storage`, `graph`, …); not for any consumer |
| `deferred` | passes the 4 criteria in principle, but waiting for usage signal before exposure |
| `pending` | no decision yet — this is the label the ratio is meant to drive to zero |

A capability may legitimately be `exposed` on one surface and `operator-only`
on another. The point is that the choice is explicit, not accidental.

---

## Operationalisation

At each release:
1. Re-run the capability/exposure count (mechanical grep — see the scan
   scripts in `research/memos/`).
2. List every capability whose label is `pending`. Force a decision on
   each: one of the five other labels.
3. Record the ratios. Note drift, do not chase a number.

The artefact is a single table — capability × surface × label — small
enough to review in one sitting. The point is the deliberation, not the
table.

---

## Why this matters beyond DSM

The two scans found that the highest-leverage product work was not
*building new things* but *exposing already-built things*. That is a
class of improvement that gets missed when a team's instinct is
forward-looking ("what do we add next?"). The Capability Exposure
discipline institutionalises the opposite question — *"what have we
already built that nobody can reach?"* — as a recurring product action.

It is also the natural complement to the Operational Envelope
(`research/2026-OrchestratedMemory/OPERATIONAL_ENVELOPE.md`). The
Envelope measures *how the system behaves*. Capability Exposure
measures *how much of that behaviour is reachable*. Together they
describe the product as it actually exists, not as it aspires to be.
