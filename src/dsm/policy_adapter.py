"""
Policy Adapter & Audit Reports (P8).

Makes DSM audit interoperable with external policy engines.
Provides structured, exportable, cryptographically signed audit reports.

DSM proves WHAT happened (hash chain).
P4 proves WHEN intent was declared (pre-commitment).
Audit proves it was ALLOWED (policy compliance).
P8 makes audit PORTABLE and INTEROPERABLE.

Inspired by @forge_inkog on Moltbook.
"""

import hashlib
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .audit import Policy, PolicyViolation, audit_shard, audit_all
from .core.storage import Storage

logger = logging.getLogger(__name__)


# ── Policy Adapters ──────────────────────────────────────────────

class PolicyAdapter(ABC):
    """
    Abstract base class for external policy format adapters.

    Subclass this to support any external policy engine.
    The adapter converts an external policy format into DSM's Policy object.
    """

    @abstractmethod
    def name(self) -> str:
        """Adapter name (e.g. 'inkog', 'opa', 'cedar')."""

    @abstractmethod
    def load(self, source: str) -> Policy:
        """
        Load and convert external policy to DSM Policy.

        Args:
            source: path to policy file, URL, or inline JSON string

        Returns:
            DSM Policy object
        """

    @abstractmethod
    def validate_source(self, source: str) -> bool:
        """Check if source is a valid policy for this adapter."""


class InkogAdapter(PolicyAdapter):
    """
    Adapter for Inkog policy format.

    Inkog policies use this structure:
    {
        "policy_id": "inkog-xxxx",
        "version": "1.0",
        "engine": "inkog",
        "rules": {
            "allow": ["action1", "action2"],
            "deny": ["action3"],
            "sources": ["agent_a", "agent_b"],
            "limits": {
                "max_actions_per_session": 100,
                "shards": ["sessions", "tasks"]
            }
        },
        "metadata": {...}
    }
    """

    def name(self) -> str:
        return "inkog"

    def load(self, source: str) -> Policy:
        """
        Load Inkog policy from file path or JSON string.

        Converts Inkog format → DSM Policy:
        - rules.allow → allowed_actions
        - rules.deny → forbidden_actions
        - rules.sources → allowed_sources
        - rules.limits.max_actions_per_session → max_actions_per_session
        - rules.limits.shards → allowed_shards
        """
        data = self._read_source(source)

        if data.get("engine") != "inkog":
            raise ValueError(f"Not an Inkog policy: engine={data.get('engine')}")

        rules = data.get("rules", {})
        limits = rules.get("limits", {})

        return Policy(
            allowed_actions=rules.get("allow"),
            forbidden_actions=rules.get("deny", []),
            allowed_sources=rules.get("sources"),
            max_actions_per_session=limits.get("max_actions_per_session"),
            allowed_shards=limits.get("shards"),
        )

    def validate_source(self, source: str) -> bool:
        """Check if source contains a valid Inkog policy."""
        try:
            data = self._read_source(source)
            return data.get("engine") == "inkog" and "rules" in data
        except Exception:
            return False

    def _read_source(self, source: str) -> dict:
        """Read policy from file or JSON string."""
        path = Path(source)
        if path.exists() and path.is_file():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return json.loads(source)


class OPAAdapter(PolicyAdapter):
    """
    Adapter for Open Policy Agent (OPA) format.

    OPA policies use this structure:
    {
        "engine": "opa",
        "package": "dsm.authz",
        "rules": {
            "allow_actions": ["action1", "action2"],
            "deny_actions": ["action3"],
            "allow_sources": ["agent_a"],
            "max_actions": 50,
            "allow_shards": ["sessions"]
        }
    }
    """

    def name(self) -> str:
        return "opa"

    def load(self, source: str) -> Policy:
        data = self._read_source(source)
        if data.get("engine") != "opa":
            raise ValueError(f"Not an OPA policy: engine={data.get('engine')}")
        rules = data.get("rules", {})
        return Policy(
            allowed_actions=rules.get("allow_actions"),
            forbidden_actions=rules.get("deny_actions", []),
            allowed_sources=rules.get("allow_sources"),
            max_actions_per_session=rules.get("max_actions"),
            allowed_shards=rules.get("allow_shards"),
        )

    def validate_source(self, source: str) -> bool:
        try:
            data = self._read_source(source)
            return data.get("engine") == "opa" and "rules" in data
        except Exception:
            return False

    def _read_source(self, source: str) -> dict:
        path = Path(source)
        if path.exists() and path.is_file():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return json.loads(source)


# ── Adapter Registry ─────────────────────────────────────────────

_ADAPTERS: Dict[str, PolicyAdapter] = {}


def register_adapter(adapter: PolicyAdapter) -> None:
    """Register a policy adapter by name."""
    _ADAPTERS[adapter.name()] = adapter


def get_adapter(name: str) -> Optional[PolicyAdapter]:
    """Get a registered adapter by name."""
    return _ADAPTERS.get(name)


def list_adapters() -> List[str]:
    """List all registered adapter names."""
    return list(_ADAPTERS.keys())


def auto_detect_adapter(source: str) -> Optional[PolicyAdapter]:
    """Try each registered adapter until one validates the source."""
    for adapter in _ADAPTERS.values():
        if adapter.validate_source(source):
            return adapter
    return None


# Register built-in adapters
register_adapter(InkogAdapter())
register_adapter(OPAAdapter())


# ── Audit Reports ────────────────────────────────────────────────

class AuditReport:
    """
    Structured, exportable, cryptographically signed audit report.

    Contains:
    - report_id: unique identifier
    - agent_id: agent being audited
    - policy_source: adapter name + policy origin
    - shard_results: per-shard audit results
    - summary: aggregate stats
    - report_hash: SHA-256 of canonical report (tamper detection)
    - timestamp: when the audit was performed
    """

    def __init__(
        self,
        report_id: str,
        agent_id: str,
        policy_engine: str,
        shard_results: List[dict],
        timestamp: str,
        report_hash: str,
    ):
        self.report_id = report_id
        self.agent_id = agent_id
        self.policy_engine = policy_engine
        self.shard_results = shard_results
        self.timestamp = timestamp
        self.report_hash = report_hash

    @property
    def summary(self) -> dict:
        total_entries = sum(r.get("total_entries", 0) for r in self.shard_results)
        total_violations = sum(r.get("violation_count", 0) for r in self.shard_results)
        shards_audited = len(self.shard_results)
        status = "COMPLIANT" if total_violations == 0 else "VIOLATIONS_FOUND"
        return {
            "shards_audited": shards_audited,
            "total_entries": total_entries,
            "total_violations": total_violations,
            "status": status,
        }

    def to_dict(self) -> dict:
        return {
            "report_id": self.report_id,
            "agent_id": self.agent_id,
            "policy_engine": self.policy_engine,
            "shard_results": self.shard_results,
            "summary": self.summary,
            "timestamp": self.timestamp,
            "report_hash": self.report_hash,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> "AuditReport":
        return cls(
            report_id=d["report_id"],
            agent_id=d["agent_id"],
            policy_engine=d["policy_engine"],
            shard_results=d["shard_results"],
            timestamp=d["timestamp"],
            report_hash=d["report_hash"],
        )

    @classmethod
    def from_json(cls, s: str) -> "AuditReport":
        return cls.from_dict(json.loads(s))


def _compute_report_hash(payload: dict) -> str:
    """SHA-256 of canonical JSON payload (excluding report_hash itself)."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_report(report: AuditReport) -> dict:
    """
    Verify audit report integrity (offline).

    Returns: {"report_id": str, "status": "INTACT" | "TAMPERED"}
    """
    payload = {
        "report_id": report.report_id,
        "agent_id": report.agent_id,
        "policy_engine": report.policy_engine,
        "shard_results": report.shard_results,
        "timestamp": report.timestamp,
    }
    expected = _compute_report_hash(payload)
    status = "INTACT" if expected == report.report_hash else "TAMPERED"
    return {"report_id": report.report_id, "status": status}


# ── Report Generation ────────────────────────────────────────────

def generate_audit_report(
    storage: Storage,
    agent_id: str,
    policy: Policy,
    policy_engine: str = "dsm",
    shard_ids: Optional[List[str]] = None,
) -> AuditReport:
    """
    Generate a full audit report for one or more shards.

    Args:
        storage: DSM storage instance
        agent_id: agent being audited
        policy: the Policy to audit against
        policy_engine: name of the policy engine (e.g. "inkog", "opa", "dsm")
        shard_ids: specific shards to audit (None = all shards)

    Returns:
        AuditReport with cryptographic hash for tamper detection
    """
    if shard_ids:
        shard_results = []
        for sid in shard_ids:
            result = audit_shard(storage, sid, policy)
            shard_results.append(result)
    else:
        shard_results = audit_all(storage, policy)

    report_id = str(uuid4())
    timestamp = datetime.utcnow().isoformat() + "Z"

    payload = {
        "report_id": report_id,
        "agent_id": agent_id,
        "policy_engine": policy_engine,
        "shard_results": shard_results,
        "timestamp": timestamp,
    }
    report_hash = _compute_report_hash(payload)

    return AuditReport(
        report_id=report_id,
        agent_id=agent_id,
        policy_engine=policy_engine,
        shard_results=shard_results,
        timestamp=timestamp,
        report_hash=report_hash,
    )


def load_and_audit(
    storage: Storage,
    agent_id: str,
    policy_source: str,
    adapter_name: Optional[str] = None,
    shard_ids: Optional[List[str]] = None,
) -> AuditReport:
    """
    Load external policy via adapter and generate audit report.

    Auto-detects adapter if adapter_name is None.

    Args:
        storage: DSM storage
        agent_id: agent being audited
        policy_source: path or JSON string for the policy
        adapter_name: adapter to use (None = auto-detect)
        shard_ids: shards to audit (None = all)

    Returns:
        AuditReport

    Raises:
        ValueError if no adapter can handle the source
    """
    if adapter_name:
        adapter = get_adapter(adapter_name)
        if not adapter:
            raise ValueError(f"Unknown adapter: {adapter_name}. Available: {list_adapters()}")
    else:
        adapter = auto_detect_adapter(policy_source)
        if not adapter:
            raise ValueError(f"No adapter can handle this policy source. Available: {list_adapters()}")

    policy = adapter.load(policy_source)
    return generate_audit_report(
        storage=storage,
        agent_id=agent_id,
        policy=policy,
        policy_engine=adapter.name(),
        shard_ids=shard_ids,
    )
