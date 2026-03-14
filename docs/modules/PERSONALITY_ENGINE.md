# Personality Engine

## Vision

A system where each Daryl agent has a **persistent cognitive personality** that shapes planning, exploration, and response style. Personality parameters are stored and updated via DSM events so they survive across sessions and can evolve over time.

## Responsibilities

- Maintain per-agent personality parameters.
- Apply personality to planner behavior, exploration level, risk tolerance, and response style.
- Evolve parameters through DSM events (e.g. `agent_personality_update`).

## Personality parameters

| Parameter    | Effect |
|-------------|--------|
| **curiosity**   | Drive to explore and ask questions |
| **caution**     | Preference for safe vs. bold actions |
| **confidence**  | Assertiveness of decisions and answers |
| **initiative**  | Willingness to act without explicit prompt |
| **verbosity**   | Length and detail of responses |
| **skepticism**  | Tendency to double-check and challenge |
| **persistence** | Willingness to retry and iterate |

These parameters evolve through **DSM events** (e.g. feedback, outcomes) and influence downstream behavior.

## Architecture

- Personality state is derived or stored via DSM (append-only events).
- Events such as `agent_personality_update` record parameter changes.
- Planner and skill router consume personality when choosing actions and response style.

## Example event

```json
{
  "event_type": "agent_personality_update",
  "agent_id": "daryl_01",
  "parameters": {
    "curiosity": 0.8,
    "caution": 0.5,
    "confidence": 0.7
  },
  "reason": "post-task feedback"
}
```

**Effects:** planner behavior, exploration level, risk tolerance, response style.

## Status

**Planned**
