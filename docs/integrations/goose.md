# DSM × Goose Integration

Provable memory backend for [Goose](https://github.com/block/goose) via MCP.

DSM records every agent action in a SHA-256 hash chain. Nothing can be deleted, reordered, or tampered with without detection.

## What it does

- **Session lifecycle** — start, end, and label sessions
- **Action logging** — record intents with optional metadata
- **Memory recall** — retrieve recent entries or search by keyword
- **Snapshots** — save and restore agent state
- **Integrity verification** — verify hash chain is intact

## Install

From the daryl repo:

```bash
pip install -e ".[goose]"
```

This installs the optional `mcp` dependency.

## Configure

Create `~/.config/goose/extensions.d/dsm-memory.yaml`:

```yaml
name: dsm-memory
description: Provable memory for Goose — SHA-256 chained, replayable, verifiable
type: stdio
cmd: python3
args: ["-m", "dsm.integrations.goose"]
```

Restart Goose.

## Quick test

After restarting Goose, run these from the Goose interface:

```
dsm_status()
```

Should return JSON with shard info and entry count.

```
dsm_start_session("my-session")
```

Should return a session confirmation.

```
dsm_log_action("user_prompt", {"text": "hello from goose"})
```

Should log the action and return a hash.

```
dsm_recent(limit=5)
```

Should list recent entries including the ones you just created.

```
dsm_verify()
```

Should return `status: OK, tampered: 0`.

## Available tools

| Tool | Description |
|---|---|
| `dsm_status` | System status (shards, entries, integrity) |
| `dsm_start_session` | Start a new session with optional label |
| `dsm_end_session` | End the current session |
| `dsm_log_action` | Log an action/intent (pending confirmation) |
| `dsm_confirm_action` | Confirm a previously logged action |
| `dsm_snapshot` | Save a state snapshot |
| `dsm_recall` | Recall entries with budget-aware retrieval |
| `dsm_recent` | Get most recent entries |
| `dsm_summary` | Get session summary statistics |
| `dsm_search` | Search entries by keyword |
| `dsm_verify` | Verify hash chain integrity |

## Where data is stored

By default: `~/.dsm-data/shards/`

Data is stored as append-only JSONL segment files with SHA-256 hash chains.

To use a custom directory, set the `DSM_DATA_DIR` environment variable or pass `--data-dir` in the Goose config:

```yaml
cmd: python3
args: ["-m", "dsm.integrations.goose", "--data-dir", "/path/to/data"]
```

## Typical user scenario

1. Start Goose → extension loads automatically
2. `dsm_start_session("project-alpha")` → session created
3. Work normally — DSM logs actions via `dsm_log_action`
4. `dsm_recent(limit=10)` → review what was recorded
5. `dsm_verify()` → confirm nothing was tampered with
6. `dsm_end_session()` → close session cleanly

## Limitations

- **Experimental** — validated in controlled environments, not yet stress-tested at scale
- **No semantic search** — DSM stores and verifies, it doesn't understand content. Use a vector DB alongside for semantic retrieval.
- **Requires daryl repo** — installation is currently `pip install -e ".[goose]"` from the daryl repo. Standalone PyPI package is planned.
- **Single machine** — DSM is a local filesystem store, not a network service.
- **Goose is one integration** — DSM is a standalone memory system. Goose is the first integration, others may follow.

## Troubleshooting

**Extension not loading**

Check that `mcp` is installed: `pip install mcp>=1.25.0`

**`No module named 'dsm'`**

DSM is not installed. Run: `pip install -e ".[goose]"` from the daryl repo.

**`No module named 'dsm.rr'`**

Restart Goose completely (quit the app, not just close the window). This can happen if Goose's MCP process was started before DSM was fully installed.

**Tools visible but calls fail**

Check Goose logs for MCP errors. Most import errors are resolved by a full Goose restart.
