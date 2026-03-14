# Skill Discovery Engine

## Vision

A system that **detects repeated action patterns** in DSM events and proposes new skills. It turns recurring sequences of actions into candidate skills that can be validated and added to the skill library.

## Responsibilities

- Analyze DSM event streams for repeated sequences.
- Propose new skill names and descriptions from patterns.
- Feed a validation step (human or automated) before skill creation.
- Support creation of new skills in the skill library.

## Pipeline

```
DSM events
    ↓
pattern detection
    ↓
skill generation
    ↓
validation
    ↓
skill creation
```

## Example pattern

Observed sequence in events:

1. `analyze_code`
2. `fix_syntax`
3. `run_tests`
4. `generate_patch`

**Proposed new skill:** `auto_refactor_pipeline`

After validation, this can be added as a single skill that encapsulates the pipeline.

## Status

**Planned**
