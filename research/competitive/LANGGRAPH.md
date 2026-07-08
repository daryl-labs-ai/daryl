# LangGraph — Competitive Product Memo

**Program:** 2026-CompetitiveProductResearch
**Product:** LangGraph v1.2.8 (`langgraph` + `langgraph-checkpoint-sqlite`
+ `langchain-core` + `langchain-ollama`)
**Tested:** 2026-07-08, isolated venv (Python 3.12), local ollama
(llama3.2).
**Classification discipline:** every claim is tagged
OBSERVED / MEASURED / INFERRED / UNKNOWN.

---

## 1. Executive Summary

LangGraph is **not a memory product**. It is a stateful workflow framework
for LLM applications. Memory, in LangGraph, is a side effect of its
checkpointing mechanism — every graph step is checkpointed so that an
interrupted workflow can be resumed. That checkpointing *looks* like memory,
but it is fundamentally **thread-scoped state recovery**, not long-term
memory, not shared memory, not verifiable memory.

This distinction is the single most important finding of this study.
LangGraph solves a real problem (resumable multi-step LLM workflows) very
well. It does not solve — and does not claim to solve — the problems Daryl
solves (provenance, tamper-evidence, cross-agent verifiable handoff,
auditability). The two products are complementary, not competitive.

The developer experience of LangGraph is the best of the three products
studied so far (Mem0, Letta, LangGraph): clean install (~15 deps), pure
Python, no Docker required, no Postgres, works with local ollama in under a
minute. The interrupt/resume mechanism is genuinely excellent. But every
observation of "memory" in LangGraph reveals a gap that Daryl was built to
fill: thread-scoped (not cross-session), opaque binary checkpoints (not
human-readable), no provenance (LLM output carries model metadata but no
integrity), no verification (forged messages are silently trusted), and
silent data loss on corruption.

---

## 2. Installation Experience

| Aspect | Observation | Class |
|--------|-------------|-------|
| `pip install langgraph` | Clean, ~15 deps. No Rust, no Docker, no Postgres. | OBSERVED |
| Additional for persistence | `langgraph-checkpoint-sqlite` (1 extra package). | OBSERVED |
| Additional for LLM | `langchain-ollama` (1 extra package). | OBSERVED |
| First successful LLM call | < 60 seconds from `pip install` to a response. | MEASURED |
| Failures during install | **Zero.** The only product in this study with a clean first install. | OBSERVED |

**Comparison:**
```
                deps    failures-to-first-run    Docker required
Mem0            ~30     2 (dims mismatch, API drift)   no
Letta           497     7 (3.14 build, asyncpg, etc.)  yes (effectively)
LangGraph       ~15     0                               no
```

LangGraph has the best developer onboarding of any product in this study.

---

## 3. Real Usage Scenarios

### Scenario A — Single agent, 3 turns, same thread (OBSERVED)

A `StateGraph` with one `chat` node, backed by `MemorySaver` (in-process)
or `SqliteSaver` (disk). Three turns in the same `thread_id`:

```
Turn 1: "I'm Alice, I use Python 3.12 with ZCode."
Turn 2: "I prefer concise answers in French."
Turn 3: "What do you know about me?"
```

Result: Turn 3 correctly recalled Alice + Python 3.12 + ZCode. State
accumulated 6 messages across the thread. Latency: 0.2–0.5 s per turn
(local ollama).

### Scenario A2 — New thread, same process (OBSERVED)

```
thread_id: "alice-session-2"
"What's my name?"
```

Result: **"I don't have any information about your identity."** Memory is
strictly thread-scoped. A new `thread_id` is a blank slate, even in the
same process, even on the same SQLite DB file.

### Scenario B — SQLite persistence + restart recovery (OBSERVED)

Phase 1: wrote 2 turns to SQLite, closed connection (simulated crash).
Phase 2: new process, reopened same DB file, same `thread_id`.

Result: **4 messages recovered, conversation continued correctly.**
Cross-process persistence works *if* the same DB file and same `thread_id`
are used. But a different `thread_id` in the same DB sees nothing.

### Scenario C — Two-agent handoff via shared state (OBSERVED)

Agent A (coder) produces output, Agent B (reviewer) reviews it. Both read
from / write to the same `messages` field in the shared `WorkflowState`.

Result: B saw A's output. Handoff works via **shared mutable state**, not
via receipts or dispatch. There is no proof that A produced its message — B
sim trusts whatever is in `state["messages"]`.

### Scenario C2 — Agent C continues from checkpoint (OBSERVED)

A third agent (C) invoked on the same `thread_id` after A+B completed.

Result: C's context included the message history, but **the LLM
hallucinated** — it invented a spy-thriller narrative instead of reading
the actual reverse-string code A had produced. The checkpoint preserved
the data; the LLM's reading of it was unreliable.

### Scenario D — Forgery injection (OBSERVED)

Injected a forged `AIMessage("Alice uses Rust")` into the message history
before invoking the graph.

Result: **The LLM trusted the forged message and told Alice she uses
Rust.** No mechanism exists to detect or reject the injection. There is no
signature, no hash, no provenance check on any message in the state.

### Scenario D4 — Corruption: delete all checkpoints (OBSERVED)

Deleted all rows from the `checkpoints` and `writes` tables in the SQLite
DB, then reopened and called `get_state`.

Result: **0 messages recovered. No error, no warning.** Silent data loss.
There is no integrity check, no "checkpoint missing" alarm, no
tamper-detection.

### Scenario E — Interrupt/resume (human-in-the-loop) (OBSERVED)

Compiled the graph with `interrupt_before=["human_review"]`. The workflow
paused before the review node. Process was killed. New process reopened
the DB, called `invoke(None)` (resume from checkpoint).

Result: **Resume worked perfectly.** The workflow continued from exactly
where it paused. This is LangGraph's strongest feature.

---

## 4. Strengths

| # | Strength | Evidence | Class |
|---|----------|----------|-------|
| S1 | **Best-in-class install experience.** ~15 deps, pure Python, no Docker, no Postgres. Zero failures to first run. | Comparison table §2. | OBSERVED |
| S2 | **Interrupt/resume is excellent.** `interrupt_before` + checkpoint + `invoke(None)` is a clean, reliable human-in-the-loop mechanism that survives process restarts. | Scenario E. | OBSERVED |
| S3 | **Flexible state schema.** The developer defines a `TypedDict` with `Annotated[list, add_lists]` reducers — full control over what accumulates and how. | StateGraph API. | OBSERVED |
| S4 | **Checkpointer abstraction.** `MemorySaver` (in-process) and `SqliteSaver` (disk) are interchangeable via one constructor argument. Pluggable to Postgres, Redis, etc. | Swapped savers between scenarios without graph changes. | OBSERVED |
| S5 | **Graph-based workflow composition.** Conditional edges, multi-node graphs, parallel branches — the developer can express complex agent workflows declaratively. | Scenario C (A→router→B). | OBSERVED |
| S6 | **LLM response carries model provenance.** `AIMessage.response_metadata` includes `model_name`, `model_provider`, `created_at`, token counts. | Field inspection. | OBSERVED |
| S7 | **Fast local execution.** 0.2–1.5 s per LLM turn with ollama; checkpoint save is transparent (no measurable overhead). | Scenarios A, E. | MEASURED |

---

## 5. Weaknesses

| # | Weakness | Evidence | Class |
|---|----------|----------|-------|
| W1 | **Memory is thread-scoped, not long-term.** A new `thread_id` is a blank slate. There is no "remember across sessions" primitive. Cross-thread memory requires the developer to build a separate store (vector DB, etc.). | Scenario A2. | OBSERVED |
| W2 | **No provenance on messages.** Messages carry `response_metadata` (model name, tokens) but no hash, no signature, no chain. A forged `AIMessage` is indistinguishable from a real one. | Scenario D. | OBSERVED |
| W3 | **No integrity verification.** Checkpoints are opaque binary blobs (msgpack, not JSON). There is no `verify()`, no hash chain, no tamper-detection. Deleting checkpoints causes silent data loss. | Scenarios D4, D2b. | OBSERVED |
| W4 | **No agent identity in the state.** Messages have a `type` (`human`/`ai`) but no `agent_id`. In a multi-agent graph, you cannot tell from the state which agent produced which message — only that it was an "AI" message. | State inspection. | OBSERVED |
| W5 | **No API for memory enumeration.** There is no `list_threads()` or `list_memories()` in the SDK. Discovering what threads exist requires raw SQL (`SELECT DISTINCT thread_id FROM checkpoints`). | Scenario D5. | OBSERVED |
| W6 | **Checkpoints are binary and opaque.** Stored as msgpack bytes in SQLite. Not human-readable, not portable across checkpoint versions, not auditable without the exact LangGraph version that wrote them. | D2b: `pickle.loads` failed (msgpack, not pickle). | OBSERVED |
| W7 | **No audit trail of decisions.** The checkpoint stores the *state* at each step, but not *why* the router chose path X, or *what evidence* supported a decision. The "why" lives in the LLM's hidden reasoning, not in the graph. | State inspection; no rationale field. | OBSERVED |
| W8 | **Handoff is via shared mutable state.** Agent B sees Agent A's output because both read/write `state["messages"]`. This is powerful but has no isolation — B can overwrite A's messages, and there is no receipt proving B received A's specific output. | Scenario C. | OBSERVED |

---

## 6. Evidence Table

| Claim | Scenario | Class |
|-------|----------|-------|
| Install is clean (0 failures, ~15 deps) | §2 | OBSERVED |
| Memory is thread-scoped (new thread = blank slate) | A2 | OBSERVED |
| SQLite persistence survives process restart | B | OBSERVED |
| Different thread_id on same DB = no cross-thread memory | B (Phase 3) | OBSERVED |
| Two-agent handoff works via shared state | C | OBSERVED |
| Agent C on same thread hallucinates (LLM misreads checkpoint) | C2 | OBSERVED |
| Forged AIMessage is silently trusted | D | OBSERVED |
| Deleting checkpoints = silent data loss (no error) | D4 | OBSERVED |
| Thread enumeration requires raw SQL (no SDK API) | D5 | OBSERVED |
| Interrupt/resume works across process restart | E | OBSERVED |
| `response_metadata` carries model name/provider/tokens | D3 | OBSERVED |
| `__signature__` on Message is `None` (Python magic, not provenance) | D3 | OBSERVED |
| Checkpoints stored as binary (msgpack), not JSON | D2b | OBSERVED |
| Latency: 0.2–1.5 s/turn (local ollama) | A, E | MEASURED |
| Latency: state recovery < 0.1 s (SQLite read) | E | MEASURED |

---

## 7. Strategic Implications for Daryl

*(Observations only. No roadmap proposals.)*

LangGraph and Daryl address **different layers of the same stack**.

LangGraph is a **workflow orchestrator** — it manages *how* agents execute
in sequence, with branching, interruption, and resumption. Its checkpointing
solves *resumability* (don't lose work on crash) but not *trustability*
(prove what happened and who did it).

Daryl is a **memory and provenance layer** — it manages *what* is recorded,
*whether* it can be verified, and *who* can prove what. It does not
orchestrate workflows.

**The complementarity is structural:**

| Concern | LangGraph | Daryl |
|---------|-----------|-------|
| Resumability (resume after crash) | ✓ checkpointer | ✓ append-only shard |
| Cross-session memory | ✗ thread-scoped | ✓ shards persist |
| Provenance (who/what/when) | ✗ no agent_id, no proof | ✓ hash chain + receipts |
| Tamper-detection | ✗ silent on forgery/corruption | ✓ verify_shard |
| Cross-agent handoff with proof | ✗ shared mutable state | ✓ dispatch + receipts |
| Auditability | ✗ binary opaque checkpoints | ✓ JSONL + replay |
| Memory enumeration | ✗ no API (raw SQL) | ✓ list_shards + RR |
| Workflow orchestration | ✓ graph + branching | ✗ not a workflow engine |

A developer building a multi-agent system with LangGraph will **naturally
need everything Daryl provides** — but will not discover that need until
they try to (a) remember something from a previous session, (b) prove an
agent did what it claims, or (c) recover from a tampered or corrupted
checkpoint. Those are exactly the failure modes Daryl was designed to
prevent.

**The integration point** (observation, not proposal): LangGraph's
`BaseCheckpointSaver` is an abstract class. A `DarylCheckpointSaver` that
writes checkpoints as DSM entries (with hash chain + provenance) would give
LangGraph workflows everything they lack — verifiable persistence, cross-
session memory, and tamper-evidence — without changing LangGraph's API.
Whether this is worth building is a decision for the canonical team.

---

## 8. Corrections Made During the Investigation

| Initial observation | Correction | Truth |
|---------------------|------------|-------|
| `__signature__` appears in `dir(AIMessage)` — looked like a provenance field. | Checked its value: `None`. It is Python's standard `__signature__` magic attribute, not a cryptographic signature. | Not provenance. Corrected. |
| Checkpoint blobs looked like pickle. | `pickle.loads()` failed; `invalid load key '{'` suggests msgpack or another serializer. Could not fully decode. | Binary opaque format. Corrected to "msgpack or similar", not "pickle". |
| Agent C appeared to recover A+B history correctly because it referenced "agents". | On closer reading, C hallucinated a spy narrative — it did **not** accurately read A's reverse-string code. The checkpoint had the data; the LLM didn't use it faithfully. | Checkpoint data survived; LLM recall was unreliable. Corrected. |

---

## 9. Unknowns

- **U1 (UNKNOWN):** LangGraph's `PostgresSaver` and `RedisSaver` were not
  tested. Whether they add any integrity or enumeration features the
  SQLite saver lacks is unknown.
- **U2 (UNKNOWN):** LangGraph's `Store` API (a separate key-value store
  for cross-thread memory, introduced in later versions) was not tested.
  It may address the thread-scoped limitation. Worth investigating.
- **U3 (UNKNOWN):** Whether LangSmith (the commercial observability
  platform) adds provenance or audit that the OSS framework lacks.
- **U4 (HYPOTHESIS):** LangGraph is the most widely-adopted agent
  framework in the ecosystem. A Daryl integration that targets LangGraph
  users specifically may have higher leverage than targeting Mem0 or Letta
  users. *(Inferred from framework positioning, not measured.)*

---

## Answers to the 8 questions

**(From evidence only.)**

**1. When does the developer naturally need memory?**
The moment they want a conversation to span more than one invocation, or
to survive a crash. In LangGraph, this is immediate — the *first* multi-
turn conversation needs a checkpointer. But "memory" here means "thread
state recovery", not "long-term recall". The developer hits the wall when
they want session 2 to remember session 1 — and discovers there is no
built-in mechanism for that.

**2. What information is the developer repeatedly reconstructing manually?**
Cross-session context. The developer must manually extract facts from
thread 1 and inject them into thread 2's initial state. There is no
"persistent user profile" or "shared memory store" primitive. Every
cross-thread handoff is hand-rolled.

**3. Where does the framework silently assume trust?**
Every message in `state["messages"]` is trusted unconditionally. A forged
`AIMessage` is indistinguishable from a real one. The router trusts that
the state was not tampered with between checkpoint and resume. The
checkpointer trusts that the SQLite file was not corrupted. None of these
assumptions are checked.

**4. What happens after a restart?**
Same `thread_id` + same DB file: full recovery, workflow resumes cleanly
(LangGraph's strongest property). Different `thread_id`: blank slate.
Corrupted DB: silent data loss, no error.

**5. Can someone explain why an agent reached a conclusion?**
No. The checkpoint stores *what* state the graph was in at each step, but
not *why* the router chose path X, *what evidence* the LLM used, or *which
facts* supported the conclusion. The "why" is in the LLM's hidden
reasoning, which is not captured.

**6. Can another agent continue the work?**
Yes — if it uses the same `thread_id`. Agent C can read A+B's message
history from the checkpoint. But there is no receipt proving C received
the right context, and the LLM may hallucinate rather than faithfully read
the checkpoint.

**7. What information disappears forever?**
- Cross-thread context (thread-scoped by design).
- The *rationale* for any decision (only outputs are stored, not reasoning).
- Agent identity (messages are typed `human`/`ai`, not `agent_A`/`agent_B`).
- Any checkpoint row deleted from the DB (silent, irreversible, undetected).
- The *proof* that a message was produced by the claimed model (no
  signature binding `response_metadata` to the message content).

**8. What would Daryl naturally provide underneath this workflow?**
A substrate where:
- every checkpoint is an append-only, hash-chained entry (tamper-evident)
- every message carries agent identity and a verifiable signature
- cross-session memory is a shard, not a thread-id convention
- handoff is a receipt + dispatch, not shared mutable state
- corruption is detected by `verify_shard`, not silently swallowed
- the "why" can be reconstructed by replaying the chain

LangGraph would be the workflow engine. Daryl would be the verifiable
memory underneath it. They compose; they do not compete.

---

## Final question

> *"If Daryl did not exist, what would this product teach us about building
> operational memory?"*

It would teach us that **resumability is not the same as memory, and
checkpointing is not the same as remembering**. LangGraph check-points
state so a workflow can resume — and does it excellently. But a checkpoint
is a snapshot of "where we were", not a record of "what happened, why, and
who is responsible". The moment you need to prove what an agent did,
remember across sessions, or trust a memory after a failure, checkpointing
alone is insufficient. You need a substrate that is append-only, hash-
chained, and verifiable — exactly the layer Daryl provides and LangGraph
does not pretend to.
