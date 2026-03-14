# Contributing to Daryl

Thank you for your interest in contributing.

## Development setup

```bash
git clone <repo>
cd daryl
pip install -e .[dev]
```

## Running tests

```bash
python -m pytest tests/ -v
```

## Critical rule

**Do not modify `src/dsm/core/` without discussion and approval.**

The DSM kernel is frozen (March 2026). Changes to the core storage, models, or segments require explicit agreement from maintainers.

## Commit format

Use conventional commits:

```
type(scope): description
```

Examples:

- `docs(readme): add installation section`
- `fix(session): handle missing session_id`
- `feat(skills): add trigger_conditions to router`

Types: `docs`, `fix`, `feat`, `build`, `refactor`, `test`, etc.
