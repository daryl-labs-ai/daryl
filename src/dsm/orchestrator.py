"""
Neutral Orchestrator — admission control for the collective.

Decides whether an entry can enter the collective based on frozen rules.
Logs every decision to `orchestrator_audit` shard (delta only, never full entries).

Design:
- Decides on hashes, never on full entries (lightweight)
- Rules are frozen at init; with_rules() returns a new instance
- Each rule is a pure function: (entry, agent, context) -> RuleResult
- Decision cache by entry hash (same entry never evaluated twice)
- Depends on A (identity) and B (sovereignty)
"""

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .core.models import Entry
from .core.storage import Storage
from .identity.identity_registry import IdentityRegistry
from .sovereignty import SovereigntyPolicy, EnforcementResult

logger = logging.getLogger(__name__)

ORCHESTRATOR_SHARD = "orchestrator_audit"


# ------------------------------------------------------------------
# Context & Results
# ------------------------------------------------------------------


@dataclass(frozen=True)
class AdmissionContext:
    """Pre-computed context passed to rules. Rules never do I/O."""
    agent_trust: float
    sovereignty_result: EnforcementResult
    recent_admissions: int      # count of recent admissions for rate limiting
    chain_tip_hash: Optional[str]  # last hash in target collective shard


@dataclass(frozen=True)
class RuleResult:
    """Result of a single rule evaluation."""
    passed: bool
    rule_name: str
    reason: Optional[str] = None


@dataclass(frozen=True)
class AdmissionResult:
    """Final admission decision."""
    verdict: str         # "allow" | "deny" | "pending"
    reason: str
    entry_hash: str      # reference to evaluated entry
    agent_id: str
    decided_at: datetime
    rule_results: tuple = ()  # individual rule results

    @property
    def allowed(self) -> bool:
        return self.verdict == "allow"


# ------------------------------------------------------------------
# Rule base + concrete rules
# ------------------------------------------------------------------


class Rule(ABC):
    """Base class for admission rules. Pure function."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def evaluate(self, entry: Entry, agent_id: str, context: AdmissionContext) -> RuleResult: ...


class SovereigntyCheckRule(Rule):
    """Check that sovereignty policy allows this agent + entry type."""

    @property
    def name(self) -> str:
        return "sovereignty_check"

    def evaluate(self, entry: Entry, agent_id: str, context: AdmissionContext) -> RuleResult:
        if context.sovereignty_result.allowed:
            return RuleResult(passed=True, rule_name=self.name)
        return RuleResult(
            passed=False,
            rule_name=self.name,
            reason=f"sovereignty: {context.sovereignty_result.reason}",
        )


class MinTrustScoreRule(Rule):
    """Check agent trust score meets a minimum threshold."""

    def __init__(self, min_score: float = 0.3):
        self._min_score = min_score

    @property
    def name(self) -> str:
        return "min_trust_score"

    def evaluate(self, entry: Entry, agent_id: str, context: AdmissionContext) -> RuleResult:
        if context.agent_trust >= self._min_score:
            return RuleResult(passed=True, rule_name=self.name)
        return RuleResult(
            passed=False,
            rule_name=self.name,
            reason=f"trust {context.agent_trust:.2f} < {self._min_score:.2f}",
        )


class RateLimitRule(Rule):
    """Check that agent hasn't exceeded admission rate limit."""

    def __init__(self, max_per_window: int = 100):
        self._max = max_per_window

    @property
    def name(self) -> str:
        return "rate_limit"

    def evaluate(self, entry: Entry, agent_id: str, context: AdmissionContext) -> RuleResult:
        if context.recent_admissions < self._max:
            return RuleResult(passed=True, rule_name=self.name)
        return RuleResult(
            passed=False,
            rule_name=self.name,
            reason=f"rate limit: {context.recent_admissions} >= {self._max}",
        )


class NoSelfReferenceRule(Rule):
    """Prevent an entry from referencing itself."""

    @property
    def name(self) -> str:
        return "no_self_reference"

    def evaluate(self, entry: Entry, agent_id: str, context: AdmissionContext) -> RuleResult:
        if entry.prev_hash and entry.hash and entry.prev_hash == entry.hash:
            return RuleResult(
                passed=False,
                rule_name=self.name,
                reason="entry references itself",
            )
        return RuleResult(passed=True, rule_name=self.name)


# ------------------------------------------------------------------
# RuleSet — frozen collection of rules
# ------------------------------------------------------------------


class RuleSet:
    """Immutable collection of admission rules."""

    def __init__(self, rules: List[Rule]):
        self._rules = tuple(rules)

    @property
    def rules(self) -> tuple:
        return self._rules

    def __len__(self) -> int:
        return len(self._rules)

    @classmethod
    def default(cls) -> "RuleSet":
        return cls([
            SovereigntyCheckRule(),
            MinTrustScoreRule(0.3),
            RateLimitRule(100),
            NoSelfReferenceRule(),
        ])

    @classmethod
    def permissive(cls) -> "RuleSet":
        """Minimal rules for testing."""
        return cls([NoSelfReferenceRule()])


# ------------------------------------------------------------------
# NeutralOrchestrator
# ------------------------------------------------------------------


class NeutralOrchestrator:
    """Neutral admission orchestrator for the collective.

    Evaluates rules, logs decisions, caches results by entry hash.
    """

    def __init__(
        self,
        storage: Storage,
        rules: RuleSet,
        identity: IdentityRegistry,
        policy: SovereigntyPolicy,
    ):
        self._storage = storage
        self._rules = rules
        self._identity = identity
        self._policy = policy
        # Decision cache: entry_hash -> AdmissionResult
        self._cache: Dict[str, AdmissionResult] = {}
        # In-memory admission counter: agent_id -> count (reset on new instance)
        self._admission_counts: Dict[str, int] = {}

    @property
    def rules(self) -> RuleSet:
        return self._rules

    def with_rules(self, rules: RuleSet) -> "NeutralOrchestrator":
        """Return a new orchestrator with different rules (immutable pattern)."""
        return NeutralOrchestrator(
            storage=self._storage,
            rules=rules,
            identity=self._identity,
            policy=self._policy,
        )

    def _build_context(
        self, agent_id: str, owner_id: str, entry_type: str,
    ) -> AdmissionContext:
        """Pre-compute context for rules. Rules never do I/O.

        Uses in-memory admission counter instead of scanning the audit shard.
        Counter is incremented on each successful admission in admit().
        O(1) — no shard read, no JSON parsing.
        """
        trust = self._identity.trust_score(agent_id)
        sov_result = self._policy.allows(owner_id, agent_id, entry_type, self._identity)

        # O(1) — in-memory counter, no shard scan
        recent = self._admission_counts.get(agent_id, 0)

        return AdmissionContext(
            agent_trust=trust,
            sovereignty_result=sov_result,
            recent_admissions=recent,
            chain_tip_hash=None,
        )

    def admit(
        self, entry: Entry, agent_id: str, owner_id: str,
    ) -> AdmissionResult:
        """Evaluate admission for an entry. Returns result, never raises.

        Decisions are cached by entry hash and logged to orchestrator_audit.
        """
        entry_hash = entry.hash or ""

        # Cache hit
        if entry_hash and entry_hash in self._cache:
            return self._cache[entry_hash]

        now = datetime.now(timezone.utc)
        entry_type = (entry.metadata or {}).get("event_type", "unknown")
        context = self._build_context(agent_id, owner_id, entry_type)

        # Evaluate all rules, short-circuit on first failure
        rule_results = []
        verdict = "allow"
        reason = "all rules passed"

        for rule in self._rules.rules:
            rr = rule.evaluate(entry, agent_id, context)
            rule_results.append(rr)
            if not rr.passed:
                verdict = "deny"
                reason = rr.reason or rr.rule_name
                break

        # Check for pending (sovereignty said pending)
        if verdict == "allow" and context.sovereignty_result.verdict == "pending":
            verdict = "pending"
            reason = context.sovereignty_result.reason or "approval required"

        result = AdmissionResult(
            verdict=verdict,
            reason=reason,
            entry_hash=entry_hash,
            agent_id=agent_id,
            decided_at=now,
            rule_results=tuple(rule_results),
        )

        # Log to audit shard (delta only — verdict + reason + hash, never full entry)
        self._log_decision(result)

        # Update in-memory admission counter (O(1) — no shard re-scan)
        if result.allowed:
            self._admission_counts[agent_id] = (
                self._admission_counts.get(agent_id, 0) + 1
            )

        # Cache
        if entry_hash:
            self._cache[entry_hash] = result

        return result

    def _log_decision(self, result: AdmissionResult) -> None:
        """Append decision to orchestrator_audit shard (delta only)."""
        content = json.dumps({
            "verdict": result.verdict,
            "reason": result.reason,
            "entry_hash": result.entry_hash,
            "agent_id": result.agent_id,
            "decided_at": result.decided_at.isoformat(),
        }, sort_keys=True, separators=(",", ":"))

        audit_entry = Entry(
            id=str(uuid4()),
            timestamp=result.decided_at,
            session_id="orchestrator",
            source="orchestrator",
            content=content,
            shard=ORCHESTRATOR_SHARD,
            hash="",
            prev_hash=None,
            metadata={
                "event_type": "admission_decision",
                "verdict": result.verdict,
                "agent_id": result.agent_id,
            },
            version="v2.0",
        )
        try:
            self._storage.append(audit_entry)
        except OSError as e:
            logger.error("Failed to log orchestrator decision: %s", e)
