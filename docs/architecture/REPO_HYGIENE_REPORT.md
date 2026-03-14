# Repository Hygiene Report

**Repository:** `/opt/daryl` (canonical DSM)  
**Date:** 2025-03-13  
**Phase:** Phase 1 — Repository hygiene (VM Organization Plan)  
**Reference:** docs/architecture/VM_ORGANIZATION_TODO.md

---

## 1. Runtime files that were tracked

Before hygiene, Git was tracking the following runtime and cache artifacts:

### Runtime data (shards / integrity)

| Path | Type |
|------|------|
| `memory/dsm/core/data/integrity/sessions_last_hash.json` | Integrity / chain state |
| `memory/dsm/core/data/shards/security_baseline.jsonl` | Shard JSONL |
| `memory/dsm/core/data/shards/sessions/sessions_0001.jsonl` | Shard JSONL |

### Logs (JSONL)

| Path | Type |
|------|------|
| `memory/dsm/logs/skills_success.jsonl` | Skills telemetry log |
| `memory/dsm/logs/skills_usage.jsonl` | Skills telemetry log |
| `memory/dsm/skills/logs/skills_success.jsonl` | Skills telemetry log |
| `memory/dsm/skills/logs/skills_usage.jsonl` | Skills telemetry log |

### Python caches (`__pycache__` / `*.pyc`)

| Path |
|------|
| `memory/dsm/__pycache__/__init__.cpython-310.pyc` |
| `memory/dsm/ans/__pycache__/__init__.cpython-310.pyc` |
| `memory/dsm/ans/__pycache__/ans_models.cpython-310.pyc` |
| `memory/dsm/core/__pycache__/__init__.cpython-310.pyc` |
| `memory/dsm/core/__pycache__/models.cpython-310.pyc` |
| `memory/dsm/core/__pycache__/shard_segments.cpython-310.pyc` |
| `memory/dsm/core/__pycache__/storage.cpython-310.pyc` |

### Not tracked (verified)

- Root `data/` — was untracked; no `git rm --cached` needed.
- `dsm_v2.egg-info/` — untracked; now covered by `.gitignore`.
- No other `build/` or `dist/` artifacts were tracked.

---

## 2. .gitignore changes

The repository `.gitignore` was updated to include all required rules.

### Before

- `__pycache__/`, `*.pyc`
- `logs/`, `*.log`, `*.jsonl`
- `memory/dsm/core/data/`
- `.env`, `venv/`

### Added (or explicitly ensured)

| Rule | Purpose |
|------|---------|
| `data/` | Root-level runtime data directory |
| `data/index/` | Runtime index under data |
| `memory/dsm/data/` | Alternate DSM data path |
| `build/` | Build output |
| `dist/` | Distribution artifacts |
| `*.egg-info/` | Setuptools build info |

### Final .gitignore (relevant excerpt)

```
# Python
__pycache__/
*.pyc

# Logs
logs/
*.log
*.jsonl

# Data and runtime
data/
data/index/
memory/dsm/core/data/
memory/dsm/data/

# Build
build/
dist/
*.egg-info/

# Environment
.env
venv/
```

---

## 3. Files removed from Git tracking

The following paths were removed from the Git index with `git rm --cached` (files remain on disk).

### Runtime data (3 files)

- `memory/dsm/core/data/integrity/sessions_last_hash.json`
- `memory/dsm/core/data/shards/security_baseline.jsonl`
- `memory/dsm/core/data/shards/sessions/sessions_0001.jsonl`

### Logs (4 files)

- `memory/dsm/logs/skills_success.jsonl`
- `memory/dsm/logs/skills_usage.jsonl`
- `memory/dsm/skills/logs/skills_success.jsonl`
- `memory/dsm/skills/logs/skills_usage.jsonl`

### Python caches (7 files)

- `memory/dsm/__pycache__/__init__.cpython-310.pyc`
- `memory/dsm/ans/__pycache__/__init__.cpython-310.pyc`
- `memory/dsm/ans/__pycache__/ans_models.cpython-310.pyc`
- `memory/dsm/core/__pycache__/__init__.cpython-310.pyc`
- `memory/dsm/core/__pycache__/models.cpython-310.pyc`
- `memory/dsm/core/__pycache__/shard_segments.cpython-310.pyc`
- `memory/dsm/core/__pycache__/storage.cpython-310.pyc`

**Total:** 14 files removed from tracking. No files were deleted from disk.

---

## 4. Commit summary

| Field | Value |
|-------|--------|
| **Commit hash** | `61ef0f7` |
| **Message** | `repository hygiene: remove runtime data and caches from tracking` |
| **Branch** | `main` |
| **Pushed** | No (as requested) |

**Staged changes:**

- **Added:** `.gitignore` (new or updated with full rule set)
- **Deleted from index only:** 14 paths (3 runtime data, 4 logs, 7 `__pycache__`)

**Not staged (intentionally):**

- All modified source files (e.g. `memory/dsm/cli.py`, skills, tests, etc.) were left unstaged; only hygiene-related changes were committed.

---

## Constraints respected

- No DSM kernel code modified.
- No directories moved.
- No refactoring of architecture.
- Only repository hygiene tasks performed in `/opt/daryl`.
- Runtime files were untracked with `git rm --cached`; no deletion from disk.
