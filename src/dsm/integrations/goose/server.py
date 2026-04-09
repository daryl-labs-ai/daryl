#!/usr/bin/env python3
"""
DSM MCP Server — Provable memory for Goose AI agent.

Exposes Daryl Sharding Memory (DSM) as MCP tools that Goose can invoke
to log actions, recall context, and verify memory integrity.

Usage:
    uvx --from dsm-mcp dsm.mcp_server:main

Goose configuration:
    extensions:
        dsm-memory:
            type: stdio
            cmd: uvx
            args: ["--from", "dsm-mcp", "dsm.mcp_server:main"]
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData, INTERNAL_ERROR, INVALID_PARAMS

logger = logging.getLogger("dsm-mcp")

# Create FastMCP server
mcp = FastMCP(
    "dsm-memory",
    instructions=(
        "DSM (Daryl Sharding Memory) — provable, hash-chained memory for Goose. "
        "Use dsm_start_session at the beginning of a session and dsm_end_session "
        "at the end. Log every significant action with dsm_log_action / dsm_confirm_action. "
        "When you need past context, use dsm_recall with a token budget instead of "
        "relying on the conversation history. Use dsm_verify periodically to ensure "
        "memory integrity."
    ),
)

# Global agent state (singleton per MCP server process)
_agent = None
_data_dir: Optional[str] = None


def _get_data_dir() -> str:
    """Return DSM data directory from env or default."""
    global _data_dir
    if _data_dir is None:
        _data_dir = os.environ.get("DSM_DATA_DIR", os.path.expanduser("~/.dsm-data"))
    return _data_dir


def _get_agent():
    """Lazy-init DarylAgent singleton."""
    global _agent
    if _agent is None:
        from dsm.agent import DarylAgent

        _agent = DarylAgent(
            agent_id="goose",
            data_dir=_get_data_dir(),
            startup_verify="reconcile",
        )
        logger.info("DSM agent initialized (data_dir=%s)", _get_data_dir())
    return _agent


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def dsm_start_session(session_label: str = "") -> str:
    """Start a new DSM session. Call this at the beginning of every Goose session.

    Args:
        session_label: Optional human-readable label for this session
                       (e.g. "refactor-auth-module", "debug-payment-flow").
    """
    agent = _get_agent()
    result = agent.start()
    if session_label:
        agent.snapshot({"label": session_label, "started_at": datetime.now(timezone.utc).isoformat()})
    status = "started" if result else "already_active"
    return json.dumps({
        "status": status,
        "agent_id": agent.agent_id,
        "session_label": session_label,
        "data_dir": _get_data_dir(),
    })


@mcp.tool()
def dsm_end_session() -> str:
    """End the current DSM session. Triggers auto-sync and digest rolling.
    Call this at the end of a Goose session or before compaction would occur."""
    agent = _get_agent()
    # Roll digests for any pending time windows
    try:
        digests = agent.roll_digests()
        digest_info = [f"{d.digest_id} ({d.source_count} entries)" for d in digests]
    except Exception as e:
        logger.debug("Digest roll skipped: %s", e)
        digest_info = []

    result = agent.end(sync=True)
    return json.dumps({
        "status": "ended" if result else "no_active_session",
        "digests_rolled": digest_info,
    })


@mcp.tool()
def dsm_log_action(
    action_name: str,
    description: str = "",
    params: str = "{}",
) -> str:
    """Log an action INTENT before executing it. This creates a hash-chained entry.

    Use this BEFORE performing any significant action (tool call, code change,
    command execution, etc.). Pair with dsm_confirm_action after completion.

    Args:
        action_name:    Name of the action (e.g. "shell_command", "file_edit", "api_call")
        description:    Human-readable description of what you're about to do
        params:         JSON string of the action parameters
    """
    agent = _get_agent()
    try:
        params_dict = json.loads(params) if isinstance(params, str) else params
    except json.JSONDecodeError:
        params_dict = {"raw": params}

    intent_id = agent.intend(action_name, params_dict)
    if intent_id is None:
        raise McpError(ErrorData(code=INTERNAL_ERROR, message="Failed to log action intent"))

    return json.dumps({
        "intent_id": intent_id,
        "action_name": action_name,
        "description": description,
        "status": "logged",
    })


@mcp.tool()
def dsm_confirm_action(
    intent_id: str,
    result: str = "{}",
    success: bool = True,
) -> str:
    """Confirm a previously logged action with its result. Call AFTER execution.

    Args:
        intent_id: The intent_id returned by dsm_log_action
        result:    JSON string of the action result or output
        success:   Whether the action succeeded
    """
    agent = _get_agent()
    try:
        result_dict = json.loads(result) if isinstance(result, str) else result
    except json.JSONDecodeError:
        result_dict = {"raw_output": result}

    entry = agent.confirm(intent_id, result=result_dict, success=success)
    if entry is None:
        raise McpError(ErrorData(code=INTERNAL_ERROR, message="Failed to confirm action"))

    return json.dumps({
        "intent_id": intent_id,
        "entry_id": entry.id,
        "entry_hash": entry.hash,
        "success": success,
        "status": "confirmed",
    })


@mcp.tool()
def dsm_snapshot(data: str = "{}") -> str:
    """Record a state snapshot. Use for checkpoints, decisions, or context saves.

    Args:
        data: JSON string of the snapshot data (decisions, state, context, etc.)
    """
    agent = _get_agent()
    try:
        data_dict = json.loads(data) if isinstance(data, str) else data
    except json.JSONDecodeError:
        data_dict = {"raw": data}

    result = agent.snapshot(data_dict)
    if result is None:
        raise McpError(ErrorData(code=INTERNAL_ERROR, message="Failed to record snapshot"))

    return json.dumps({
        "entry_id": result.id,
        "entry_hash": result.hash,
        "status": "snapshotted",
    })


@mcp.tool()
def dsm_recall(
    max_tokens: int = 8000,
    hours_back: float = 24.0,
) -> str:
    """Budget-aware context recall. Returns the best combination of recent
    entries and temporal digests within a token budget. THIS IS THE KEY TOOL
    for replacing auto-compaction — instead of losing context, recall it
    verifiably from DSM.

    The response includes:
      - recent_entries: Full recent entries (Tier 2, ~300 tokens each)
      - hourly_digests: Aggregated hourly summaries (~80 tokens each)
      - daily_digests:  Aggregated daily summaries (~80 tokens each)
      - weekly_digests: Aggregated weekly summaries (~80 tokens each)
      - total_tokens:   Actual tokens used
      - coverage:       Time span covered (e.g. "last_5_hours")

    Args:
        max_tokens:  Maximum tokens to use for context (default 8000)
        hours_back:  How far back to look for recent entries (default 24h)
    """
    agent = _get_agent()
    from datetime import timedelta
    since = datetime.now(timezone.utc) - timedelta(hours=hours_back)

    try:
        context = agent.read_with_digests(since=since, max_tokens=max_tokens)
    except Exception as e:
        # Fallback: if collective/digester not set up, use basic read
        logger.debug("read_with_digests failed, falling back to basic read: %s", e)
        from dsm.rr.relay import DSMReadRelay
        relay = DSMReadRelay(data_dir=_get_data_dir())
        recent = relay.read_recent("sessions", limit=max(1, max_tokens // 300))
        return json.dumps({
            "recent_entries": [
                {
                    "hash": e.hash,
                    "agent_id": e.source,
                    "timestamp": e.timestamp.isoformat(),
                    "content": e.content[:500],
                    "action_type": (e.metadata or {}).get("action_name", ""),
                }
                for e in recent
            ],
            "hourly_digests": [],
            "daily_digests": [],
            "weekly_digests": [],
            "total_tokens": len(recent) * 300,
            "coverage": "basic_fallback",
        })

    return json.dumps({
        "recent_entries": [
            {
                "hash": e.hash,
                "agent_id": e.agent_id,
                "timestamp": e.contributed_at.isoformat(),
                "summary": e.summary,
                "action_type": e.action_type,
                "detail": e.detail[:500] if e.detail else "",
                "key_findings": list(e.key_findings),
            }
            for e in context.recent
        ],
        "hourly_digests": [
            {
                "digest_id": d.digest_id,
                "level": d.level,
                "time_range": f"{d.start_time.isoformat()} → {d.end_time.isoformat()}",
                "source_count": d.source_count,
                "key_events": list(d.key_events[:10]),
                "agents_involved": list(d.agents_involved),
                "success_rate": d.metrics.get("success_rate", 0),
            }
            for d in context.hourly_digests
        ],
        "daily_digests": [
            {
                "digest_id": d.digest_id,
                "level": d.level,
                "time_range": f"{d.start_time.isoformat()} → {d.end_time.isoformat()}",
                "source_count": d.source_count,
                "key_events": list(d.key_events[:10]),
                "agents_involved": list(d.agents_involved),
                "success_rate": d.metrics.get("success_rate", 0),
            }
            for d in context.daily_digests
        ],
        "weekly_digests": [
            {
                "digest_id": d.digest_id,
                "level": d.level,
                "time_range": f"{d.start_time.isoformat()} → {d.end_time.isoformat()}",
                "source_count": d.source_count,
                "key_events": list(d.key_events[:10]),
                "agents_involved": list(d.agents_involved),
                "success_rate": d.metrics.get("success_rate", 0),
            }
            for d in context.weekly_digests
        ],
        "total_tokens": context.total_tokens,
        "coverage": context.coverage,
    })


@mcp.tool()
def dsm_recent(limit: int = 20) -> str:
    """Get the last N entries from the sessions shard. Returns raw entries
    with full content and metadata.

    Args:
        limit: Number of entries to return (default 20)
    """
    from dsm.rr.relay import DSMReadRelay

    relay = DSMReadRelay(data_dir=_get_data_dir())
    entries = relay.read_recent("sessions", limit=limit)

    return json.dumps([
        {
            "id": e.id,
            "hash": e.hash,
            "prev_hash": e.prev_hash,
            "timestamp": e.timestamp.isoformat(),
            "session_id": e.session_id,
            "source": e.source,
            "content": e.content[:1000],
            "event_type": (e.metadata or {}).get("event_type", ""),
            "action_name": (e.metadata or {}).get("action_name", ""),
        }
        for e in entries
    ])


@mcp.tool()
def dsm_summary() -> str:
    """Get a lightweight activity summary: entry count, unique sessions,
    errors, and top actions performed."""
    from dsm.rr.relay import DSMReadRelay

    relay = DSMReadRelay(data_dir=_get_data_dir())
    summary = relay.summary("sessions", limit=500)

    return json.dumps(summary)


@mcp.tool()
def dsm_verify(shard_id: str = "") -> str:
    """Verify the integrity of the DSM hash chain. Detects tampering,
    corruption, or chain breaks. Use periodically to ensure memory integrity.

    Args:
        shard_id: Specific shard to verify. Empty string = verify all shards.
    """
    agent = _get_agent()
    if shard_id:
        result = agent.verify(shard_id=shard_id)
    else:
        result = agent.verify()

    # Handle different return formats
    if isinstance(result, list):
        return json.dumps(result)
    elif isinstance(result, dict):
        return json.dumps(result)
    else:
        return json.dumps({"status": "verified", "raw": str(result)})


@mcp.tool()
def dsm_search(
    action_name: str = "",
    hours_back: float = 168.0,
    limit: int = 50,
) -> str:
    """Query actions across sessions. Find specific actions or recent activity.

    Args:
        action_name: Filter by action name (e.g. "shell_command", "file_edit").
                     Empty string = all actions.
        hours_back:  How far back to search (default 168h = 1 week)
        limit:       Maximum results (default 50)
    """
    agent = _get_agent()
    from datetime import timedelta
    start_time = (datetime.now(timezone.utc) - timedelta(hours=hours_back)).isoformat()

    results = agent.query_actions(
        action_name=action_name or None,
        start_time=start_time,
        limit=limit,
    )

    return json.dumps(results)


@mcp.tool()
def dsm_status() -> str:
    """Show DSM data directory, shards, entry counts, and integrity status."""
    agent = _get_agent()
    storage = agent.storage
    shards = storage.list_shards()
    total = sum(s.entry_count for s in shards)

    return json.dumps({
        "data_dir": _get_data_dir(),
        "agent_id": agent.agent_id,
        "shards": [
            {
                "shard_id": s.shard_id,
                "entry_count": s.entry_count,
                "created_at": s.created_at.isoformat() if hasattr(s, "created_at") else None,
                "last_updated": s.last_updated.isoformat() if s.last_updated else None,
                "integrity": s.integrity_status,
            }
            for s in shards
        ],
        "total_entries": total,
    })


# ---------------------------------------------------------------------------
# MCP Resources
# ---------------------------------------------------------------------------

@mcp.resource("dsm://status")
def resource_status() -> str:
    """Current DSM status as a JSON resource."""
    return dsm_status()


@mcp.resource("dsm://summary")
def resource_summary() -> str:
    """Current DSM session summary as a JSON resource."""
    return dsm_summary()


@mcp.resource("dsm://config")
def resource_config() -> str:
    """Current DSM configuration."""
    return json.dumps({
        "data_dir": _get_data_dir(),
        "agent_id": "goose",
        "version": "1.0.0",
    })


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    """Run the DSM MCP server."""
    import argparse

    parser = argparse.ArgumentParser(description="DSM Memory MCP Server for Goose")
    parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    mcp.run()


if __name__ == "__main__":
    main()
