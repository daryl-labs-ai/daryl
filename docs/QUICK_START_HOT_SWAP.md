# Quick Start — Hot Swap in 5 Minutes

**Goal:** prove that a project continues when you change tools.
**Time:** ~5 minutes (after prerequisites).
**Result:** you will see a project pass between tools without copy/paste.

---

## What you will do

```
You define a feature
    ↓
Zcode (or any script) writes it to DSM
    ↓
LM Studio (local LLM) reads it from DSM and reviews it
    ↓
Claude Desktop reads BOTH from DSM and continues
    ↓
Nothing was copy/pasted. The project survived the tool swap.
```

---

## Prerequisites

1. **Python 3.12+** installed
2. **This repository** cloned locally
3. **LM Studio** running with a model loaded (any model, e.g. llama-3.3-70b)
   - Start LM Studio → load a model → confirm API at `http://localhost:1234`
4. **Claude Desktop** installed (optional, for the full 3-actor demo)

---

## Step 1 — Install DSM (30 seconds)

```bash
cd daryl  # the cloned repo

# Create a virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install DSM + dependencies
pip install -e packages/dsm-primitives
pip install -e ".[dev]"
```

Verify:
```bash
python -c "import dsm; print('DSM', dsm.__version__)"
# → DSM 0.8.0
```

---

## Step 2 — Run a 2-actor Hot Swap (Zcode + LM Studio)

This script writes a decision to DSM, then LM Studio reads it and produces
a review — proving cross-tool continuity.

```bash
python research/platform/hot_swap_mvp.py
```

You should see:
```
Actor 1 (Zcode): defines a feature → writes to DSM
Actor 2 (LM Studio): reads from DSM → produces a review → writes back
Final: verify_shard OK, all receipts confirmed
```

**What just happened:** LM Studio read context that Zcode wrote, without
any copy/paste. The project continued across a tool swap.

---

## Step 3 — Connect Claude Desktop (full 3-actor demo)

### 3a. Add DSM to Claude Desktop's MCP config

Open (or create) `~/Library/Application Support/Claude/claude_desktop_config.json`
and add this to the `mcpServers` section:

```json
{
  "mcpServers": {
    "dsm-continuity": {
      "command": "/path/to/daryl/.venv/bin/python",
      "args": ["-m", "dsm.integrations.goose"],
      "env": {
        "DSM_DATA_DIR": "/Users/YOU/.dsm-data",
        "PYTHONPATH": "/path/to/daryl/src:/path/to/daryl/packages/dsm-primitives/src"
      }
    }
  }
}
```

Replace `/path/to/daryl` with your actual clone path and `YOU` with your
username.

### 3b. Restart Claude Desktop

Fully quit and reopen Claude Desktop.

### 3c. Test the connection

Ask Claude:
> *"What DSM tools do you have available?"*

Claude should list tools including `dsm_catch_up`, `dsm_publish_receipt`,
`dsm_dcp_verify`, `dsm_project_context`.

### 3d. Run the Hot Swap

**In your terminal** (Step 2 already wrote entries to `~/.dsm-data`):

**In Claude Desktop**, ask:
> *"Call dsm_catch_up for project 'hotswap_v1_project' and tell me what happened."*

Claude should see the decisions written by Zcode and LM Studio — **without
you copy/pasting anything**.

Then ask:
> *"Publish your own decision to this project using dsm_publish_receipt."*

Claude writes a new entry to DSM.

**Verify the full chain:**
> *"Call dsm_dcp_verify for project 'hotswap_v1_project'."*

Should return: `status: OK`.

---

## What you have proven

| Claim | How you proved it |
|-------|-------------------|
| The project survives tool swaps | Claude read what Zcode + LM Studio wrote |
| No copy/paste needed | All context came from DSM |
| Memory is verifiable | `dsm_dcp_verify` returned OK |
| Any tool can participate | A cloud assistant, a script, and a local LLM shared memory |

---

## Troubleshooting

### Claude Desktop doesn't see DSM tools
- Check that `claude_desktop_config.json` has valid JSON (no trailing commas)
- Check that the Python path exists (`which python` inside your venv)
- Check that `PYTHONPATH` includes both `src/` and `packages/dsm-primitives/src`
- Restart Claude Desktop fully (not just reload)

### LM Studio times out
- Make sure a model is loaded in LM Studio (not just running)
- Try a smaller model (e.g. `nvidia/nemotron-3-nano-omni`)
- Increase the timeout in the script

### `dsm_catch_up` returns 0 decisions
- Make sure `DSM_DATA_DIR` points to the same directory for both the script
  and Claude Desktop
- Default: `~/.dsm-data`

---

## The DCP Primitives

Claude (or any tool) uses these 5 operations to participate in continuity:

| Tool | When | What it does |
|------|------|-------------|
| `dsm_join_project` | On arrival | Identify + get initial context |
| `dsm_catch_up` | Before work | Recover full project state |
| `dsm_publish_receipt` | After work | Write decision + portable proof |
| `dsm_dcp_verify` | Anytime | Check project integrity |
| `dsm_project_context` | On demand | Get prompt-ready provenance |

These 5 operations are the **DSM Continuity Protocol (DCP v1.1)**. Any
tool that implements them can participate in project continuity.

---

## Next steps

- Read the [DCP specification](../docs/architecture/DSM_CONTINUITY_PROTOCOL_v1.md)
- Read the [Platform Doctrine (ADR-0000)](../docs/architecture/ADR-0000-daryl-platform-doctrine.md)
- Build your own Continuity Provider (implement the 5 primitives, run the
  conformance suite)
