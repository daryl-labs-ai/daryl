# VM Repository Scan — Daryl / DSM

Filesystem scan of the project environment for clean Git repository migration. **Analysis only; no files were modified.**

---

## 1. Detected Project Root

**Project root:** `/opt/daryl`

This directory contains:

- **DSM source code** — `memory/dsm/` (core, session, rr, block_layer, skills, ans, modules, storage, moltbook)
- **Documentation** — `docs/`, `docs/architecture/`, `docs/roadmap/`, `ARCHITECTURE.md`, `AGENTS.md`, `HEARTBEAT.md`
- **Scripts / tests** — `memory/dsm/*.py` (CLI, trace_replay, tests), `memory/dsm/tests_v2/`, `tests/`
- **Package metadata** — `pyproject.toml`, `dsm_v2.egg-info/`
- **Agents / examples** — `agents/`, `examples/`, `modules/`, `skills/` (top-level)

---

## 2. Directory Tree (Depth 4)

```
/opt/daryl/
   .git/
   agents/
      clawdbot/           # symlink runtime → external; dsm_v2 → memory/dsm
   data/
      integrity/
      security/
      shards/
         default/
   docs/
      architecture/
      roadmap/
   dsm_v2.egg-info/
   examples/
   memory/
      dsm/
         ans/
         block_layer/
         core/
            data/         # runtime (integrity, security, shards)
         data/            # runtime (integrity, shards)
         logs/            # runtime
         modules/
         moltbook/
         rr/
         session/
         skills/
            browser/
            libraries/
               anthropic/
               community/
               custom/
            logs/          # runtime
         storage/
         tests/
         tests_v2/
   modules/
   skills/
   tests/
```

*Note: `__pycache__` directories exist under memory/dsm and subpackages; omitted from tree for clarity.*

---

## 3. Code Directories

Directories containing Python source (`.py` files):

| Directory | Purpose |
|-----------|---------|
| `memory/dsm/` | Main DSM package (root) |
| `memory/dsm/ans/` | ANS (Audience Neural System) |
| `memory/dsm/block_layer/` | Block aggregation layer |
| `memory/dsm/core/` | DSM kernel (storage, models, segments, signing, replay, security, etc.) |
| `memory/dsm/modules/` | Optional modules (e.g. dsm_rm) |
| `memory/dsm/moltbook/` | Moltbook support |
| `memory/dsm/rr/` | Read Relay (relay.py) |
| `memory/dsm/session/` | SessionGraph, SessionLimitsManager |
| `memory/dsm/skills/` | Skill registry, router, ingestor, loggers |
| `memory/dsm/skills/browser/` | Browser skill |
| `memory/dsm/skills/libraries/` | Skill libraries (anthropic, community, custom) |
| `memory/dsm/storage/` | Storage facade |
| `memory/dsm/tests_v2/` | Kernel/session tests |
| `tests/` | Top-level tests (dsm_rr_test, clawdbot_dsm_session_test) |

**Note:** `agents/clawdbot/runtime` is a symlink to `/home/buraluxtr/clawd` (external). `dsm_v2` at repo root is a symlink to `memory/dsm` (same code).

---

## 4. Runtime Data Directories

Directories that contain runtime data and **should NOT be committed to Git**:

| Directory | Content |
|-----------|---------|
| `data/` | Root DSM data: integrity, security, shards (default) |
| `data/integrity/` | Last-hash / integrity metadata per shard |
| `data/security/` | Security audit log (audit.jsonl) |
| `data/shards/` | Shard family directories and segment JSONL files |
| `data/shards/default/` | Default shard segments (e.g. default_0001.jsonl) |
| `memory/dsm/core/data/` | Core runtime data (integrity, security, shards) — duplicate/legacy layout |
| `memory/dsm/data/` | Alternate data dir (integrity, shards) |
| `memory/dsm/logs/` | Skills usage/success JSONL logs |
| `memory/dsm/skills/logs/` | Skills telemetry JSONL (duplicate or alternate path) |

**Recommendation:** All of the above should be ignored by Git. Shard segments (`.jsonl`), integrity files, and log files are runtime-generated and environment-specific.

**Optional future (RR):** `data/index/` — if RR index is implemented, it should also be ignored (derived, rebuildable).

---

## 5. Large Files

**Search:** Files larger than 10 MB under the project root (excluding `.git`).

**Result:** **None.** No files over 10 MB were found.

All detected JSONL and data files are small (bytes to a few KB). No large binaries or dumps present in the scanned tree.

---

## 6. DSM Shard Detection

**Patterns:** `*.jsonl`, `*_0001.jsonl`, `*_0002.jsonl` (segment naming).

**Detected files:**

| Directory | File count | Files | Total size (approx) |
|-----------|------------|--------|----------------------|
| `data/shards/default/` | 1 | default_0001.jsonl | 688 B |
| `data/security/` | 1 | audit.jsonl | 965 B |
| `memory/dsm/core/data/shards/` | 1 | security_baseline.jsonl | 672 B |
| `memory/dsm/core/data/shards/sessions/` | 1 | sessions_0001.jsonl | 2,208 B |
| `memory/dsm/logs/` | 2 | skills_success.jsonl, skills_usage.jsonl | ~3.3 KB |
| `memory/dsm/skills/logs/` | 2 | skills_success.jsonl, skills_usage.jsonl | ~2.2 KB |

**Summary:**

- **Shard segments (DSM event storage):** `data/shards/default/default_0001.jsonl`, `memory/dsm/core/data/shards/sessions/sessions_0001.jsonl`. These are DSM append-only shards (or test/legacy data).
- **Security/audit:** `data/security/audit.jsonl`, `memory/dsm/core/data/shards/security_baseline.jsonl` — runtime/security artifacts.
- **Telemetry logs:** `memory/dsm/logs/*.jsonl`, `memory/dsm/skills/logs/*.jsonl` — skills usage/success logs (not DSM kernel shards).

All of these should be excluded from version control.

---

## 7. Git Status

**Repository:** Present at `/opt/daryl` (`.git/` exists).

**Current status (summary):**

- **Modified (M):** Many files under `memory/dsm/` (core, session, skills, modules, tests, CLI, etc.), plus `ARCHITECTURE.md`. Several `__pycache__/*.pyc` files are tracked and show as modified.
- **Untracked (??):** `.gitignore`, `AGENTS.md`, `HEARTBEAT.md`, `data/`, `docs/`, `dsm_v2.egg-info/`, `memory/dsm/block_layer/`, `memory/dsm/rr/`, `pyproject.toml`, `tests/`, and some new skill/library files.

**Tracked files that are runtime/derived (should be ignored):**

- `memory/dsm/core/data/integrity/sessions_last_hash.json`
- `memory/dsm/core/data/shards/security_baseline.jsonl`
- `memory/dsm/core/data/shards/sessions/sessions_0001.jsonl`
- `memory/dsm/logs/skills_success.jsonl`
- `memory/dsm/logs/skills_usage.jsonl`
- `memory/dsm/skills/logs/skills_success.jsonl`
- `memory/dsm/skills/logs/skills_usage.jsonl`
- `memory/dsm/__pycache__/` and other `__pycache__` directories

**Current `.gitignore` (exists):**

```
# Python
__pycache__/
*.pyc

# Logs
logs/
*.log
*.jsonl

# Data shards
memory/dsm/core/data/

# Environment
.env
venv/
```

**Gaps:** Root `data/` is not ignored (so `data/` appears as untracked). `*.jsonl` is ignored but some JSONL files were committed before and remain tracked. `dsm_v2.egg-info/` is build artifact and should be ignored. Broader `data/` and `**/logs/` coverage is recommended.

---

## 8. Classify Project Content

| Category | Directories / paths |
|----------|----------------------|
| **CODE** | `memory/dsm/` (excluding data, logs, __pycache__), `memory/dsm/core/`, `memory/dsm/session/`, `memory/dsm/rr/`, `memory/dsm/block_layer/`, `memory/dsm/skills/`, `memory/dsm/ans/`, `memory/dsm/modules/`, `memory/dsm/storage/`, `memory/dsm/moltbook/` |
| **DOCUMENTATION** | `docs/`, `docs/architecture/`, `docs/roadmap/`, `ARCHITECTURE.md`, `AGENTS.md`, `HEARTBEAT.md` |
| **TESTS** | `memory/dsm/tests_v2/`, `tests/`, and `*_test*.py` under `memory/dsm/` |
| **SCRIPTS** | `memory/dsm/cli.py`, `memory/dsm/trace_replay.py`, `memory/dsm/run_stability_suite.py`, `memory/dsm/check_dsm_config.py`, and other runnable modules at `memory/dsm/` root |
| **RUNTIME DATA** | `data/`, `memory/dsm/core/data/`, `memory/dsm/data/` |
| **LOGS** | `memory/dsm/logs/`, `memory/dsm/skills/logs/` |
| **BUILD / CACHE** | `dsm_v2.egg-info/`, `__pycache__/` (everywhere) |
| **SYMLINKS / EXTERNAL** | `agents/clawdbot/runtime` → external; `dsm_v2` → memory/dsm (optional alias) |

---

## 9. Recommended Repository Structure

**Proposed clean layout (what should be committed):**

```
repo/
   memory/
      dsm/
         __init__.py
         cli.py
         security.py
         storage/          # facade
         core/             # kernel (no core/data/)
         session/
         rr/
         block_layer/
         skills/
         ans/
         modules/
         moltbook/
         tests_v2/
         trace_replay.py
         ... (other .py at dsm root)
   docs/
      architecture/
      roadmap/
      *.md
   tests/
   agents/
      clawdbot/            # only non-runtime assets if any; or document runtime symlink
   examples/
   modules/
   skills/
   ARCHITECTURE.md
   AGENTS.md
   HEARTBEAT.md
   pyproject.toml
   .gitignore
```

**Committed:**

- All Python source under `memory/dsm/` except under `data/`, `logs/`, `__pycache__/`.
- All documentation under `docs/` and root `.md` files.
- `tests/`, `memory/dsm/tests_v2/`.
- `pyproject.toml`, `.gitignore`.
- Skill/library definitions (JSON, SKILL.md, manifest) under `memory/dsm/skills/libraries/`.
- Top-level `examples/`, `modules/`, `skills/` if they contain source or config to version; otherwise document or remove from repo.
- `agents/clawdbot/` only if it contains versioned config; the `runtime` symlink points outside the repo and should not commit the target.

**Ignored:**

- `data/` (entire root data tree).
- `memory/dsm/core/data/`, `memory/dsm/data/`.
- `memory/dsm/logs/`, `memory/dsm/skills/logs/`.
- `**/__pycache__/`, `*.pyc`.
- `*.jsonl` (or explicitly `data/**/*.jsonl`, `**/logs/*.jsonl`).
- `dsm_v2.egg-info/`.
- `.env`, `venv/`, `*.log`.

**Moved / cleaned (optional for migration):**

- Remove runtime and build artifacts from Git tracking: `git rm --cached` for `memory/dsm/core/data/`, `memory/dsm/logs/`, `memory/dsm/skills/logs/`, and any `__pycache__` if currently tracked. Then rely on `.gitignore` so they are not re-added.
- Ensure root `data/` is in `.gitignore` so it is never committed.
- Decide whether to keep `agents/clawdbot/runtime` as a symlink (document only) or replace with a stub that points to an env-specific path.

---

## 10. Suggested .gitignore

Proposed contents for a comprehensive `.gitignore` (merge with existing; do not remove existing entries that are still desired):

```gitignore
# Python
__pycache__/
*.py[cod]
*.pyo
*.pyd
.Python
*.so
*.egg
*.egg-info/
*.eggs
dist/
build/

# DSM runtime data — do not commit
data/
memory/dsm/core/data/
memory/dsm/data/

# Logs and telemetry
logs/
*.log
*.jsonl
memory/dsm/logs/
memory/dsm/skills/logs/

# RR index (when implemented)
data/index/

# Environment
.env
.env.*
venv/
.venv/

# IDE / OS
.idea/
.vscode/
*.swp
.DS_Store

# Optional: keep shard pattern explicit if needed
# data/shards/
# **/shards/**/*.jsonl
```

**Rationale:**

- `data/` at root covers all DSM data (shards, integrity, security) in one place.
- `memory/dsm/core/data/` and `memory/dsm/data/` cover legacy/alternate data dirs.
- `*.jsonl` avoids committing any JSONL (shards, audit, skills logs). If you need to version specific JSONL (e.g. fixtures), use exceptions or a different extension for fixtures.
- `data/index/` prepares for future RR index (derived, rebuildable).
- `dsm_v2.egg-info/` and other build artifacts keep the tree clean.

---

## 11. Summary

| Item | Result |
|------|--------|
| **Project root** | `/opt/daryl` |
| **Code directories** | `memory/dsm/` and subpackages (core, session, rr, block_layer, skills, ans, modules, storage, moltbook, tests_v2); `tests/` |
| **Runtime data** | `data/`, `memory/dsm/core/data/`, `memory/dsm/data/`, `memory/dsm/logs/`, `memory/dsm/skills/logs/` — should not be committed |
| **Large files** | None > 10 MB |
| **DSM shards** | 2 segment files (default, sessions) plus audit/skills JSONL in 6 locations; total size negligible |
| **Git** | Repository present; some runtime and cache files still tracked; `.gitignore` exists but incomplete |
| **Recommendation** | Broaden `.gitignore` (root `data/`, logs, egg-info, index); stop tracking runtime/cache files; keep only source, docs, tests, and config in the repository |

This report is analysis-only. No files were modified. Use it to plan the clean Git repository migration (e.g. update `.gitignore`, run `git rm --cached` on listed paths, then re-add and commit only the desired tree).
