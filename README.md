<p align="center">
  <img src="assets/daryl_logo.png" width="220">
</p>

<h1 align="center">Daryl</h1>

<p align="center">
Deterministic Sharding Memory for AI Agents
</p>

<p align="center">
Created by <strong>Mohamed Azizi</strong><br>
<a href="https://www.daryl.md">www.daryl.md</a>
</p>

<p align="center">
<img src="https://github.com/daryl-labs-ai/daryl/actions/workflows/ci.yml/badge.svg">
<img src="https://img.shields.io/badge/python-3.10%2B-blue">
<img src="https://img.shields.io/badge/license-MIT-green">
</p>

---

Daryl is an experimental architecture for deterministic AI agent memory.

It introduces **DSM (Daryl Sharding Memory)** — an append-only sharded event log designed for:

- deterministic memory
- replayable agent history
- verifiable integrity
- scalable shard segmentation

DSM enables AI agents to store events in a **deterministic memory layer** that can be replayed, verified and audited.

## Project Status

Daryl is an experimental research project exploring deterministic
memory architectures for AI agents.

The core storage layer (**DSM Core**) is frozen as of March 2026
and considered stable.

Higher-level modules such as:

- RR (Read Relay)
- ANS (Adaptive Navigation System)
- Skills

may evolve as the architecture grows.

---

## Overview

Daryl provides a **deterministic memory kernel** (DSM — Daryl Sharding Memory) for AI agents: append-only, shard-based event logs with hash-chain integrity and replay verification.

- **Append-only memory**: Events are written as immutable entries; existing entries are never modified or deleted.
- **Shard segmentation**: Data is organized by shards (e.g. `sessions`, `default`, custom names). Each shard is a logical log; physically it may span one or several segment files.
- **Hash-chain integrity**: Each entry can carry a content hash and a reference to the previous entry's hash (`prev_hash`), enabling integrity checks and deterministic replay of a shard.
- **Replay verification**: Traces can be verified and replayed from the ordered, chained stream of entries.

DSM does not provide query/search or vector search; it is an ordered, append-only event log. Agents read recent entries from a shard and interpret them in their own logic.

## Architecture

- **DSM Core**: Frozen kernel (storage, models, segments). See [ARCHITECTURE.md](ARCHITECTURE.md).
- **Sessions**: Lifecycle management (session start/end, snapshots, tool calls) via `SessionGraph`.
- **RR (Read Relay)**: Read-only relay over DSM storage (summaries, recent reads).
- **ANS (Adaptive Navigation System)**: Analysis of skill performance and workflow recommendations.
- **Skills**: Registry and router for matching tasks to skills.

See full architecture diagram in: [docs/architecture_diagram.md](docs/architecture_diagram.md)

## Installation

From the repository root:

```bash
pip install -e .
```

For development (tests, coverage):

```bash
pip install -e .[dev]
```

## Quick Example

From the repository root (after `pip install -e .`):

```python
from datetime import datetime
from uuid import uuid4
import tempfile
from dsm.core.storage import Storage
from dsm.core.models import Entry

with tempfile.TemporaryDirectory() as tmp:
    storage = Storage(data_dir=tmp)
    entry = Entry(
        id=str(uuid4()),
        timestamp=datetime.utcnow(),
        session_id="example",
        source="readme",
        content="Hello DSM",
        shard="default",
        hash="",
        prev_hash=None,
        metadata={},
        version="v2.0",
    )
    storage.append(entry)
    entries = storage.read("default", limit=10)
    print("Entries:", len(entries))
    if entries:
        print("Latest:", entries[0].content)
```

## Why DSM?

| Approach | Model | Trade-off |
|----------|-------|-----------|
| RAG + Vector DB | Semantic similarity search | Fast retrieval, but non-deterministic — same query can return different results |
| Structured logs | Append-only text files | Deterministic, but no query layer or integrity guarantees |
| DSM | Append-only sharded event log with hash chain | Deterministic replay and verification, but no semantic search |

## Running tests

```bash
python -m pytest tests/ -v
```

## Repository Structure

```
src/
  dsm/
    core/       # frozen append-only storage
    rr/         # read relay navigation
    ans/        # analytics and insights
    skills/     # agent skill registry
    session/    # session graph

tests/          # unit and integration tests
assets/         # logos and images
docs/           # architecture documentation
```

- `src/dsm/` — DSM package: `core` (frozen), `session`, `rr`, `ans`, `skills`, etc.
- `tests/` — Pytest test suite (core, session, skills, rr, ans, integration).
- `scripts/` — Runners and utilities.
- `docs/` — Documentation.

## Contributing Quick Start

```bash
git clone https://github.com/daryl-labs-ai/daryl
cd daryl

pip install -e .[dev]

python -m pytest tests/
```

Note: the DSM storage kernel located in `src/dsm/core/`
is considered frozen and should not be modified without
opening a design discussion.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Do not modify `src/dsm/core/` without discussion and approval; the DSM kernel is frozen.
