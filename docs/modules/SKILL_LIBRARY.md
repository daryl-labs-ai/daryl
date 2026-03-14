# Skill Library

## Vision

A structured library of agent skills used by the Skill Router and planners. Skills are organized by domain and follow a consistent format for metadata, documentation, and examples.

## Responsibilities

- Store skill definitions (metadata, triggers, descriptions).
- Provide a directory layout by domain (finance, devops, robotics, research, coding, writing).
- Support DSM-based telemetry: `skill_used`, `skill_success`, `skill_failure`.

## Directory concept

```
skills/
  finance/
  devops/
  robotics/
  research/
  coding/
  writing/
```

Each skill contains:

- **skill.yaml** — Metadata: id, name, domain, triggers, parameters.
- **skill.md** — Human-readable description and usage.
- **examples/** — Example inputs/outputs or traces.

## DSM records

Skills integrate with DSM for observability:

| Record type     | Purpose |
|-----------------|--------|
| **skill_used** | Log when a skill was selected and invoked |
| **skill_success** | Log successful completion and outcome |
| **skill_failure** | Log failures and context for improvement |

These records are written to DSM (append-only); they do not modify the frozen kernel code.

## Status

**Planned**
