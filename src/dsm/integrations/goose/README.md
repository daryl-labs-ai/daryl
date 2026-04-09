# DSM Goose Integration

MCP server that connects [Goose](https://github.com/block/goose) to DSM's provable memory.

## How it works

```
Goose UI  →  MCP stdio  →  DSM Goose server  →  DarylAgent  →  ~/.dsm-data/shards/
                                                                       ↓
                                                              SHA-256 hash chain
                                                              (append-only, verifiable)
```

Every action Goose logs is hash-chained. Nothing can be silently altered.

## Install

```bash
# From the daryl repo
pip install -e ".[goose]"
```

## Configure Goose

Add to `~/.config/goose/extensions.d/dsm-memory.yaml`:

```yaml
name: dsm-memory
description: Provable memory for Goose — SHA-256 chained, replayable, verifiable
type: stdio
cmd: python3
args: ["-m", "dsm.integrations.goose"]
```

Restart Goose. The extension provides 11 MCP tools.

## Available tools

| Tool | What it does |
|---|---|
| `dsm_start_session` | Start a new provable session |
| `dsm_end_session` | End current session, trigger digest rolling |
| `dsm_log_action` | Log an action intent (creates hash chain entry) |
| `dsm_confirm_action` | Confirm an action with its result |
| `dsm_snapshot` | Record a state snapshot |
| `dsm_recall` | Budget-aware context recall with temporal digests |
| `dsm_recent` | Read the most recent entries |
| `dsm_summary` | Lightweight activity summary (entries, sessions, top actions) |
| `dsm_search` | Query actions across sessions |
| `dsm_verify` | Verify hash chain integrity (tamper detection) |
| `dsm_status` | Current system status (shards, entries, integrity) |

## Quick test

From Goose, after enabling the extension:

```
dsm_status()                  # → JSON with shard info
dsm_start_session("test")     # → {status: "started"}
dsm_log_action("test", {})    # → {intent_id: "..."}
dsm_recent(limit=5)           # → entries just written
dsm_verify()                  # → {status: "OK"}
```

## Run standalone (debug)

```bash
python3 -m dsm.integrations.goose --help
python3 -m dsm.integrations.goose --data-dir /tmp/test-dsm --debug
```

## Run tests

```bash
python -m pytest tests/integrations/test_goose.py -v   # 14 tests
```

## Data location

By default, DSM writes to `~/.dsm-data/shards/`. Each shard is a JSONL segment with SHA-256 chained entries.

Override with `DSM_DATA_DIR` environment variable.
