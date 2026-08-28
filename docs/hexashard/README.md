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

## Layout

```
src/hexashard/            Core — frozen v0.1, byte-identical to the archived release
src/hexashard_adapter/    Adapter — chat runtime over Core
tests/hexashard/          Core suite (68)
tests/hexashard_adapter/  Adapter suite (34) + gate regressions (12)
docs/hexashard/           this documentation
```

## Use

```python
from hexashard_adapter import AdapterConfig, HexaShardAdapter

adapter = HexaShardAdapter.create(
    "./my-project", name="my-project", mission="Ship the thing.",
    config=AdapterConfig(provider="mock"),
)
source = adapter.add_source("spec", "Budget", "The downlink budget per pass is 6.1 TB.")
adapter.pin("downlink", "6.1 TB", source.source_id, critical=True)

result = adapter.chat("What is the downlink budget?")
print(result.response_text, result.retrieved_source_ids, result.pin_warnings)
```

Use `mode="READ_ONLY"` for questions that must not advance project state — see
LIMITATIONS.

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
