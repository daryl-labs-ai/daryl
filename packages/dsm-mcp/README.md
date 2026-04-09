# dsm-mcp

MCP server that connects [Goose](https://github.com/aaif-goose/goose) to DSM's provable memory.

Every action Goose logs is SHA-256 hash-chained. Nothing can be silently altered.

## Install

```bash
pip install dsm-mcp
```

Or run directly with uvx (no install required):

```bash
uvx dsm-mcp
```

## Configure Goose

Add to `~/.config/goose/extensions.d/dsm-memory.yaml`:

```yaml
name: dsm-memory
description: Provable memory for Goose — SHA-256 chained, replayable, verifiable
type: stdio
cmd: uvx
args: ["dsm-mcp"]
```

Restart Goose. 11 MCP tools are now available.

## Available tools

| Tool | What it does |
|---|---|
| `dsm_start_session` | Start a new provable session |
| `dsm_end_session` | End session, trigger digest rolling |
| `dsm_log_action` | Log an action intent (creates hash chain entry) |
| `dsm_confirm_action` | Confirm an action with its result |
| `dsm_snapshot` | Record a state snapshot |
| `dsm_recall` | Budget-aware context recall |
| `dsm_recent` | Read the most recent entries |
| `dsm_summary` | Lightweight activity summary |
| `dsm_search` | Query actions across sessions |
| `dsm_verify` | Verify hash chain integrity |
| `dsm_status` | Current system status |

## Source

Full source and documentation: [daryl-labs-ai/daryl](https://github.com/daryl-labs-ai/daryl/tree/main/src/dsm/integrations/goose)
