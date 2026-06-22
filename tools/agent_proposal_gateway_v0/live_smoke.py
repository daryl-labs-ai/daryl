#!/usr/bin/env python3
"""Manual live smoke for Agent Proposal Gateway v0.

This script is intentionally outside CI. It is a thin wrapper over the
existing gateway so a local OpenAI-compatible provider can propose while DSM
keeps validation and status assignment.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (_REPO_ROOT, _REPO_ROOT / "src"):
    _path_text = str(_path)
    if _path_text not in sys.path:
        sys.path.insert(0, _path_text)

from eval.skill_retrieval_v0 import load_records
from tools.agent_proposal_gateway_v0 import (
    MockProposalProvider,
    OpenAICompatibleProvider,
    build_agent_proposal_context,
    build_openai_compatible_payload,
    run_agent_proposal_gateway,
)


VALIDATION_NOTICE = "validated for form/honesty, not truth"
DRY_RUN_CONTRACT_NOTICE = "dry-run contract preview; provider not called"
DEFAULT_BASE_URL = "http://localhost:1234/v1"
DEFAULT_PROVIDER_NAME = "lmstudio"
DEFAULT_MODEL = "local-model"
DEFAULT_DATA_DIR = ".venv-live-smoke/agent-proposal"
DEFAULT_RECORDS_PATH = "datasets/dsm_reasoning_v0/records.jsonl"
DEFAULT_USER_ID = "mohamed"
DEFAULT_DOMAIN = "omari_ai"
DEFAULT_SKILL_ID = "omari_ai.lead_capture_reliability"
DEFAULT_TASK_TYPE = "prioritization_decision"


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    environment = os.environ if env is None else env
    args = _parse_args(argv, environment)
    if args.dry_run_contract:
        preview = build_contract_preview(args)
        _print_contract_preview(preview)
        return 0
    try:
        result = run_live_smoke(args, environment)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    _print_result(result, args)
    return 0


def run_live_smoke(args: argparse.Namespace, env: Mapping[str, str]) -> dict[str, Any]:
    if args.live and _truthy(env.get("CI")):
        raise RuntimeError("refusing to run --live when CI=true")
    if args.provider != "mock" and not args.live:
        raise RuntimeError(
            "refusing to contact a live provider without --live; "
            "use --provider mock for a no-network smoke or add --live manually"
        )

    provider = _provider_from_args(args, env)
    records = load_records(args.records_path)
    return run_agent_proposal_gateway(
        records,
        provider=provider,
        data_dir=args.data_dir,
        user_id=args.user_id,
        domain=args.domain,
        skill_id=args.skill_id,
        task_type=args.task_type,
        known_inputs={
            "customer_name": "Before",
            "interruption_detected": True,
        },
    )


def build_contract_preview(args: argparse.Namespace) -> dict[str, Any]:
    records = load_records(args.records_path)
    context = build_agent_proposal_context(
        records,
        user_id=args.user_id,
        domain=args.domain,
        skill_id=args.skill_id,
        task_type=args.task_type,
        known_inputs={
            "customer_name": "Before",
            "interruption_detected": True,
        },
    )
    payload = build_openai_compatible_payload(context, model=args.model)
    return {
        "notice": DRY_RUN_CONTRACT_NOTICE,
        "provider": args.provider,
        "provider_name": args.provider_name,
        "base_url_label": args.base_url_label,
        "context": context,
        "openai_compatible_payload": payload,
    }


def _provider_from_args(
    args: argparse.Namespace,
    env: Mapping[str, str],
) -> MockProposalProvider | OpenAICompatibleProvider:
    if args.provider == "mock":
        return MockProposalProvider(args.mock_scenario)
    api_key = env.get(args.api_key_env, "") if args.api_key_env else ""
    return OpenAICompatibleProvider(
        base_url=args.base_url,
        model=args.model,
        name=args.provider_name,
        base_url_label=args.base_url_label,
        api_key=api_key or None,
        transport=_live_openai_transport(
            base_url=args.base_url,
            timeout=args.timeout,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            api_key=api_key or None,
        ),
    )


def _live_openai_transport(
    *,
    base_url: str,
    timeout: float,
    temperature: float,
    max_tokens: int | None,
    api_key: str | None,
):
    def transport(payload: dict[str, Any], _metadata: dict[str, str]) -> dict[str, Any]:
        live_payload = {**payload, "temperature": temperature}
        if max_tokens is not None:
            live_payload["max_tokens"] = max_tokens
        data = json.dumps(live_payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        request = urllib.request.Request(
            f"{base_url.rstrip('/')}/chat/completions",
            data=data,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    return transport


def _print_result(result: dict[str, Any], args: argparse.Namespace) -> None:
    persistence = result["persistence"]
    proposal = result["proposal"]
    validation = result["validation"]

    print(VALIDATION_NOTICE)
    print(f"Provider: {proposal['provider']['name']}")
    print(f"Model: {proposal['provider']['model']}")
    print(f"Data dir: {Path(args.data_dir)}")
    print(f"Validation status: {validation['status']}")
    print(f"Decision hash: {persistence['decision_hash']}")
    print(f"Input context hash: {proposal['input_context_hash']}")
    print(f"Raw output hash: {proposal['raw_output_hash']}")
    print()
    print("Explain JSON:")
    print(json.dumps(persistence["explain"], indent=2, sort_keys=True))
    print()
    print("Markdown audit:")
    markdown = persistence["markdown"]
    print(markdown, end="" if markdown.endswith("\n") else "\n")


def _print_contract_preview(preview: dict[str, Any]) -> None:
    print(DRY_RUN_CONTRACT_NOTICE)
    print(json.dumps(preview, indent=2, sort_keys=True))


def _parse_args(
    argv: list[str] | None,
    env: Mapping[str, str],
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manual live smoke for Agent Proposal Gateway v0.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Explicitly allow a live OpenAI-compatible provider call.",
    )
    parser.add_argument(
        "--dry-run-contract",
        action="store_true",
        help="Print the final provider contract/context without calling a provider.",
    )
    parser.add_argument(
        "--provider",
        choices=("openai-compatible", "mock"),
        default=env.get("AGENT_PROPOSAL_PROVIDER", "openai-compatible"),
    )
    parser.add_argument(
        "--base-url",
        default=env.get("AGENT_PROPOSAL_BASE_URL", DEFAULT_BASE_URL),
    )
    parser.add_argument(
        "--model",
        default=env.get("AGENT_PROPOSAL_MODEL", DEFAULT_MODEL),
    )
    parser.add_argument(
        "--temperature",
        type=_parse_temperature,
        default=env.get("AGENT_PROPOSAL_TEMPERATURE", "low"),
        help="Number or alias: low, medium, high.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(env.get("AGENT_PROPOSAL_TIMEOUT", "30")),
    )
    parser.add_argument(
        "--max-tokens",
        type=_parse_optional_int,
        default=env.get("AGENT_PROPOSAL_MAX_TOKENS", "700"),
    )
    parser.add_argument(
        "--provider-name",
        default=env.get("AGENT_PROPOSAL_PROVIDER_NAME", DEFAULT_PROVIDER_NAME),
    )
    parser.add_argument(
        "--base-url-label",
        default=env.get("AGENT_PROPOSAL_BASE_URL_LABEL", "local-manual"),
    )
    parser.add_argument(
        "--api-key-env",
        default=env.get("AGENT_PROPOSAL_API_KEY_ENV", "AGENT_PROPOSAL_API_KEY"),
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(env.get("AGENT_PROPOSAL_DATA_DIR", DEFAULT_DATA_DIR)),
    )
    parser.add_argument(
        "--records-path",
        type=Path,
        default=Path(env.get("AGENT_PROPOSAL_RECORDS_PATH", DEFAULT_RECORDS_PATH)),
    )
    parser.add_argument(
        "--user-id",
        default=env.get("AGENT_PROPOSAL_USER_ID", DEFAULT_USER_ID),
    )
    parser.add_argument(
        "--domain",
        default=env.get("AGENT_PROPOSAL_DOMAIN", DEFAULT_DOMAIN),
    )
    parser.add_argument(
        "--skill-id",
        default=env.get("AGENT_PROPOSAL_SKILL_ID", DEFAULT_SKILL_ID),
    )
    parser.add_argument(
        "--task-type",
        default=env.get("AGENT_PROPOSAL_TASK_TYPE", DEFAULT_TASK_TYPE),
    )
    parser.add_argument(
        "--mock-scenario",
        default=env.get("AGENT_PROPOSAL_MOCK_SCENARIO", "golden"),
    )
    return parser.parse_args(argv)


def _parse_temperature(value: str) -> float:
    aliases = {
        "low": 0.0,
        "medium": 0.2,
        "high": 0.7,
    }
    normalized = value.strip().lower()
    if normalized in aliases:
        return aliases[normalized]
    try:
        temperature = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "temperature must be a number or one of: low, medium, high"
        ) from exc
    if temperature < 0:
        raise argparse.ArgumentTypeError("temperature must be non-negative")
    return temperature


def _parse_optional_int(value: str) -> int | None:
    if value.strip().lower() in {"", "none", "null", "off"}:
        return None
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("max-tokens must be positive or none")
    return parsed


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    raise SystemExit(main())
