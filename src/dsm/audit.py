"""
Policy Audit for DSM.

Verifies that every action recorded in a shard was authorized
by a policy. DSM proves WHAT happened. The audit proves it was ALLOWED.

A policy defines:
- allowed_actions: list of action names the agent may execute
- forbidden_actions: list of action names explicitly denied (takes precedence)
- allowed_sources: list of valid session sources
- max_actions_per_session: maximum number of actions in a single session
- allowed_shards: list of shards the agent may write to

The audit reads entries from a shard and checks each one against
the policy. Violations are collected and returned.

Inspired by feedback from @forge_inkog on Moltbook.
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class PolicyViolation:
    """A single policy violation found during audit."""

    def __init__(
        self,
        entry_id: str,
        timestamp: str,
        rule: str,
        detail: str,
        action_name: Optional[str] = None,
        session_id: Optional[str] = None,
    ):
        self.entry_id = entry_id
        self.timestamp = timestamp
        self.rule = rule
        self.detail = detail
        self.action_name = action_name
        self.session_id = session_id

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "timestamp": self.timestamp,
            "rule": self.rule,
            "detail": self.detail,
            "action_name": self.action_name,
            "session_id": self.session_id,
        }


class Policy:
    """
    Defines what an agent is allowed to do.

    Can be loaded from a JSON file or constructed in code.
    """

    def __init__(
        self,
        allowed_actions: Optional[list] = None,
        forbidden_actions: Optional[list] = None,
        allowed_sources: Optional[list] = None,
        max_actions_per_session: Optional[int] = None,
        allowed_shards: Optional[list] = None,
    ):
        self.allowed_actions = allowed_actions  # None = all allowed
        self.forbidden_actions = forbidden_actions or []
        self.allowed_sources = allowed_sources  # None = all allowed
        self.max_actions_per_session = max_actions_per_session  # None = unlimited
        self.allowed_shards = allowed_shards  # None = all allowed

    @classmethod
    def from_file(cls, path: str) -> "Policy":
        """Load policy from a JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(
            allowed_actions=data.get("allowed_actions"),
            forbidden_actions=data.get("forbidden_actions", []),
            allowed_sources=data.get("allowed_sources"),
            max_actions_per_session=data.get("max_actions_per_session"),
            allowed_shards=data.get("allowed_shards"),
        )

    def to_dict(self) -> dict:
        return {
            "allowed_actions": self.allowed_actions,
            "forbidden_actions": self.forbidden_actions,
            "allowed_sources": self.allowed_sources,
            "max_actions_per_session": self.max_actions_per_session,
            "allowed_shards": self.allowed_shards,
        }


def audit_shard(storage, shard_id: str, policy: Policy) -> dict:
    """
    Audit a shard against a policy.

    Reads all entries from the shard and checks each one against the policy rules.

    Returns:
        {
            "shard_id": str,
            "total_entries": int,
            "actions_checked": int,
            "violations": [PolicyViolation.to_dict(), ...],
            "violation_count": int,
            "sessions_checked": int,
            "status": "COMPLIANT" | "VIOLATIONS_FOUND"
        }
    """
    entries = storage.read(shard_id, limit=100000)
    entries = list(reversed(entries))  # chronological order

    violations = []
    actions_checked = 0
    session_action_counts = {}
    sessions_seen = set()

    for entry in entries:
        event_type = entry.metadata.get("event_type", "")
        action_name = entry.metadata.get("action_name", "")
        session_id = entry.session_id
        timestamp = (
            entry.timestamp.isoformat()
            if hasattr(entry.timestamp, "isoformat")
            else str(entry.timestamp)
        )

        sessions_seen.add(session_id)

        # Check shard is allowed
        if policy.allowed_shards is not None:
            if entry.shard not in policy.allowed_shards:
                violations.append(
                    PolicyViolation(
                        entry_id=entry.id,
                        timestamp=timestamp,
                        rule="allowed_shards",
                        detail=f"Shard '{entry.shard}' not in allowed list: {policy.allowed_shards}",
                        session_id=session_id,
                    )
                )

        # Check source is allowed (on session_start events)
        if event_type == "session_start":
            source = entry.metadata.get("source") or entry.source
            if policy.allowed_sources is not None:
                if source not in policy.allowed_sources:
                    violations.append(
                        PolicyViolation(
                            entry_id=entry.id,
                            timestamp=timestamp,
                            rule="allowed_sources",
                            detail=f"Source '{source}' not in allowed list: {policy.allowed_sources}",
                            session_id=session_id,
                        )
                    )

        # Check action permissions (on action_intent events)
        if event_type == "action_intent" and action_name:
            actions_checked += 1

            session_action_counts[session_id] = (
                session_action_counts.get(session_id, 0) + 1
            )

            # Forbidden actions (takes precedence)
            if action_name in policy.forbidden_actions:
                violations.append(
                    PolicyViolation(
                        entry_id=entry.id,
                        timestamp=timestamp,
                        rule="forbidden_actions",
                        detail=f"Action '{action_name}' is explicitly forbidden",
                        action_name=action_name,
                        session_id=session_id,
                    )
                )

            # Allowed actions whitelist
            elif policy.allowed_actions is not None:
                if action_name not in policy.allowed_actions:
                    violations.append(
                        PolicyViolation(
                            entry_id=entry.id,
                            timestamp=timestamp,
                            rule="allowed_actions",
                            detail=f"Action '{action_name}' not in allowed list: {policy.allowed_actions}",
                            action_name=action_name,
                            session_id=session_id,
                        )
                    )

    # Check max_actions_per_session
    if policy.max_actions_per_session is not None:
        for sid, count in session_action_counts.items():
            if count > policy.max_actions_per_session:
                violations.append(
                    PolicyViolation(
                        entry_id="session_aggregate",
                        timestamp="",
                        rule="max_actions_per_session",
                        detail=f"Session '{sid[:12]}...' had {count} actions, max allowed is {policy.max_actions_per_session}",
                        session_id=sid,
                    )
                )

    status = "COMPLIANT" if len(violations) == 0 else "VIOLATIONS_FOUND"

    return {
        "shard_id": shard_id,
        "total_entries": len(entries),
        "actions_checked": actions_checked,
        "violations": [v.to_dict() for v in violations],
        "violation_count": len(violations),
        "sessions_checked": len(sessions_seen),
        "status": status,
    }


def audit_all(storage, policy: Policy) -> list:
    """Audit all shards against a policy."""
    results = []
    for meta in storage.list_shards():
        result = audit_shard(storage, meta.shard_id, policy)
        results.append(result)
    return results
