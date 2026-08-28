# HexaShard

**Experimental — v0.1. Not production software.**

HexaShard is a bounded project-context runtime. It keeps the working set a model
actually sees small, while the full project history stays on disk, addressable, and
attributable to primary sources.

It is a research prototype inside DARYL. It does not depend on DSM, on any model
vendor, or on a multi-agent topology.

## What it is

- **Sources** are the authority for project truth. Model output is never written back
  as a source.
- **Pins** are invariants carrying a pointer to the source that grounds them.
- **ActiveState** is the bounded working set, enforced against a token budget, and
  rotated into a new **epoch** with a bounded handoff when it saturates.
- **Retrieval** is structured filters plus lexical (BM25) search plus pin lookup.
- The **Adapter** turns that into one chat turn against a provider, and owns nothing
  that Core owns.

## What it is not

HexaShard does **not** give a model infinite context, prevent hallucination,
guarantee correct answers, or do semantic retrieval. It does not make a model more
capable. It manages what the model is shown.

The name is historical. There are no agents, no hex routing, and no six-port
topology — those were tested and rejected. A "Hex" is an addressable context unit.

## Measured properties

Everything here is a specific measurement on a specific fixture, not a general claim.
See [EVIDENCE.md](EVIDENCE.md) and [LIMITATIONS.md](LIMITATIONS.md).

- On the MERIDIAN-9 synthetic project (170,855 stored tokens), peak active state was
  **5,384 tokens** against a 6,000 budget — a store-to-active ratio of **31.7x** on
  that fixture.
- On the Adapter smoke project (101,627 stored tokens), mean model-visible context was
  **336 tokens**, peak **363**.
- Against a local `qwen3.6:35b-a3b`, at a 250k-token stored project the ordinary
  full-context arm could not run at all while the HexaShard arm completed. At smaller
  sizes the two arms answered within one question of each other.

## Repository status

An independent runtime temporarily co-located in DARYL — not a DSM module, and
excluded from the `daryl-dsm` distribution. Its repository boundary and
extraction triggers are governed by
[ADR-HEXASHARD-0001](../architecture/ADR-HEXASHARD-0001-repository-boundary.md).

## Layout

```
src/hexashard/            Core — frozen v0.1, byte-identical to the archived release
src/hexashard_adapter/    Adapter — chat runtime over Core
tests/hexashard/          Core suite (68)
tests/hexashard_adapter/  Adapter suite (34) + gate regressions (12)
docs/hexashard/           this documentation
```

## Use

A project is not a chat session. The chat window can be empty, on another
machine, or pointed at a different provider; the project is what persists. These
commands maintain it — no Python required.

```bash
python -m hexashard_adapter create ./launch --name launch --mission "Ship it."

python -m hexashard_adapter source add ./launch \
    --type legal --title "Data residency" \
    --text "All customer data stays in the EU. Non-negotiable."

python -m hexashard_adapter pin ./launch \
    --key residency --value "EU only" --source "Data residency" --critical

python -m hexashard_adapter chat ./launch --provider ollama
```

`python -m hexashard_adapter --help` lists everything. Sources are referred to by
title or by id — you never have to invent an id, and an ambiguous title is an
error rather than a guess.

### Keeping the project true

**Sources ground; pins point.** A pin records an invariant *and the source that
backs it*. Pinning without `--source` is refused unless you pass `--ungrounded`
to say you meant it.

**Superseding** makes one source replace another. The old one stays retrievable
as history:

```bash
python -m hexashard_adapter source add ./launch --type finance \
    --title "Budget revision" --text "The budget is now 1.8M." \
    --claim-key budget --claim-value "1.8M"
python -m hexashard_adapter supersede ./launch --old "Budget" --new "Budget revision"
```

Declaring `--claim-key`/`--claim-value` lets a pin on that fact carry the new
value forward automatically. **Without it the pin keeps its old value**, is marked
`NEEDS_REVIEW`, and `supersede` tells you so — see LIMITATIONS.

**A decision is something you record, not something the model says.** A model
answer never becomes project truth, and neither does the transcript:

```bash
python -m hexashard_adapter decision ./launch "Launch moves to 12 November."
python -m hexashard_adapter question add ./launch --text "Who covers Spain?"
python -m hexashard_adapter question resolve ./launch --id Q1
```

### Asking without changing anything

`chat --mode READ_ONLY` answers from the project and mutates nothing — no turn,
no epoch, no bytes written. It is a flag you choose up front, which is a known
usability limitation rather than a design goal.

### When the provider fails

A turn that produces no response does not persist. If generation fails, the
project is left exactly as it was — same turn, same epoch, same state — and the
request can simply be retried. The failure is still recorded in the adapter's
metrics, because observability is not project truth.

Run the tests:

```bash
python -m pytest tests/hexashard tests/hexashard_adapter
```

## Core integrity

The Core was frozen as an archive before any downstream experiment ran. Its modules
were migrated here byte-for-byte, and `hexashard_adapter.core_lock` pins their
digests. Every Core and Adapter test asserts the Core is unmodified.

```
archive SHA-256: 268f0f08362982c2c6e85d5672d9f2e9efcc34f2e3306d40f5ee23e3763ca999
```
