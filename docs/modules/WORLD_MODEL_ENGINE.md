# World Model Engine

## Vision

A module that reconstructs a **world state** from DSM events. It consumes the event stream (read via DSM-RR or the kernel read API) and produces structured snapshots of projects, systems, and tasks.

## Responsibilities

- Reconstruct **state of project** — modules, status, milestones from events.
- Reconstruct **state of system** — infrastructure, services, config from events.
- Reconstruct **state of tasks** — open/closed tasks, assignments, outcomes from events.

Output is a consistent, queryable view of “how things stand” at a given time or event cursor.

## Architecture

- Reads from DSM (or DSM-RR) as the source of truth.
- Applies projection rules to derive state views (e.g. `state_of_project`, `state_of_system`, `state_of_tasks`).
- Output can be consumed by planners, skills, and UI.

## Example output

```yaml
project: daryl

modules:
  - DSM
  - DarylViz
  - BattleOfNodes

status:
  - DSM kernel frozen
  - RR planned
```

Similar structures for system state (services, health) and task state (backlog, done, blocked).

## Status

**Planned**
