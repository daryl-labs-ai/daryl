# Daryl Architecture

Daryl is an experimental AI agent architecture built around a deterministic memory kernel called DSM (Daryl Sharding Memory).

## Directory Structure

/opt/daryl

agents/
    clawdbot/
        runtime -> /home/buraluxtr/clawd
        (current production runtime)

memory/
    dsm/
        core/
        session/
        ans/
        skills/
        modules/

modules/
    reusable components

skills/
    future agent skills

examples/
    example agents

tests/
    validation and stress tests

docs/
    documentation

## Core Concepts

DSM (Daryl Sharding Memory)
- append-only storage
- shard-based event logs
- deterministic replay

### Session components

- **SessionTracker** (`memory/dsm/core/session.py`): runtime heartbeat tracking (kernel).
- **SessionGraph** (`memory/dsm/session/session_graph.py`): event logging system — records `session_start`, `tool_call`, `snapshot`, `session_end`.

Clawdbot writes session events to the DSM shard **`clawdbot_sessions`**.

Clawdbot
- main runtime agent
- interacts with DSM
- executes skills

ANS (Audience Neural System)
- analyzes skill performance
- suggests workflow improvements

## Current Runtime

Production runtime lives in:

/home/buraluxtr/clawd

Daryl repository links to it via:

agents/clawdbot/runtime

This allows safe refactoring while production continues running.

## Development Workflow

Cursor → development
Clawdbot → runtime testing
DSM → logging + memory
Git → versioning
