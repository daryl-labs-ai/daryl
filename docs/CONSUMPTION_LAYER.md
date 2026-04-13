# DSM Consumption Layer

Technical reference for `dsm.recall`, `dsm.context`, and `dsm.provenance` — the three modules that let agents read, package, and verify their own history.

Introduced in Daryl v1.1.0. 77 tests, 0 regressions against the existing 1153.

---

## Problem

DSM v1.0 solved the write side: every agent decision is recorded as an append-only, hash-chained entry. Verification proves the trail has not been tampered with.

But recording is only half the problem. An agent that cannot read its own history is an agent with amnesia. It will repeat decisions, contradict prior commitments, and lose institutional knowledge across sessions.

The missing piece was a read path that satisfies three constraints simultaneously:

1. **Relevance** — not all history matters for the current task. The agent needs the subset that is relevant, ranked by importance.
2. **Budget** — LLM context windows are finite. Recalled memory must fit within a token budget without truncating critical information.
3. **Provenance** — recalled memory must be traceable to its source entries and verifiable against the original hash chain. Unverified recall is no better than hallucination.

No existing system provides all three. Vector databases handle relevance but not provenance. RAG pipelines handle budget but not integrity. DSM now handles all three through the Consumption Layer.

---

## Solution

The Consumption Layer is a read-only pipeline with three phases:

```
Phase 1: dsm.recall       →  find relevant entries across past sessions
Phase 2: dsm.context      →  compact and budget them for an LLM prompt
Phase 3: dsm.provenance   →  verify cryptographic origin of recalled entries
```

Each phase consumes the output of the previous one. Each can be used independently. None of them write to storage.

---

## Architecture

### Phase 1 — `dsm.recall.search_memory()`

Scans entries across all shards. Scores them against a query using deterministic keyword overlap (no ML, no embeddings). Applies temporal classification:

- **still_relevant** — recent and not contradicted
- **superseded** — a newer entry covers the same topic with strictly newer information
- **outdated** — older than 30 days with no newer corroboration

Scoring combines three signals:
- Token overlap between query and entry content (normalized by entry length)
- Recency boost (exponential decay, half-life 60 days)
- Type weight (verified_fact > historical_decision > working_assumption > outdated_possibility)

The current session is excluded from past recall by default. This is deliberate: recall is for cross-session memory, not intra-session context.

```python
from dsm.recall import search_memory

result = search_memory(
    query="architecture decisions about the API",
    storage=storage,
    session_id="current_session_id",
    across_sessions=True,
    max_results=10,
    include_provenance=True,
)

# result["past_session_recall"] — ranked matches from past sessions
# result["verified_claims"]     — extracted verified facts
# result["provenance"]          — integrity metadata for recalled entries
```

### Phase 2 — `dsm.context.build_context()`

Takes the output of `search_memory()` and produces a `ContextPack` — a structured object with sections bucketed by reliability and recency, all within a token budget.

Sections (in priority order):
1. `verified_facts` — action results confirmed as successful
2. `working_state` — current session entries (if included)
3. `recent_relevant_events` — past entries younger than 24 hours
4. `past_session_recall` — older relevant entries
5. `uncertain_or_superseded` — entries flagged by temporal analysis

When the token budget is exceeded, sections are trimmed from lowest priority first. Verified facts are trimmed last.

```python
from dsm.context import build_context, build_prompt_context

# Structured output
pack = build_context(
    query="architecture decisions",
    storage=storage,
    max_tokens=4000,
)
# pack.system_facts, pack.digest, pack.token_estimate, pack.trimmed

# Prompt-ready string
prompt = build_prompt_context(
    query="architecture decisions",
    storage=storage,
    max_tokens=2000,
    audience="agent",  # or "human", "debug"
)
```

### Phase 3 — `dsm.provenance.build_provenance()`

Produces a `ProvenancePack` — a typed dataclass that traces recalled entries back to their source shards and optionally verifies chain integrity.

Two modes:

- `verify=False` (lightweight): integrity and trust derived from metadata only. No hash recomputation.
- `verify=True` (full): runs `verify_shard()` on each source shard. Reports broken chains and computes trust level.

Trust level semantics:
- `verified` — all source shards pass chain verification
- `partial` — some shards pass, some fail
- `unverified` — no shards pass, or verification was not run

```python
from dsm.provenance import build_provenance

prov = build_provenance(
    items=result["past_session_recall"],
    storage=storage,
    verify=True,
)
# prov.integrity      — "OK" | "not_verified" | "broken"
# prov.trust_level    — "verified" | "partial" | "unverified"
# prov.broken_chains  — number of chain breaks found
# prov.source_shards  — list of shards that contributed entries
```

---

## Example Flow

The `demo_consumption_layer.py` script at the repo root demonstrates the full pipeline:

1. **Setup** — creates three sessions spanning 45 days. Session 1 records "use REST for the API." Session 2 records "use gRPC for the API" (superseding Session 1). Session 3 is the current active session.

2. **Recall** — `search_memory()` finds entries matching "architecture decision API gateway protocol." The older REST decision is marked `superseded`. The newer gRPC decision ranks higher.

3. **Context** — `build_context()` packages the results into a token-budgeted context pack. `build_prompt_context()` renders it as a string ready for injection into an LLM system prompt.

4. **Provenance** — `build_provenance(verify=True)` verifies the hash chain of the `sessions` shard. Reports `integrity=OK`, `trust=verified`, `broken_chains=0`.

```bash
python demo_consumption_layer.py
```

---

## How It Composes with the Trust Layer

The Consumption Layer sits on top of the Trust Layer. It reads from the same append-only shards that `SessionGraph` writes to and that `verify_shard()` audits.

```
Agent writes (Trust Layer)          Agent reads (Consumption Layer)
─────────────────────────           ──────────────────────────────
SessionGraph.execute_action()       search_memory()
  → append-only entry                 → scan + score + rank
  → SHA-256 hash chain                → temporal status
  → Ed25519 signature (optional)      → verified claims extraction

verify_shard()                      build_context()
  → binary integrity check            → bucket + trim + compact
                                      → token-budgeted output

                                    build_provenance()
                                      → trace to source shards
                                      → verify chain integrity
                                      → compute trust level
```

The Consumption Layer never writes to storage. It never modifies entries. It is strictly read-only. This is by design: the trust layer guarantees are only meaningful if the read path cannot alter what the write path recorded.

---

## Guarantees

- **Read-only** — the Consumption Layer never writes to any shard. `search_memory`, `build_context`, and `build_provenance` are pure readers.
- **Deterministic scoring** — keyword overlap + recency decay + type weighting. No stochastic components. Same inputs produce same rankings.
- **Temporal correctness** — superseded detection uses strict token-subset comparison. An entry is only marked superseded if a strictly newer entry covers all of its matched query tokens.
- **Budget honoring** — `build_context()` trims from lowest-priority sections first. The output never exceeds `max_tokens * 0.95`.
- **Provenance traceability** — every recalled entry carries its `entry_hash` and `source_shard_id`. `build_provenance(verify=True)` re-verifies the chain.

---

## Limitations

These are real constraints of the V0 implementation. They are not bugs; they define the current scope.

- **Keyword scoring only** — V0 uses token overlap, not semantic similarity. It will miss synonyms and paraphrases. "use gRPC" will not match a query about "protocol buffers" unless those words appear in the entry. Embedding-based scoring is planned for a future phase.

- **No cross-shard temporal reasoning** — superseded detection operates within the set of recalled entries. If two entries in different shards contradict each other but only one is recalled, the contradiction will not be detected.

- **Approximate token estimation** — token counts use `len(text) // 4` as a heuristic. This is close for English text but may diverge for other languages, code, or structured data. The 5% headroom buffer compensates for most cases.

- **No incremental recall** — `search_memory()` scans all entries in the target shards on every call. There is no index, no cache, no cursor. For shards with more than 100K entries, this may become slow.

- **Provenance is per-shard, not per-entry** — `build_provenance(verify=True)` verifies entire shard chains. It cannot report integrity for individual entries without verifying the full chain up to that point.

---

## What's Next

**Phase 2 — Embedding-based recall**: replace keyword overlap with embedding similarity for semantic matching. The scoring pipeline is designed to be pluggable; the `build_match()` function can be swapped without changing the rest of the pipeline.

**Phase 3 — Incremental indexing**: maintain a lightweight inverted index over shard entries, updated on each append. Eliminates full-shard scans during recall.

**Cross-agent recall**: extend `search_memory()` to read from multiple agents' shards via the A-E governance layer (IdentityRegistry, CollectiveShard). An agent could recall decisions made by other agents in its collective, with provenance proving which agent made which decision.

**Context streaming**: for very large context budgets, stream sections to the LLM incrementally rather than building the full pack in memory.
