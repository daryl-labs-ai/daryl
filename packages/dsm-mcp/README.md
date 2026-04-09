# DSM MCP Server

Provable, append-only memory for AI agents via MCP.

## Install

```bash
pip install dsm-mcp
```

## Run

```bash
dsm-mcp
# or
python -m dsm.integrations.goose
```

## Configure with Goose

Add to `~/.config/goose/extensions.d/dsm-memory.yaml`:

```yaml
name: dsm-memory
type: stdio
cmd: dsm-mcp
```

## What it does

DSM records every agent action in an append-only SHA-256 hash chain.
Nothing can be deleted, reordered, or tampered with without detection.

11 MCP tools: `dsm_status`, `dsm_start_session`, `dsm_end_session`,
`dsm_log_action`, `dsm_confirm_action`, `dsm_snapshot`, `dsm_recall`,
`dsm_recent`, `dsm_summary`, `dsm_search`, `dsm_verify`.

## Links

- Project: https://github.com/daryl-labs-ai/daryl
- Goose integration: https://github.com/daryl-labs-ai/daryl/tree/main/src/dsm/integrations/goose
