#!/usr/bin/env python3
"""Provider abstractions for Agent Proposal Gateway v0."""

from __future__ import annotations

import json
import urllib.request
from typing import Any, Protocol


class ProposalProvider(Protocol):
    metadata: dict[str, str]

    def propose(self, context: dict[str, Any]) -> dict[str, Any]:
        """Return an untrusted proposal for a DSM-composed context."""


class MockProposalProvider:
    """CI-only proposal provider with canned deterministic scenarios."""

    def __init__(self, scenario: str = "golden", *, metadata: dict[str, str] | None = None):
        self.scenario = scenario
        self.metadata = metadata or {
            "kind": "mock",
            "name": "mock",
            "model": f"mock-{scenario}",
            "base_url_label": "local-test",
        }

    def propose(self, context: dict[str, Any]) -> dict[str, Any]:
        scenarios = {
            "golden": self._golden,
            "over_promise": self._over_promise,
            "candidate_promotion": self._candidate_promotion,
            "missing_required_check": self._missing_required_check,
            "unknown_claimed_check": self._unknown_claimed_check,
            "cross_user_leak": self._cross_user_leak,
            "low_coverage": self._low_coverage,
            "agent_status": self._agent_status,
            "agent_status_over_promise": self._agent_status_over_promise,
        }
        try:
            return scenarios[self.scenario](context)
        except KeyError as exc:
            raise ValueError(f"unsupported mock scenario: {self.scenario}") from exc

    def _golden(self, context: dict[str, Any]) -> dict[str, Any]:
        claimed, limitations = _claims_and_limitations(context)
        return _proposal(
            narrative="Proposal scaffold respects DSM trust boundaries.",
            action="Prepare a reasoner review using retrieved validated rules.",
            claimed_checks=claimed,
            limitations=limitations,
        )

    def _over_promise(self, context: dict[str, Any]) -> dict[str, Any]:
        claimed, limitations = _claims_and_limitations(context)
        return _proposal(
            narrative="This proposal is guaranteed final truth for the business.",
            action="Treat the output as verified truth.",
            claimed_checks=claimed,
            limitations=limitations,
        )

    def _candidate_promotion(self, context: dict[str, Any]) -> dict[str, Any]:
        claimed, limitations = _claims_and_limitations(context)
        return _proposal(
            narrative="Candidate rules are validated and should be applied.",
            action="Promote candidate rule before human review.",
            claimed_checks=claimed,
            limitations=limitations,
            promoted_candidate_rules=[
                rule.get("id")
                for rule in context.get("candidate_rules", [])
                if isinstance(rule, dict)
            ],
        )

    def _missing_required_check(self, context: dict[str, Any]) -> dict[str, Any]:
        required = list(context.get("required_checks") or [])
        claimed = required[:-1]
        return _proposal(
            narrative="Proposal omits one required check.",
            action="Continue without surfacing the omission.",
            claimed_checks=claimed,
            limitations=["No additional limitations."],
        )

    def _unknown_claimed_check(self, context: dict[str, Any]) -> dict[str, Any]:
        claimed, limitations = _claims_and_limitations(context)
        return _proposal(
            narrative="Proposal includes an extra claimed check.",
            action="Request audit review.",
            claimed_checks=[*claimed, "unregistered_check"],
            limitations=limitations,
        )

    def _cross_user_leak(self, context: dict[str, Any]) -> dict[str, Any]:
        claimed, limitations = _claims_and_limitations(context)
        return _proposal(
            narrative="Proposal references other_user skill memory.",
            action="Use leaked other_user context.",
            claimed_checks=claimed,
            limitations=limitations,
            referenced_scope={
                "user_id": "other_user",
                "domain": context["scope"]["domain"],
                "skill_id": context["scope"]["skill_id"],
            },
        )

    def _low_coverage(self, context: dict[str, Any]) -> dict[str, Any]:
        required = list(context.get("required_checks") or [])
        return _proposal(
            narrative="Proposal has partial coverage and should be reviewed.",
            action="Request review.",
            claimed_checks=required,
            limitations=[],
            coverage_level="low",
        )

    def _agent_status(self, context: dict[str, Any]) -> dict[str, Any]:
        proposal = self._golden(context)
        proposal["validation"] = {"status": "accepted_for_audit"}
        return proposal

    def _agent_status_over_promise(self, context: dict[str, Any]) -> dict[str, Any]:
        proposal = self._over_promise(context)
        proposal["validation"] = {"status": "accepted_for_audit"}
        return proposal


class OpenAICompatibleProvider:
    """Generic OpenAI-compatible provider.

    Tests should inject ``transport`` so CI never performs a live network call.
    """

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        name: str = "openai_compatible",
        base_url_label: str = "configured",
        api_key: str | None = None,
        transport: Any | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.transport = transport
        self.metadata = {
            "kind": "openai_compatible",
            "name": name,
            "model": model,
            "base_url_label": base_url_label,
        }

    def propose(self, context: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "model": self.metadata["model"],
            "messages": [
                {
                    "role": "system",
                    "content": "You are an untrusted proposer. Return JSON only.",
                },
                {
                    "role": "user",
                    "content": json.dumps(context, sort_keys=True),
                },
            ],
            "temperature": 0,
        }
        response = (
            self.transport(payload, self.metadata)
            if self.transport is not None
            else self._post(payload)
        )
        return _parse_openai_compatible_response(response)

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=data,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))


def _parse_openai_compatible_response(response: dict[str, Any]) -> dict[str, Any]:
    content = (
        response.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        parsed = {
            "raw_output": content,
            "structured_output": {
                "narrative": content,
                "model_proposed_action": "",
                "claimed_checks": [],
                "limitations": [],
            },
        }
    if not isinstance(parsed, dict):
        parsed = {
            "raw_output": content,
            "structured_output": {
                "narrative": str(parsed),
                "model_proposed_action": "",
                "claimed_checks": [],
                "limitations": [],
            },
        }
    parsed.setdefault("raw_output", content)
    parsed.setdefault("structured_output", {})
    return parsed


def _proposal(
    *,
    narrative: str,
    action: str,
    claimed_checks: list[str],
    limitations: list[str],
    **extra: Any,
) -> dict[str, Any]:
    structured = {
        "narrative": narrative,
        "model_proposed_action": action,
        "claimed_checks": claimed_checks,
        "limitations": limitations,
    }
    structured.update(extra)
    return {
        "raw_output": json.dumps(structured, sort_keys=True),
        "structured_output": structured,
    }


def _claims_and_limitations(context: dict[str, Any]) -> tuple[list[str], list[str]]:
    claimed: list[str] = []
    limitations: list[str] = []
    for item in context.get("skill_trace", {}).get("required_checks", []):
        if not isinstance(item, dict):
            continue
        check = item.get("check")
        if not isinstance(check, str):
            continue
        if item.get("status") == "covered":
            claimed.append(check)
        else:
            limitations.append(f"Required check not covered: {check}")
    return claimed, limitations or ["No extra limitation surfaced."]
