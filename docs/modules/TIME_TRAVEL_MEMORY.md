# Time Travel Memory

## Vision

Temporal navigation inside DSM memory: the ability to move along the event stream in time, take snapshots, and replay history. DSM behaves like a **git-like cognitive memory system** where past states can be inspected and replayed without altering the log.

## Responsibilities

- **memory.timeline** — Navigate events along a timeline (by session, agent, project).
- **memory.snapshot** — Capture a point-in-time view of state or context.
- **memory.replay** — Replay a segment of cognitive history (decisions, actions, outcomes).

## Use cases

- **Analyze past decisions** — Inspect why a given action was chosen at a given time.
- **Replay cognitive history** — Step through events in order for debugging or auditing.
- **Simulate alternate choices** — Compare “what happened” vs. “what if” without mutating the store.

All of this is **read-only** over the append-only DSM kernel; no kernel logic is changed.

## Architecture

- Built on top of DSM (and optionally DSM-RR) read APIs.
- Timeline and snapshot are views over the same event stream.
- Replay uses existing replay/verification concepts where applicable.

## Status

**Planned**
