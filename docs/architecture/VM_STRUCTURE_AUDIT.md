# VM Structure Audit — Daryl / DSM

Structural audit of the development VM for the Daryl / DSM project. **Analysis only; no files were modified, moved, or refactored.**

---

## 1. VM Overview

The VM has a single primary user home directory. The following zones were scanned:

| Zone | Path | Purpose (detected) |
|------|------|--------------------|
| **Home** | `~/` (`/home/buraluxtr`) | User home; contains clawd, dsm_staging_repo_2, memory, clawdbot_dsm_test, and other projects. |
| **Laboratory** | `~/clawd` | Experimental workspace: DSM-related code (dsm_v2, dsm_modules), many scripts, docs, runtime data, Moltbook/Telegram/bot code. |
| **Staging repo (candidate)** | `~/dsm_staging_repo_2` | Separate Git repo: slot normalizer + custom DSM-style kernel/modules (src/dsm_kernel, src/dsm_modules). **Not** the same layout as the canonical DSM kernel. |
| **Runtime data** | `~/memory` | Minimal: single `logs/` directory with one log file. |
| **Official DSM repo (on this VM)** | `/opt/daryl` | Git repository containing the **canonical DSM kernel** layout: `memory/dsm/core`, `session`, `rr`, `block_layer`, `ans`, plus docs, tests, agents. |

**Finding:** The **canonical DSM kernel** (structure with `memory/dsm/core`, `session`, `rr`, `block_layer`, `ans`) exists in only one place on the VM: **`/opt/daryl`**. It does **not** exist under `~/dsm_staging_repo_2` (which has a different project structure). It exists in **partial/copy form** under `~/clawd/dsm_v2` (core, session, ans, skills, modules — but **no** `rr`, **no** `block_layer`).

---

## 2. Directory Classification

### 2.1 Scan results per directory

**`~/` (home)**  
- **Purpose:** User home; aggregates all projects and config.  
- **Type:** Mixed (config, multiple projects, runtime dirs).  
- **Contains:** `.cursor`, `.clawdbot`, `clawd`, `dsm_staging_repo_2`, `memory`, `clawdbot_dsm_test`, other project dirs (e.g. polymarket_bot, aurelian-web-temp).

**`~/clawd`**  
- **Purpose:** Experimental laboratory for DSM, Clawdbot, Moltbook, Telegram, feeds, and related tooling.  
- **Type:** Code + runtime + docs + experiments.  
- **Contains:**  
  - Git repo (`.git`).  
  - `dsm_v2/` — DSM-like package (core, session, ans, skills, modules, storage, moltbook; **no** rr, **no** block_layer).  
  - `dsm_modules/` — e.g. dsm_rr (index/navigator style).  
  - `data/` — runtime (diagnostics, index, integrity, runtime, security, shards).  
  - 200+ Python scripts at root (dsm_*.py, fix_*.py, apply_*.py, moltbook_*.py, etc.).  
  - Many markdown docs (DSM_*, MOLTBOOK_*, HEARTBEAT.md, etc.).  
  - `daryl-faucet/`, `sharding_project/`, and other experiments.  
- **Size:** ~289 MB.

**`~/dsm_staging_repo_2`**  
- **Purpose:** Separate project (slot normalizer + custom DSM-style components).  
- **Type:** Code + config + docs.  
- **Contains:**  
  - Git repo, `.venv`, `config/`, `docs/`, `scripts/`, `tests/`.  
  - `src/dsm_kernel/` — api, integrity, shard_manager, shard_catalog, event_log (different from `memory/dsm/core`).  
  - `src/dsm_modules/` — dsm_rr, dsm_cache, dsm_cleaner, dsm_compressor, dsm_loop, dsm_router, dsm_validator.  
  - `src/services/`, `src/dsm_tools/`.  
  - SLOT_NORMALIZER_* documentation.  
- **Not** the canonical DSM kernel layout (no `memory/dsm/core`, etc.).  
- **Size:** ~98 MB.

**`~/memory`**  
- **Purpose:** Runtime data (logs).  
- **Type:** Runtime.  
- **Contains:** `logs/` with one log file (e.g. `dsm_20260209.log`).

**`~/clawdbot_dsm_test`**  
- **Purpose:** Test or runtime data for DSM/Clawdbot.  
- **Type:** Runtime.  
- **Contains:** directory named `memory`; total ~680 KB.

**`/opt/daryl`**  
- **Purpose:** Official DSM repository on this VM — canonical kernel and layers.  
- **Type:** Code + documentation + tests.  
- **Contains:**  
  - Git repo.  
  - `memory/dsm/` with **core**, **session**, **rr**, **block_layer**, **ans**, skills, modules, storage, moltbook, tests_v2.  
  - `docs/`, `docs/architecture/`, `tests/`, `agents/` (symlink to clawd runtime), `pyproject.toml`, `ARCHITECTURE.md`, `AGENTS.md`, `HEARTBEAT.md`.  
  - Root `data/` (runtime) and `dsm_v2.egg-info/` (build).  
- **Size:** ~2.7 MB (without large runtime).

### 2.2 Classification table

| Category | Directories |
|----------|-------------|
| **LAB** | `~/clawd` — experiments, scripts, lab DSM copy (dsm_v2), dsm_modules, Moltbook/Telegram, many one-off scripts and docs. |
| **REPOSITORY** | `/opt/daryl` — canonical DSM Git repo. `~/dsm_staging_repo_2` — separate Git repo (slot normalizer + custom DSM-style kernel). |
| **RUNTIME** | `~/memory` (logs), `~/clawdbot_dsm_test`, `~/clawd/data`, `~/clawd/dsm_v2/data`, `~/clawd/dsm_v2/core/data`, `/opt/daryl/data`. |
| **TOOLS** | Scripts and CLI under `~/clawd` (dsm_*.py, daryl_memory_cli, etc.); `/opt/daryl` CLI via `memory/dsm/cli.py`. |
| **EXPERIMENTAL** | `~/clawd` (entire tree: fix_*, apply_*, add_*, moltbook_*, daryl-faucet, sharding_project, etc.). |

---

## 3. DSM Kernel Location

**Canonical structure (architecture):**  
`memory/dsm/core`, `memory/dsm/session`, `memory/dsm/rr`, `memory/dsm/block_layer`, `memory/dsm/ans`.

**Where it exists:**

| Location | core | session | rr | block_layer | ans |
|----------|------|---------|-----|-------------|-----|
| **/opt/daryl** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **~/clawd/dsm_v2** | ✅ | ✅ | ❌ | ❌ | ✅ |
| **~/dsm_staging_repo_2** | ❌ (different layout) | ❌ | — | — | — |

**Conclusion:**

- The **real DSM kernel** (full canonical layout) lives in **`/opt/daryl`** only.
- **`~/clawd/dsm_v2`** is a **copy or variant** of DSM with core, session, ans, skills, modules — but **no** rr or block_layer. It also contains runtime data (`data/`, `logs/`) and is embedded in the lab.
- **`~/dsm_staging_repo_2`** is a **different codebase** (slot normalizer + `src/dsm_kernel`, `src/dsm_modules`), not the same as `memory/dsm`.

---

## 4. Structural Issues

### 4.1 Runtime files inside potential repositories

- **~/clawd:** Contains `data/`, `dsm_v2/data/`, `dsm_v2/core/data/`, `dsm_v2/logs/` — runtime and shard data live inside the lab repo. These should not be committed (or should be ignored).
- **/opt/daryl:** Contains root `data/` (shards, integrity, security) and `memory/dsm` runtime dirs; `.gitignore` and VM scan report already recommend ignoring `data/` and runtime paths.

### 4.2 Duplicated DSM implementations

- **Two DSM-like codebases:**  
  - **/opt/daryl** — full kernel (memory/dsm with core, session, rr, block_layer, ans).  
  - **~/clawd/dsm_v2** — partial copy (core, session, ans, skills, modules; no rr, no block_layer).  
- Divergence risk: fixes or features in one place may not exist in the other. Lab (clawd) may have older or different code.

### 4.3 Multiple DSM versions / names

- **dsm_v2** — used in /opt/daryl as symlink `dsm_v2` → `memory/dsm`; in clawd as directory `dsm_v2/` (actual package).  
- **dsm_lite, dsm_lite_fixed** — scripts under `~/clawd` (e.g. dsm_lite.py, dsm_lite_fixed.py).  
- **dsm_modules** — in clawd (dsm_rr, etc.) and in dsm_staging_repo_2 (src/dsm_modules).  
- **dsm_kernel** — in dsm_staging_repo_2 (src/dsm_kernel) with different modules (api, shard_manager, integrity, etc.).  
- Naming and layout are inconsistent across the VM; the only place that matches the documented “memory/dsm” architecture is **/opt/daryl**.

### 4.4 Experimental scripts mixed with architecture code

- **~/clawd** has 200+ Python files at root: fix_*, apply_*, add_*, dsm_*, moltbook_*, test_*, etc. These are experiments and one-off scripts alongside the dsm_v2 package.  
- Lab docs (DSM_*, MOLTBOOK_*, HEARTBEAT.md, etc.) and code live together; no clear separation between “stable DSM” and “lab-only” in the same tree.

### 4.5 Symlinks and references

- **/opt/daryl/agents/clawdbot/runtime** → `~/clawd` (points lab as runtime for the “clawdbot” agent from the repo).  
- **/opt/daryl/dsm_v2** → `memory/dsm` (same repo, alias for package path).  
- So the “official” repo at /opt/daryl **depends on the lab** (clawd) for that agent runtime; clawd is not a clone of /opt/daryl.

---

## 5. Recommended Organization

### 5.1 Architecture map (target view)

```
VM Structure

LAB (experimental)
    ~/clawd
    — DSM experiments, scripts, dsm_v2 copy, dsm_modules, Moltbook/Telegram, runtime data
    — Keep as laboratory; do not treat as canonical DSM repo

REPOSITORY (canonical DSM)
    /opt/daryl
    — Single source of truth for DSM kernel (memory/dsm: core, session, rr, block_layer, ans)
    — Docs, tests, pyproject.toml; minimal runtime under data/ (ignored)

REPOSITORY (other project)
    ~/dsm_staging_repo_2
    — Separate project (slot normalizer + custom dsm_kernel/dsm_modules)
    — Not the Daryl DSM kernel; keep separate

RUNTIME
    ~/memory
    — Logs only

RUNTIME / TEST DATA
    ~/clawdbot_dsm_test
    — Test/runtime data; do not commit
```

### 5.2 Which directory should become the official DSM repository

- **Use `/opt/daryl`** as the **official DSM repository**.  
- It is the only location with the full canonical layout (`memory/dsm/core`, `session`, `rr`, `block_layer`, `ans`) and with architecture docs (docs/architecture), AGENTS.md, HEARTBEAT.md, pyproject.toml.  
- **Do not** use `~/dsm_staging_repo_2` as the DSM kernel repo — it is a different project (slot normalizer + custom kernel).  
- **Do not** use `~/clawd` as the official repo — it mixes lab scripts, partial DSM copy, and runtime; it is the right place for experiments only.

### 5.3 Which directory should remain a laboratory

- **`~/clawd`** should remain the **laboratory**.  
- Use it for: experiments, one-off scripts, Moltbook/Telegram/bot code, dsm_modules (e.g. RR indexer), and any copy of DSM used for testing.  
- When features or fixes are validated in the lab, they should be ported into **/opt/daryl** (or into a branch of the official repo), not the other way around for “stable” kernel code.

### 5.4 Which files should never be committed

- **Runtime data:**  
  - `~/memory/`, `~/clawdbot_dsm_test/`,  
  - `~/clawd/data/`, `~/clawd/dsm_v2/data/`, `~/clawd/dsm_v2/core/data/`, `~/clawd/dsm_v2/logs/`,  
  - `/opt/daryl/data/`, any `**/shards/**`, `**/integrity/**`, `**/logs/*.jsonl`, `**/audit.jsonl`.  
- **Build/cache:** `**/__pycache__/`, `*.pyc`, `*.egg-info/`, `.venv/`, `.pytest_cache/`.  
- **Secrets/config (per env):** `.env`, credentials, wallet files (e.g. `*_wallet*.json` in lab).  
- **Large or generated:** zips, tarballs, dumps — unless explicitly versioned as release artifacts.

---

## 6. Next Steps

1. **Confirm official repo:** Treat **/opt/daryl** as the single canonical DSM repository. Ensure Git ignores `data/`, `**/logs/`, `*.egg-info/`, and any runtime paths (see VM_REPOSITORY_SCAN.md).  
2. **Document lab vs repo:** In docs (e.g. LAB_TO_DARYL_MIGRATION_PLAN.md or README), state that `~/clawd` is the laboratory and `/opt/daryl` is the official DSM repo; document the symlink `agents/clawdbot/runtime` → `~/clawd`.  
3. **Avoid double maintenance:** Prefer developing kernel and RR/session/block_layer in **/opt/daryl**. Sync or copy from lab only when a change is validated and should become part of the official tree.  
4. **Clean lab repo (optional):** In `~/clawd`, add or tighten `.gitignore` so that `data/`, `dsm_v2/data/`, `dsm_v2/core/data/`, `dsm_v2/logs/` are not committed.  
5. **Keep dsm_staging_repo_2 separate:** Do not merge it with the DSM kernel repo unless the intent is to adopt its layout and code; today it is a different project (slot normalizer + custom kernel).  
6. **Runtime layout:** Keep `~/memory` and `~/clawdbot_dsm_test` as runtime/test data only; do not version their contents in the DSM repo.

This audit is analysis-only. No code or files were modified, moved, or refactored.
