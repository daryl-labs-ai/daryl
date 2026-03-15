<p align="center">
  <img src="assets/daryl_logo.png" width="220">
</p>

<h1 align="center">Daryl</h1>

<p align="center">
<strong>Provable memory for AI agents</strong>
</p>

<p align="center">
Created by <strong>Mohamed Azizi</strong> · <a href="https://www.daryl.md">daryl.md</a>
</p>

<p align="center">
<img src="https://github.com/daryl-labs-ai/daryl/actions/workflows/ci.yml/badge.svg">
<img src="https://img.shields.io/badge/python-3.10%2B-blue">
<img src="https://img.shields.io/badge/license-MIT-green">
<img src="https://img.shields.io/badge/tests-67%20passing-brightgreen">
<img src="https://img.shields.io/badge/kernel-frozen%20%C2%B7%20stable-blueviolet">
</p>

---

AI agents forget everything between sessions.
When they don't, you can't verify what they remember.

**DSM (Daryl Sharding Memory)** gives agents a memory they can prove — an append-only event log where every entry is hash-chained, every session is replayable, and every claim is verifiable with one command.

## What agents get

- **Total recall** — every action, snapshot, and decision is logged as an immutable entry. Nothing is lost, nothing is overwritten.
- **Tamper-proof history** — each entry carries a SHA-256 hash chained to the previous one. Alter one byte, the chain breaks.
- **One-command verification** — `dsm verify --shard sessions` checks the entire history in milliseconds.
- **Structured sessions** — start, act, observe, end. The agent's lifecycle is a first-class concept, not an afterthought.

## 10 seconds to memory

```python
from dsm.core.storage import Storage
from dsm.session.session_graph import SessionGraph
from dsm.session.session_limits_manager import SessionLimitsManager

storage = Storage(data_dir="memory")
limits = SessionLimitsManager.agent_defaults("memory")
session = SessionGraph(storage=storage, limits_manager=limits)

session.start_session(source="my_agent")
session.execute_action("search", {"query": "weather in paris"})
session.execute_action("reply", {"text": "It's sunny in Paris"})
session.end_session()
```

4 events written. Hash-chained. Replayable. Done.

## Verify everything

```
$ dsm verify --shard sessions

shard_id: sessions
total_entries: 4
verified: 4
tampered: 0
chain_breaks: 0
status: OK
```

If anyone — or anything — modifies the history, DSM catches it.

## How it compares

| What you need | Logs | Vector DB | DSM |
|---|:---:|:---:|:---:|
| Replay exact agent history | ❌ | ❌ | ✅ |
| Prove nothing was altered | ❌ | ❌ | ✅ |
| Audit agent behavior | ❌ | ❌ | ✅ |
| Semantic search | ❌ | ✅ | ❌ |

DSM doesn't replace a vector database. It complements it — **the vector DB searches, DSM proves.**

## Architecture

```
Your Agent
    ↓
SessionGraph          ← lifecycle: start, snapshot, action, end
    ↓
RR (Read Relay)       ← query: recent entries, summaries, filters
    ↓
DSM Core              ← storage: append-only, hash-chained, frozen
```

The kernel (`src/dsm/core/`) is **frozen since March 2026** — battle-tested, 67 tests, no modifications. Everything above it uses the public API without touching the internals.

For the full architecture: [ARCHITECTURE.md](ARCHITECTURE.md)

## Install

```bash
git clone https://github.com/daryl-labs-ai/daryl
cd daryl
pip install -e .
```

## Run the tests

```bash
pip install -e .[dev]
python -m pytest tests/ -v   # 67 tests, 0 failures
```

## Read agent memory

```python
from dsm.core.storage import Storage
from dsm.rr.relay import DSMReadRelay

storage = Storage(data_dir="memory")
relay = DSMReadRelay(storage=storage)

# Last 10 events
recent = relay.read_recent("sessions", limit=10)

# Session summary with top actions
summary = relay.summary("sessions")
# → {'entry_count': 15, 'unique_sessions': 4, 'top_actions': [('search', 3), ('reply', 2)]}
```

## Verify integrity

```python
from dsm.verify import verify_shard, verify_all

# Verify one shard
result = verify_shard(storage, "sessions")
assert result["status"] == "OK"

# Verify everything
results = verify_all(storage)
```

## Repository structure

```
src/dsm/
  core/         # frozen kernel — storage, models, hash chain, segments
  session/      # SessionGraph lifecycle management
  rr/           # Read Relay — query layer over storage
  ans/          # Analytics — skill performance, workflow insights
  skills/       # Skill registry, router, ingestor

tests/          # 67 tests — core, session, rr, ans, integration
docs/           # Architecture, known issues, roadmap
```

## Known limitations

DSM is an **event log**, not a database.

- **No semantic search** — it stores and verifies, it doesn't understand. Use a vector DB alongside it for retrieval.
- **Single writer per shard** — concurrent writes to the same shard from multiple threads can corrupt metadata ([K-1](docs/KNOWN_ISSUES.md)). Use one writer per shard, or serialize at the application level.
- **Linux/macOS only** — the kernel uses `fcntl` for file locking, which is not available on Windows.

These are architectural choices, not bugs. DSM does one thing — provable, replayable agent memory — and does it correctly.

## Contributing

```bash
git clone https://github.com/daryl-labs-ai/daryl && cd daryl
pip install -e .[dev]
python -m pytest tests/
```

The kernel (`src/dsm/core/`) is frozen. Do not modify it without opening a design discussion.

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT — see [LICENSE](LICENSE).
