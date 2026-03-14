# RR Context Builder — Implementation

This document describes the **RR Context Builder**: its role, pipeline, context structure, and example usage.

**Reference:** RR_ARCHITECTURE.md, RR_IMPLEMENTATION_PLAN.md, RR_QUERY_ENGINE_IMPLEMENTATION.md.

---

## 1. Role of the Context Builder

The **RRContextBuilder** turns RR query results into **structured context** that agents or LLMs can consume. It:

- Sits **above** the RR Query Engine and uses only **RRQueryEngine** (no direct access to navigator, index, or Storage).
- Calls `query_engine.query(...)` with `resolve=False` to obtain metadata records.
- Extracts structured information (entry_id, session_id, agent, timestamp, event_type, metadata) and builds a single **context object** (dict).
- Does **not** write to DSM, does **not** call the LLM; it only shapes data for downstream use.

RR remains read-only; the context builder is a pure transformation layer.

---

## 2. Pipeline

1. **Query** — Call `query_engine.query(session_id=..., agent=..., start_time=..., end_time=..., resolve=False, limit=limit, sort="desc")`. No resolution to full Entry; only metadata records are used.
2. **Empty handling** — If the query returns no records, return a fixed structure with empty lists and `context_summary: "No recent events found."`.
3. **Extract** — For each record, read `entry_id`, `session_id`, `agent`, `timestamp`, `event_type`, and optional `metadata`.
4. **Build context** — Build:
   - **recent_events** — List of event summaries (entry_id, agent, timestamp, event_type, short summary text).
   - **agents_involved** — Unique list of agents.
   - **sessions** — Unique list of session_ids.
   - **time_range** — `{ start, end }` from min/max of record timestamps.
   - **context_summary** — Short natural-language summary from `_generate_summary(records)`.

---

## 3. Context structure

**When there are records:**

```python
{
    "recent_events": [
        {
            "entry_id": "...",
            "agent": "...",
            "timestamp": ...,       # raw value from record (e.g. float or ISO string)
            "event_type": "...",
            "summary": "short description"   # e.g. "tool_call by planner"
        },
        ...
    ],
    "agents_involved": ["agent_a", "agent_b"],
    "sessions": ["s1", "s2"],
    "time_range": {
        "start": 1234567890.0,
        "end": 1234567900.0
    },
    "context_summary": "Recent activity includes 12 events involving planner and clawdbot across 2 sessions."
}
```

**When the query returns no records:**

```python
{
    "recent_events": [],
    "agents_involved": [],
    "sessions": [],
    "time_range": {"start": None, "end": None},
    "context_summary": "No recent events found."
}
```

---

## 4. Summary generation

The helper **\_generate_summary(records)** produces a short sentence:

- Count of events, unique agents, and unique sessions.
- Example: *"Recent activity includes 12 events involving planner and clawdbot across 2 sessions."*
- If no records, returns *"No recent events found."* (also used in the empty context above).

This field is the main place where the builder turns structured data into language for an agent or LLM.

---

## 5. Example usage

```python
from memory.dsm.core.storage import Storage
from memory.dsm.rr.index import RRIndexBuilder
from memory.dsm.rr.navigator import RRNavigator
from memory.dsm.rr.query import RRQueryEngine
from memory.dsm.rr.context import RRContextBuilder

storage = Storage(data_dir="/path/to/data")
builder = RRIndexBuilder(storage=storage, index_dir="/path/to/data/index")
builder.ensure_index()
navigator = RRNavigator(index_builder=builder, storage=storage)
query_engine = RRQueryEngine(navigator=navigator)
context_builder = RRContextBuilder(query_engine=query_engine)

context = context_builder.build_context(
    agent="planner",
    limit=10
)

print(context["context_summary"])
for ev in context["recent_events"]:
    print(ev["timestamp"], ev["event_type"], ev["summary"])
```

---

## 6. Location and dependencies

- **Module:** `memory/dsm/rr/context/rr_context_builder.py`
- **Class:** `RRContextBuilder(query_engine: RRQueryEngine)`
- **Dependencies:** Only **RRQueryEngine**. No dependency on DSM core, Storage, index builder, or navigator from this module.

---

## 7. Summary

- **Role:** Transform query results (metadata records) into a single structured context dict for agents/LLMs.
- **Pipeline:** Query (resolve=False) → extract from records → build recent_events, agents_involved, sessions, time_range, context_summary.
- **Empty safety:** Empty query result yields a valid context with empty lists and a fixed summary message.
- **No kernel or storage:** The context builder only calls the query engine; RR stays read-only.
