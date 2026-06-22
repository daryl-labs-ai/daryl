<p align="center">
  <img src="assets/daryl_logo.png" width="220">
</p>

<h1 align="center">Daryl</h1>

<p align="center">
<strong>DSM (Daryl Sharding Memory) — The trust layer for AI agents.</strong>
</p>

<p align="center">
<em>Tamper-evident, hash-chained execution trails for AI agents.</em><br>
<em>Designed for auditability — an experimental proof layer, not a legal guarantee.</em>
</p>

<p align="center">
Created by <strong>Mohamed Azizi</strong> · <a href="https://www.daryl.md">daryl.md</a>
</p>

<p align="center">
<img src="https://github.com/daryl-labs-ai/daryl/actions/workflows/ci.yml/badge.svg">
<img src="https://img.shields.io/badge/python-3.10%2B-blue">
<img src="https://img.shields.io/badge/license-MIT-green">
<img src="https://img.shields.io/badge/coverage-90%25-brightgreen">
<img src="https://img.shields.io/badge/tests-1500%2B%20passing-brightgreen">
<img src="https://img.shields.io/badge/kernel-stable-blueviolet">
<img src="https://img.shields.io/badge/demo-60s%20tamper%20detection-black">
</p>

---

## The Problem

You deployed an AI agent. It made a decision. Something went wrong.

Now prove what happened.

Logs tell you *that* something ran. Observability dashboards tell you *how long* it took. Neither can answer the question that matters: **did the agent actually do what it claims it did, and can you prove it hasn't been altered after the fact?**

- Logs are mutable. Anyone with access can edit or delete them.
- Vector databases reconstruct context probabilistically — they don't preserve decisions.
- Agent frameworks track tool calls, not verifiable proof of execution.

When a regulator, an auditor, or your own CTO asks *"prove this agent did X and not Y"*, none of these tools can answer. DSM is built to provide **tamper-evidence** for that history. It detects post-hoc modification, reordering, and truncation of a recorded trail; strong append-only guarantees against a fully privileged adversary additionally require external anchoring (see [Threat model & limitations](#threat-model--limitations)).

## The Solution

**DSM (Daryl Sharding Memory)** is a trust layer that gives AI agents a cryptographically verifiable execution trail. DSM turns agent execution into cryptographic evidence.

Every action, every decision, every input-output pair is recorded as an immutable, hash-chained entry. Each entry carries a SHA-256 hash linked to the previous one. Alter one byte anywhere in the chain, and verification fails. One command checks the entire history.

DSM does not replace your logs or your vector database. It sits alongside them as the **proof layer** — the part you hand to an auditor.

## How It Works

```
1. Agent acts                      →  action intent is appended to an append-only shard
2. Entry is hashed                 →  SHA-256(content + prev_hash) — chained to all prior entries
3. Entry is signed                 →  Ed25519 signature proves authorship (optional)
4. Chain is sealed                 →  shard can be archived with a cryptographic tombstone
5. Anyone can verify independently →  replay the chain, recompute every hash, confirm integrity
```

**Append-only**: entries are never modified or deleted. New entries extend the chain.
**Hash-chained**: each entry's hash depends on the previous entry. Tampering breaks the chain.
**Attestation**: input-output bindings prove which output was produced for which input.
**Replay**: the full agent history can be deterministically replayed and verified.

## How It Compares

| Capability | Logs | Vector DB | Agent Frameworks | **Daryl (DSM)** |
|---|:---:|:---:|:---:|:---:|
| Prove nothing was altered | - | - | - | **SHA-256 hash chain** |
| Prove agent authorship | - | - | - | **Ed25519 signatures** |
| Prove input→output binding | - | - | - | **Compute attestation** |
| Replay exact execution history | - | - | Partial | **Full deterministic replay** |
| Cross-agent causal proof | - | - | - | **Dispatch + routing hashes** |
| Compliance-ready audit trail | - | - | - | **Seal + archive** |
| Semantic search | - | Yes | - | - |
| Real-time dashboards | Yes | - | Yes | - |

DSM is not a replacement for observability. It is the layer designed to make your agent's history **auditable and tamper-evident**. (Legal admissibility depends on jurisdiction and process and is not something a library can assert on its own.)

## Architecture

Daryl is structured in three layers: execution, trust, and governance.

```
Your Agent(s)
    ↓
SessionGraph              ← lifecycle: start, act, confirm, end
    ↓
┌──────────────────────────────────────────────────────┐
│  Trust Modules                                       │
│  · Ed25519 Signing     — prove authorship            │
│  · Compute Attestation — bind input to output        │
│  · Causal Binding      — prove cross-agent causality │
│  · Trust Receipts      — portable proof of work      │
│  · Shard Sealing       — archive with crypto proof   │
└──────────────────────────────────────────────────────┘
    ↓
┌──────────────────────────────────────────────────────┐
│  Governance (A→E Pillars)                            │
│  A IdentityRegistry    — multi-agent identity        │
│  B SovereigntyPolicy   — human access control        │
│  C NeutralOrchestrator — rule-based admission        │
│  D CollectiveShard     — shared verifiable state     │
│  E ShardLifecycle      — drain / seal / archive      │
└──────────────────────────────────────────────────────┘
    ↓
DSM Core (stable; evolves only via the kernel process)
    ← append-only storage, hash chain, segments
```

## Quick Start

### Install

```bash
pip install daryl-dsm
```

```bash
# From source
git clone https://github.com/daryl-labs-ai/daryl
cd daryl
python3.12 -m venv .venv312
source .venv312/bin/activate
PYTHON=python bash scripts/setup_dev_env.sh
```

`dsm-primitives` is a monorepo peer package used by both `daryl-dsm` and
`agent-mesh`. The root package declares it as a runtime dependency for honest
wheel metadata. Install it first when working from source; project metadata
uses a package dependency instead of a relative path dependency so the root
package remains publishable. A public `daryl-dsm` PyPI release requires
`dsm-primitives` to be resolvable from the package index first.

The setup script installs internal peer packages in the required local order:

```bash
python -m pip install -e packages/dsm-primitives
python -m pip install -e ".[dev]"
python -m pip install -e "agent-mesh[dev]"
python scripts/validate_dev_install.py
```

`agent-mesh` is required for cross-package integration tests such as
`tests/integration/test_hash_parity.py`.

### Record and verify agent actions

```python
from dsm.core.storage import Storage
from dsm.session.session_graph import SessionGraph
from dsm.session.session_limits_manager import SessionLimitsManager

# Initialize
storage = Storage(data_dir="agent_trail")
limits = SessionLimitsManager.agent_defaults("agent_trail")
session = SessionGraph(storage=storage, limits_manager=limits)

# Record agent actions — each one becomes a hash-chained entry
session.start_session(source="my_agent")
session.execute_action("search", {"query": "weather in paris"})
session.execute_action("reply", {"text": "It's sunny in Paris"})
session.end_session()
```

### Verify the entire trail

```python
from dsm.verify import verify_shard

result = verify_shard(storage, "sessions")
assert result["status"] == "OK"
# → total_entries: 4, verified: 4, tampered: 0, chain_breaks: 0
```

```bash
$ dsm verify --shard sessions

shard_id: sessions
total_entries: 4
verified: 4
tampered: 0
chain_breaks: 0
status: OK
```

If anyone — or anything — modifies the trail after the fact, verification fails.

👉 See [`demo/README.md`](demo/README.md) — tamper detection, multi-agent verification, security insight.

## 🧪 Demo

```bash
python demo/demo_verify.py
```

Records a high-value agent decision trail, simulates a post-hoc modification, and shows how Daryl detects it.

![Daryl Verify Demo](demo_verify.gif)

Run it locally:

```bash
git clone https://github.com/daryl-labs-ai/daryl
cd daryl
python demo/demo_verify.py
```

→ See the full multi-agent demo: [`demo/README.md`](demo/README.md)

## Consumption Layer

DSM does not just store memory.
It recalls it, packages it, and proves its origin.

```python
from dsm.recall import search_memory
from dsm.context import build_context
from dsm.provenance import build_provenance

# Recall relevant memory across past sessions
result = search_memory(storage, query="kernel decisions",
                       session_id="current", include_provenance=True)

# Package into token-budgeted context
pack = build_context(storage, query="kernel decisions",
                     max_tokens=4000)

# Verify cryptographic origin
prov = build_provenance(storage, source_shards=["sessions"],
                        verify=True)
# → integrity: OK | trust: verified | broken_chains: 0
```

→ Full walkthrough: [`demo_consumption_layer.py`](demo/demo_consumption_layer.py)

## Agent Memory API V1

Daryl also includes a minimal agent-facing memory layer above the DSM kernel.
It records four reasoning item types only: `fact`, `hypothesis`, `inference`,
and `decision`. `source_refs` are DSM references shaped as
`{"shard": "...", "entry_hash": "..."}`; `depends_on` uses stable DSM entry
hashes; optional `confidence` is a float from `0.0` to `1.0`.

```python
from dsm.memory import (
    explain_decision,
    record_decision,
    record_fact,
    record_hypothesis,
    record_inference,
)

fact = record_fact("DSM entries are hash-chained.", storage=storage)
hypothesis = record_hypothesis("The answer needs a local-trust caveat.", storage=storage)
inference = record_inference(
    "The response should cite DSM verification limits.",
    depends_on=[fact.hash, hypothesis.hash],
    storage=storage,
)
decision = record_decision(
    "Answer with a verifiable DSM-backed justification.",
    depends_on=[inference.hash],
    storage=storage,
)

explanation = explain_decision(decision.hash, storage=storage)
```

This layer is outside `src/dsm/core/`: it writes normal append-only DSM entries
and can be verified with `dsm verify --shard agent_memory`. It is not a vector
database and does not change DSM's hash or storage format. Strong proof against
a fully privileged local rewrite still requires future witness / anchoring work.

### First justified answer demo

```bash
python demo/demo_agent_memory_justified_answer.py
python demo/demo_agent_memory_justified_answer.py --data-dir /tmp/daryl-agent-memory-demo
```

The demo records a deterministic `fact -> hypothesis -> inference -> decision`
chain for a simple operational question, then uses `explain_decision()` to
reconstruct the justification and print DSM entry hashes. It proves that the
answer can be backed by local tamper-evident DSM entries; it does not prove
truthfulness of the original facts or strong resistance to fully privileged
local rewrite without future witness / anchoring.

The demo prints the `Data dir`, `Decision hash`, and a ready-to-run CLI command
for rendering the same decision as a Markdown audit report:

```bash
python -m dsm memory explain <decision_hash> --data-dir /tmp/daryl-agent-memory-demo --shard agent_memory --markdown
```

### Omari lead-capture dogfood demo

```bash
python demo/demo_agent_memory_omari_lead_capture.py --data-dir /tmp/daryl-omari-agent-memory
python -m dsm memory explain <decision_hash> --data-dir /tmp/daryl-omari-agent-memory --shard agent_memory --markdown
```

This demo records a deterministic Omari AI prioritization decision:
fix a lead-capture interruption before adding new sales features. It writes two
facts, one hypothesis, one inference, and one decision to the `agent_memory`
shard, then prints the `Data dir`, `Decision hash`, and a ready-to-run
Markdown explain command.

Known V1 limitation: external evidence such as logs/tickets is not yet
represented as first-class `source_refs` unless imported into DSM first.
The demo therefore references only DSM entries already written by the scenario.
The resulting report is local tamper-evident only; it does not prove factual
truth, reasoning validity, or external anchoring.

### Agent Memory CLI

```bash
dsm memory explain <decision_hash> --data-dir data
dsm memory explain <decision_hash> --json
```

The command reconstructs a recorded decision's Agent Memory chain: decision,
direct inference dependencies, supporting facts and hypotheses, DSM hashes, and
verifiable `source_refs`. To verify the shard hash chain directly, run:

```bash
dsm verify --shard agent_memory --data-dir data
```

This is local tamper-evidence in local trust. It does not yet provide external
witness, MMR/STH, or anchoring proof against a fully privileged local rewrite.

### Agent Memory explain JSON contract

```bash
dsm memory explain <decision_hash> --data-dir data --json
```

The JSON output is versioned as `agent_memory.explain.v1` and is intended for
agents, dashboards, comparison tools, and human audit reports. Minimal shape:

```json
{
  "schema_version": "agent_memory.explain.v1",
  "status": "ok",
  "query": {
    "decision_hash": "v1:...",
    "shard": "agent_memory",
    "depth": 2
  },
  "decision": {
    "kind": "decision",
    "statement": "...",
    "entry_hash": "v1:...",
    "depends_on": ["v1:..."]
  },
  "supporting_chain": {
    "facts": [],
    "hypotheses": [],
    "inferences": []
  },
  "source_refs": [],
  "verification": {
    "local_status": "OK",
    "hint": "dsm verify --shard agent_memory",
    "scope": "local tamper-evident; not external anchoring"
  },
  "warnings": []
}
```

Field semantics:

- `verification.local_status` is a convenience local status reported by
  `memory explain` for the target shard. It does not prove that facts are true,
  does not prove that the agent reasoned correctly, and does not replace an
  explicit `dsm verify` run.
- `verification.hint` is the command or operator hint for local DSM
  verification, for example `dsm verify --shard agent_memory`.
- `verification.scope` states the trust boundary: local tamper-evident status,
  not external anchoring.
- `warnings` is a list of non-blocking resolution anomalies. Current warning
  codes include `missing_dependency`, `depth_limit_reached`, and
  `cycle_detected` when observable by the bounded traversal. Future resolvers
  may also report unresolved `source_refs`.

For `--json` failures, the command returns `status: "error"` with a stable
`error.code` such as `decision_not_found`. The contract reports local
tamper-evidence status and a verification hint; it does not claim external
anchoring or third-party witness evidence.

### Agent Memory Markdown audit report

```bash
dsm memory explain <decision_hash> --data-dir data --markdown
```

The Markdown report is a human audit view rendered from the
`agent_memory.explain.v1` JSON contract. It shows the query, decision,
supporting facts, hypotheses, inferences, source references, warnings,
confidence self-estimates, and local verification fields.
Each report includes a stable header with `Contract: agent_memory.explain.v1`
and `Status: ok` or `Status: error`.

The renderer is a pure JSON-to-Markdown transform: it does not read DSM storage,
does not rebuild the chain, and does not enrich the report from disk. It is
useful for reviews, audit notes, and handoff documents that need a stable,
readable explanation of one recorded decision.

The report is local tamper-evident only. It does not prove factual truth, does
not prove reasoning validity, and does not replace `dsm verify`. Local
tamper-evidence means the local shard can be checked for consistency inside
the local trust boundary. External anchoring would require a separate witness,
MMR/STH, or anchoring mechanism; this report does not provide that.

## Core Guarantees

- **Stable kernel** — the core storage engine (`src/dsm/core/`) is change-controlled: it evolves only through the documented kernel process (see `CONTRIBUTING.md`), and most work happens in the layers above it via the public API. (A prior version of this README claimed the kernel was "frozen since March 2026 with zero modifications"; that was inaccurate and has been corrected — security fixes to the kernel are recorded in `docs/security/`.)
- **Crash-safe writes** — the WAL (write-ahead log) pattern ensures that if a process crashes between `execute_action` and `confirm_action`, the incomplete intent is detectable on replay. No silent data loss.
- **Deterministic verification** — `verify_shard` recomputes every hash from raw data in chronological order and compares the observed tip and entry count against the pinned tip. It detects in-place modification, reordering, and **trailing truncation** (deletion of the most recent entries). A shard with no integrity pin is reported as `UNPINNED` rather than a silent `OK`.

## Threat model & limitations

DSM is honest about what it does and does not prove.

**What DSM detects (single-host integrity):**
- In-place modification of any recorded field (hash mismatch).
- Reordering or insertion of entries (broken `prev_hash` chain).
- Trailing truncation of recent entries (observed tip/count vs the pinned tip).

**What DSM does *not* prove on its own:**
- That the original data was truthful, or that the agent's computation was correct (that needs TEEs).
- Strong append-only against a **fully privileged adversary** who can rewrite both the shard *and* the local integrity pin in the same step. The pin raises the bar (truncation is detected, and `reconcile` refuses to shrink it without an explicit, audited `allow_truncation` flag), but a local-only pin shares the same trust boundary as the data. Defeating this requires **external anchoring** — signed checkpoints, independent witnesses, or on-chain anchoring — which is on the roadmap (see `docs/security/P0_REMEDIATION.md`).
- Non-equivocation (an operator showing different histories to different verifiers) — also addressed by external witnessing.

In short: DSM today is a strong **tamper-evidence** layer for honest-but-curious and partially-malicious settings, and an explicit work-in-progress toward cryptographically anchored, third-party-verifiable proofs.

## Advanced Capabilities

### Cross-Agent Trust Receipts

*Module: `dsm.exchange`*

When Agent B completes work for Agent A, it issues a **TaskReceipt** — a portable proof-of-work token. The receipt includes the entry hash, shard tip hash, and entry count at the time of issuance. A third party can check the receipt against Agent B's shard to confirm the entry exists and the hashes match. (Note: this binds the receipt to a shard *state*; it does not by itself prevent a later truncation of that shard — see [Threat model & limitations](#threat-model--limitations). Anchored, fully third-party-verifiable receipts are on the roadmap.)

```python
from dsm.exchange import issue_receipt, verify_receipt, verify_receipt_against_storage

receipt = issue_receipt(storage, agent_id="agent_b", entry_id="...",
                        shard_id="sessions", task_description="Translated document")

result = verify_receipt(receipt)
# → {"status": "INTACT", "issuer": "agent_b", ...}

result = verify_receipt_against_storage(storage, receipt)
# → {"status": "CONFIRMED", "entry_found": True, "hash_matches": True}
```

### Ed25519 Entry Signing

*Module: `dsm.signing`*

Every entry or receipt can be signed with an Ed25519 keypair. This proves authorship: only the agent holding the private key could have produced a valid signature. Supports key rotation, key revocation, and hash-chained key history.

```python
from dsm.signing import AgentSigning

signer = AgentSigning(keys_dir="keys", agent_id="agent_a")
signer.generate_keypair()

signature = signer.sign_entry(entry_hash="abc123...")

result = signer.verify_signature(data_hash="abc123...",
                                  signature=signature,
                                  public_key=signer.get_public_key())
# → {"valid": True, ...}
```

### Cross-Agent Causal Binding

*Module: `dsm.causal`*

Proves that Agent B's work was in response to Agent A's specific dispatch — not a coincidence, not a replay. The dispatch hash binds A's entry, task parameters, and timestamp into a single verifiable token.

```python
from dsm.causal import create_dispatch_hash, DispatchRecord, verify_dispatch_hash

dispatch_hash = create_dispatch_hash(
    dispatcher_entry_hash="abc123...",
    task_params={"action": "translate", "lang": "fr"},
)

record = DispatchRecord(
    dispatch_hash=dispatch_hash,
    dispatcher_agent_id="agent_a",
    dispatcher_entry_hash="abc123...",
    target_agent_id="agent_b",
    task_params={"action": "translate", "lang": "fr"},
    timestamp="2026-04-12T10:00:00Z",
)

result = verify_dispatch_hash(record)
# → {"status": "VALID", ...}
```

### Compute Attestation

*Module: `dsm.attestation`*

Binds a specific input to a specific output for a given model. The attestation hash proves that *this agent* claims *this output* was produced from *this input* using *this model*. Does not prove the computation was correct (that requires TEEs) — but it makes the claim verifiable and signed.

```python
from dsm.attestation import create_attestation, verify_attestation, sign_attestation

attestation = create_attestation(
    agent_id="agent_a",
    raw_input="What is the capital of France?",
    raw_output="Paris",
    model_id="claude-sonnet-4-20250514",
)

result = verify_attestation(attestation)
# → {"status": "VALID", ...}

signed = sign_attestation(attestation, signer)
```

### Shard Sealing

*Module: `dsm.seal`*

When a shard is complete — a session is over, a compliance window has closed — it can be **sealed**. Sealing computes a cryptographic tombstone over the entire shard, optionally archives the data, and records the seal in a registry. The shard data can then be deleted; the seal proves the history existed and what it contained.

```python
from dsm.seal import seal_shard, SealRegistry, verify_seal

registry = SealRegistry(seal_dir="seals")

record = seal_shard(storage, "old_sessions", registry, archive_path="archive/")

result = verify_seal(registry, "old_sessions")
# → {"status": "VALID", "entry_count": 42, "sealed_at": "2026-04-12T..."}
```

## Why It Matters

**EU AI Act (2026)**: High-risk AI systems must maintain logs that allow traceability of decisions. DSM provides a hash-chained, tamper-evident audit trail **designed to support** this kind of traceability requirement. It is a building block, not a certification: it does not by itself make a system compliant, and it is not a substitute for a legal compliance review.

**Accountability**: When an agent makes a consequential decision — approving a loan, triaging a patient, executing a trade — the organization must be able to reconstruct what happened. DSM is designed to make that reconstruction verifiable rather than merely plausible, within the limits described below.

**Internal governance**: For teams running multi-agent systems, DSM provides the infrastructure to answer "which agent did what, when, and was it authorized?" — with cryptographic proof, not log grep.

## Open vs Private

**This repository (open source, MIT)**:
- DSM core engine — append-only storage, hash chain, verification
- Session lifecycle — start, act, confirm, end
- All trust modules — signing, attestation, causal binding, receipts, sealing
- Multi-agent governance — identity, sovereignty, orchestration, collective, lifecycle
- Parallel shard lanes, cold storage, Read Relay query layer
- CLI tools, Goose MCP integration
- 1500+ tests (DSM core + agent-mesh)

**Private extensions (not in this repo)**:
- Hosted verification API
- Dashboard and compliance reporting UI
- Enterprise SSO and team management
- Managed archival and retention policies

## Vision

Daryl aims to become the standard for verifiable agent execution — the equivalent of digital signatures, but for AI decisions.

## Get in Touch

- Web: [daryl.md](https://www.daryl.md)
- GitHub: [github.com/daryl-labs-ai/daryl](https://github.com/daryl-labs-ai/daryl)

## Run the Tests

```bash
git clone https://github.com/daryl-labs-ai/daryl
cd daryl
python3.12 -m venv .venv312
source .venv312/bin/activate
PYTHON=python bash scripts/setup_dev_env.sh
python -m pytest -q
```

## Contributing

```bash
git clone https://github.com/daryl-labs-ai/daryl && cd daryl
python3.12 -m venv .venv312
source .venv312/bin/activate
PYTHON=python bash scripts/setup_dev_env.sh
python -m pytest -q
```

The kernel (`src/dsm/core/`) is frozen. Do not modify it without opening a design discussion. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT — see [LICENSE](LICENSE).

## Disclaimer

DSM provides cryptographic integrity verification for agent execution trails. It proves that recorded data has not been tampered with after the fact. It does **not** prove that the original data was truthful, that the computation was correct, or that the agent behaved as intended. Hash chain integrity is a necessary condition for trustworthy audit trails, not a sufficient one. For claims about computation correctness, additional infrastructure (e.g., trusted execution environments) is required.
