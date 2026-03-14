# DSM-RR (Read Relay)

## Vision

DSM-RR is a **read relay layer** for DSM that allows agents to navigate memory without touching the frozen kernel. It sits above the append-only DSM kernel and provides query, reconstruction, and summarization over stored events.

## Responsibilities

- **Query shards** — Run topic, tag, or semantic-style queries over shard contents.
- **Reconstruct sessions** — Rebuild full session flows from scattered entries.
- **Build timelines** — Produce ordered timelines per agent, project, or topic.
- **Summarize memory** — Generate high-level summaries (e.g. by project, time range).
- **Detect anomalies** — Flag inconsistencies, gaps, or unexpected patterns in the event stream.

## Architecture

```
Agents
  ↓
DSM-RR
  ↓
DSM Kernel (frozen)
```

Agents and planners call DSM-RR; DSM-RR reads from the DSM kernel via its public read API. No writes go through DSM-RR to the kernel; the kernel remains append-only and deterministic.

## Example usage

```python
# Query by topic
rr.query("topic:trading")

# Timeline for an agent
rr.timeline("agent_01")

# Summary for a project
rr.summary("project:daryl")
```

## Status

**Planned**
