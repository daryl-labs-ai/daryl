# Claude Continuity Provider — Technical Plan

**Status:** Design — ready for implementation
**Scope:** Add 5 DCP v1.1 primitives to the existing MCP server
**Constraint:** No kernel change, no new logic — compose existing SDK methods

---

## DCP Primitive → SDK mapping

| DCP Primitive | SDK method(s) | Gap? |
|---------------|--------------|------|
| `join_project(project_id, agent_id)` | `DarylAgent.__init__` (already done via `_get_agent`) + `verify_shard` + `read` | **Compose** — no single method, but ingredients exist |
| `catch_up(project_id)` | `verify_shard` + `Storage.read` + `DSMReadRelay.summary` | **Compose** — already prototyped in `hot_swap_mvp.py` |
| `publish_receipt(project_id, agent_id, task, result)` | `Storage.append` + `issue_receipt` | **Thin adapter** — `DarylAgent.intend` + `confirm` + `issue_receipt` exist but are session-scoped; need a project-scoped wrapper |
| `verify(project_id)` | `DarylAgent.verify(shard_id)` | **Direct map** — exists |
| `project_context(project_id)` | `build_provenance` + `Storage.read` | **Compose** — ingredients exist |

**Verdict:** Zero kernel changes. Two compositions (`catch_up`, `join_project`), one thin adapter (`publish_receipt`), two direct maps (`verify`, `project_context`).

---

## MCP tool signatures (DCP v1.1)

```python
@mcp.tool()
def dsm_join_project(project_id: str, agent_id: str = "") -> str:
    """Join a project. Returns participation context + initial catch_up."""

@mcp.tool()
def dsm_catch_up(project_id: str) -> str:
    """Recover full project state. Returns decisions, integrity, summary."""

@mcp.tool()
def dsm_publish_receipt(project_id: str, task: str, result: str,
                        agent_id: str = "") -> str:
    """Write a decision to the project and issue a receipt."""

@mcp.tool()
def dsm_verify(project_id: str) -> str:
    """Verify project integrity."""

@mcp.tool()
def dsm_project_context(project_id: str) -> str:
    """Get a prompt-ready provenance block."""
```

---

## Implementation approach

All 5 tools live in `src/dsm/integrations/goose/server.py`, following the
exact pattern of the existing 11 tools:
1. Get the singleton `_agent` via `_get_agent()`
2. Call SDK methods on `_agent`
3. Return JSON string

For `catch_up` and `join_project`, compose:
- `verify_shard(_agent._storage, project_id)` for integrity
- `_agent._storage.read(project_id)` for decisions
- `DSMReadRelay(storage=_agent._storage).summary(project_id)` for summary

For `publish_receipt`, compose:
- Create an `Entry` with `source=agent_id`, `shard=project_id`
- `_agent._storage.append(entry)` to write
- `issue_receipt(_agent._storage, agent_id, entry.id, project_id, task)` for receipt

---

## What does NOT change

- Kernel: untouched
- DarylAgent: no new methods (compositions live in the MCP server)
- Existing 11 MCP tools: unchanged
- DCP v1.1 spec: unchanged (unless implementation reveals ambiguity)

---

## Risk

| Risk | Mitigation |
|------|-----------|
| `publish_receipt` needs to write to an arbitrary project_id shard, not the agent's default shard | `Storage.append` accepts any shard — verified in Boucle 1 |
| Claude Desktop MCP config may differ from Goose | Documented in Boucle 4; standard MCP stdio config |
| The `_agent` singleton is agent_id="goose" — project entries should attribute to the real agent | `publish_receipt` takes `agent_id` param, sets `source=agent_id` on the Entry |
