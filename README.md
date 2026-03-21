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
<img src="https://img.shields.io/badge/tests-656%20passing-brightgreen">
<img src="https://img.shields.io/badge/kernel-frozen%20%C2%B7%20stable-blueviolet">
</p>

---

AI agents forget everything between sessions.
When they don't, you can't verify what they remember.

**DSM (Daryl Sharding Memory)** gives agents a memory they can prove — an append-only event log where every entry is hash-chained, every session is replayable, and every claim is verifiable with one command. With v0.8.0, DSM extends to **multi-agent collective memory**: multiple agents — across multiple AI models — share a verifiable, auditable, tamper-proof reality, governed by human sovereignty.

## What agents get

- **Total recall** — every action, snapshot, and decision is logged as an immutable entry. Nothing is lost, nothing is overwritten.
- **Tamper-proof history** — each entry carries a SHA-256 hash chained to the previous one. Alter one byte, the chain breaks.
- **One-command verification** — `dsm verify --shard sessions` checks the entire history in milliseconds.
- **Structured sessions** — start, act, observe, end. The agent's lifecycle is a first-class concept, not an afterthought.
- **Multi-agent collective memory** — N agents share a verifiable shard with projections, not copies. Single writer guaranteed. *(v0.8.0)*
- **Multi-AI native** — Claude, GPT, Gemini, open source — same protocol. Identity is a key, not a model. *(v0.8.0)*
- **Human sovereignty** — the owner sets who can contribute, with what trust level, and which entry types are allowed. *(v0.8.0)*
- **Budget-aware context** — `read_with_digests(max_tokens=8000)` loads the best combination of recent entries and temporal digests within a token budget. *(v0.8.0)*

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
| Detect hallucinated memories | ❌ | ❌ | ✅ |
| Semantic search | ❌ | ✅ | ❌ |

DSM doesn't replace a vector database. It complements it — **the vector DB searches, DSM proves.**

## Agents that can't lie about what they did

When an agent says *"I searched the web and found X"*, how do you know it actually did?

With DSM, you don't trust — you verify. Every action the agent claims to have taken is either in the hash-chained log or it isn't. There is no middle ground.

```python
# Agent says it searched for weather — did it?
entries = storage.read("sessions", limit=20)
actions = [e for e in entries if e.metadata.get("action_name") == "search"]
# Either the search entry exists with its exact payload, or the agent is hallucinating.
```

This doesn't prevent an LLM from hallucinating. It makes hallucinations about past behavior **detectable and provable** — the agent's memory is a chain of cryptographic facts, not a probabilistic reconstruction.

### Self-aware agents

An agent with DSM can detect **its own** hallucinations before responding:

```python
# Agent "remembers" searching for weather yesterday.
# Instead of trusting its context window, it checks:

entries = storage.read("sessions", limit=100)
searches = [e for e in entries if e.metadata.get("action_name") == "search"]

if searches:
    # Memory confirmed — respond with confidence
    last_search = searches[0]
else:
    # No search in the log. The "memory" is a hallucination.
    # Agent corrects itself before the user ever sees the mistake.
```

The agent's context window is lossy and probabilistic. DSM is neither. When the two disagree, DSM is right.

## Architecture

```
Your Agent(s)
    ↓
DarylAgent facade     ← SDK: register, push, pull, admit, drain, seal
    ↓
┌─────────────────────────────────────────────────┐
│  A→E Pillars (v0.8.0)                          │
│  A IdentityRegistry   — multi-agent governance  │
│  B SovereigntyPolicy  — human access control    │
│  C NeutralOrchestrator — rule-based admission   │
│  D CollectiveShard     — shared memory + sync   │
│  E ShardLifecycle      — drain/seal/archive     │
└─────────────────────────────────────────────────┘
    ↓
SessionGraph          ← lifecycle: start, snapshot, action, end
    ↓
RR (Read Relay)       ← query: recent entries, summaries, filters
    ↓
DSM Core (frozen)     ← storage: append-only, hash-chained, stable
```

The kernel (`src/dsm/core/`) is **frozen since March 2026** — battle-tested, zero modifications since. Everything above it uses the public API without touching the internals. v0.8.0 adds pillar modules A→E (identity, sovereignty, orchestration, collective, lifecycle) entirely above the freeze line — 7 new source files, 171 new tests, zero kernel changes.

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
python -m pytest tests/ -v   # 656 tests, 0 failures
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
  core/                # frozen kernel — storage, models, hash chain, segments
  session/             # SessionGraph lifecycle management
  identity/            # Identity module — IdentityManager + IdentityRegistry (A)
  rr/                  # Read Relay — query layer over storage
  ans/                 # Analytics — skill performance, workflow insights
  skills/              # Skill registry, router, ingestor
  agent.py             # DarylAgent — SDK facade + A→E integration
  sovereignty.py       # Human sovereignty — pre-execution access control (B)
  orchestrator.py      # Neutral orchestration — rule-based admission (C)
  collective.py        # Collective memory — sync engine, digester (D)
  lifecycle.py         # Shard lifecycle — drain/seal/archive state machine (E)
  shard_families.py    # Shard classification by family (cross-cutting)
  exceptions.py        # A→E shared exceptions
  anchor.py            # Pre-commitment & environment anchoring
  seal.py              # Shard sealing for selective forgetting
  exchange.py          # Cross-agent trust receipts
  signing.py           # Ed25519 entry signing
  artifacts.py         # Content-addressable artifact store
  causal.py            # Cross-agent causal binding
  attestation.py       # Compute attestation — input-output binding
  status.py            # Status enums (including A→E enums)

tests/                 # 656 tests — core, session, rr, ans, A→E, security, integration
docs/architecture/     # DSM_PILLARS_A_TO_E.md — full design + quantitative impact
```

## Multi-agent in 30 seconds (v0.8.0)

```python
from dsm.agent import DarylAgent

agent = DarylAgent(data_dir="memory")

# A — Register agents
agent.register_agent("claude_1", "pk_claude")
agent.register_agent("gpt_1", "pk_gpt")

# B — Set sovereignty policy
agent.set_policy({
    "agents": ["claude_1", "gpt_1"],
    "min_trust_score": 0.3,
    "allowed_types": ["observation", "decision"],
})

# D — Push to collective
agent.start()
agent.push("claude_1", "owner", "sessions", "key")
agent.push("gpt_1", "owner", "sessions", "key")

# D — Read with budget
context = agent.read_context(hours=24, max_tokens=8000)

# E — Lifecycle
agent.drain_shard("old_shard", "owner", "sig")
agent.seal_shard("old_shard", "owner", "sig")
agent.end()
```

Two agents, two AI models, one verifiable collective. For the full design: [DSM_PILLARS_A_TO_E.md](docs/architecture/DSM_PILLARS_A_TO_E.md)

## Known limitations

DSM is an **event log**, not a database.

- **No semantic search** — it stores and verifies, it doesn't understand. Use a vector DB alongside it for retrieval.
- **Single writer per shard** — concurrent writes are serialized per shard via lockfile (fixed in v0.7.0, see [K-1](docs/KNOWN_ISSUES.md)). Multi-process writes to the same shard are safe; multi-shard parallelism is native.
- **Cross-platform** — v0.7.0 uses `filelock` for portable locking (Linux, macOS, Windows).

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
