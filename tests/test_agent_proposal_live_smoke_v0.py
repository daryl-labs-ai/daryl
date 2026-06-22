from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from eval.skill_retrieval_v0 import load_records
from tools.agent_proposal_gateway_v0 import (
    ACCEPTED_FOR_AUDIT,
    NEEDS_HUMAN_REVIEW,
    REJECTED_BY_VALIDATOR,
    run_agent_proposal_gateway,
)
from tools.agent_proposal_gateway_v0 import live_smoke


REPO_ROOT = Path(__file__).resolve().parents[1]
LIVE_SMOKE_PATH = REPO_ROOT / "tools" / "agent_proposal_gateway_v0" / "live_smoke.py"
MAIN_MEMORY_PATH = REPO_ROOT / ".dsm-data"
RECORDS_PATH = REPO_ROOT / "datasets" / "dsm_reasoning_v0" / "records.jsonl"
LIVE_SMOKE_REQUIRED_CHECKS = (
    "bug_before_feature",
    "external_evidence_limit_disclosed",
    "known_context_not_reasked",
    "persistence_failure_checked",
)


def test_live_smoke_refuses_live_under_ci(monkeypatch, tmp_path, capsys):
    def fail_provider(*_args, **_kwargs):
        raise AssertionError("live provider should not be constructed under CI")

    monkeypatch.setattr(live_smoke, "OpenAICompatibleProvider", fail_provider)

    code = live_smoke.main(
        ["--live", "--data-dir", str(tmp_path / "smoke")],
        env={"CI": "true"},
    )

    captured = capsys.readouterr()
    assert code == 2
    assert "CI=true" in captured.err


def test_live_smoke_refuses_live_provider_without_live_flag(
    monkeypatch,
    tmp_path,
    capsys,
):
    def fail_provider(*_args, **_kwargs):
        raise AssertionError("live provider should not be constructed without --live")

    monkeypatch.setattr(live_smoke, "OpenAICompatibleProvider", fail_provider)

    code = live_smoke.main(
        ["--data-dir", str(tmp_path / "smoke")],
        env={"CI": "false"},
    )

    captured = capsys.readouterr()
    assert code == 2
    assert "--live" in captured.err


def test_live_smoke_mock_plumbing_writes_only_test_data_dir(
    monkeypatch,
    tmp_path,
    capsys,
):
    def fail_urlopen(*_args, **_kwargs):
        raise AssertionError("mock smoke must not perform network I/O")

    monkeypatch.setattr(live_smoke.urllib.request, "urlopen", fail_urlopen)
    data_dir = tmp_path / "agent-proposal-smoke"

    code = live_smoke.main(
        ["--provider", "mock", "--data-dir", str(data_dir)],
        env={"CI": "true"},
    )

    captured = capsys.readouterr()
    assert code == 0
    assert live_smoke.VALIDATION_NOTICE in captured.out
    assert "# Agent Memory Audit Report" in captured.out
    assert "Validation status: accepted_for_audit" in captured.out
    assert "Decision hash: v1:" in captured.out
    assert "Raw output hash: v1:" in captured.out
    assert data_dir.exists()
    assert data_dir != MAIN_MEMORY_PATH
    assert tmp_path in data_dir.parents


def test_direct_script_execution_from_repo_root_without_pythonpath(tmp_path):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["CI"] = "true"
    data_dir = tmp_path / "direct-smoke"

    result = subprocess.run(
        [
            sys.executable,
            str(LIVE_SMOKE_PATH),
            "--provider",
            "mock",
            "--data-dir",
            str(data_dir),
        ],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert live_smoke.VALIDATION_NOTICE in result.stdout
    assert "Validation status: accepted_for_audit" in result.stdout
    assert "ModuleNotFoundError" not in result.stderr
    assert data_dir.exists()


def test_live_smoke_mock_can_use_rejected_scenario_without_truth_claim(
    tmp_path,
    capsys,
):
    code = live_smoke.main(
        [
            "--provider",
            "mock",
            "--mock-scenario",
            "over_promise",
            "--data-dir",
            str(tmp_path / "rejected-smoke"),
        ],
        env={"CI": "true"},
    )

    captured = capsys.readouterr()
    assert code == 0
    assert live_smoke.VALIDATION_NOTICE in captured.out
    assert "Validation status: rejected_by_validator" in captured.out
    assert "rejected_proposal_audit" in captured.out


def test_conformant_provider_reaches_accepted_for_audit_without_lowering_bar(tmp_path):
    result = _run_conformant_provider(tmp_path, ConformantProposalProvider())

    validation = result["validation"]
    proposal = result["proposal"]

    assert validation["status"] == ACCEPTED_FOR_AUDIT
    assert validation["warnings"] == []
    assert validation["rejections"] == []
    assert proposal["agent_supplied_status"] is None
    assert set(proposal["structured_output"]["claimed_checks"]) == set(
        result["context"]["required_checks"]
    )
    assert proposal["structured_output"]["limitations"]
    assert "promoted_candidate_rules" not in proposal["structured_output"]


@pytest.mark.parametrize("omitted_check", LIVE_SMOKE_REQUIRED_CHECKS)
def test_conformant_provider_omitting_required_check_is_rejected(
    omitted_check,
    tmp_path,
):
    result = _run_conformant_provider(
        tmp_path,
        ConformantProposalProvider(omit_checks={omitted_check}),
        data_dir_name=f"missing-{omitted_check}",
    )

    validation = result["validation"]

    assert validation["status"] == REJECTED_BY_VALIDATOR
    assert _issue_codes(validation["rejections"]) == {
        "required_check_not_covered_or_surfaced"
    }
    assert any(
        issue.get("check") == omitted_check
        and issue["code"] == "required_check_not_covered_or_surfaced"
        for issue in validation["rejections"]
    )


def test_conformant_provider_without_limitations_is_not_accepted(tmp_path):
    result = _run_conformant_provider(
        tmp_path,
        ConformantProposalProvider(limitations=[]),
        data_dir_name="missing-limitations",
    )

    validation = result["validation"]

    assert validation["status"] == NEEDS_HUMAN_REVIEW
    assert validation["rejections"] == []
    assert "missing_limitations" in _issue_codes(validation["warnings"])


def test_alternative_phrasing_conformant_provider_reaches_accepted_for_audit(tmp_path):
    result = _run_conformant_provider(
        tmp_path,
        ConformantProposalProvider(alternative_phrasing=True),
        data_dir_name="alternative-phrasing",
    )

    validation = result["validation"]
    proposal = result["proposal"]

    assert validation["status"] == ACCEPTED_FOR_AUDIT
    assert validation["warnings"] == []
    assert validation["rejections"] == []
    assert "explicitly covers" not in proposal["structured_output"]["narrative"]
    assert set(proposal["structured_output"]["claimed_checks"]) == set(
        result["context"]["required_checks"]
    )


def test_openai_compatible_provider_is_not_called_live_in_ci(monkeypatch, tmp_path):
    def fail_transport(*_args, **_kwargs):
        raise AssertionError("live transport should not be created under CI")

    monkeypatch.setattr(live_smoke, "_live_openai_transport", fail_transport)

    code = live_smoke.main(
        ["--live", "--data-dir", str(tmp_path / "smoke")],
        env={"CI": "1"},
    )

    assert code == 2


def test_live_transport_applies_manual_config_with_mocked_http(monkeypatch):
    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            content = {
                "raw_output": "ok",
                "structured_output": {
                    "narrative": "ok",
                    "claimed_checks": [],
                    "limitations": ["mocked transport"],
                },
            }
            return json.dumps(
                {"choices": [{"message": {"content": json.dumps(content)}}]}
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["timeout"] = timeout
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["headers"] = dict(request.header_items())
        return FakeResponse()

    monkeypatch.setattr(live_smoke.urllib.request, "urlopen", fake_urlopen)
    transport = live_smoke._live_openai_transport(
        base_url="http://localhost:1234/v1",
        timeout=12,
        temperature=0.2,
        max_tokens=123,
        api_key="secret",
    )

    response = transport({"model": "m", "messages": [], "temperature": 0}, {})

    assert response["choices"][0]["message"]["content"]
    assert captured["timeout"] == 12
    assert captured["url"] == "http://localhost:1234/v1/chat/completions"
    assert captured["payload"]["temperature"] == 0.2
    assert captured["payload"]["max_tokens"] == 123
    assert captured["headers"]["Authorization"] == "Bearer secret"


def test_live_smoke_accepts_env_config():
    args = live_smoke._parse_args(
        [],
        {
            "AGENT_PROPOSAL_PROVIDER": "mock",
            "AGENT_PROPOSAL_MODEL": "local-test-model",
            "AGENT_PROPOSAL_TEMPERATURE": "medium",
            "AGENT_PROPOSAL_TIMEOUT": "12",
            "AGENT_PROPOSAL_MAX_TOKENS": "123",
            "AGENT_PROPOSAL_PROVIDER_NAME": "local-provider",
            "AGENT_PROPOSAL_DATA_DIR": ".venv-live-smoke/custom",
            "AGENT_PROPOSAL_USER_ID": "mohamed",
            "AGENT_PROPOSAL_DOMAIN": "omari_ai",
            "AGENT_PROPOSAL_SKILL_ID": "omari_ai.lead_capture_reliability",
        },
    )

    assert args.provider == "mock"
    assert args.model == "local-test-model"
    assert args.temperature == 0.2
    assert args.timeout == 12
    assert args.max_tokens == 123
    assert args.provider_name == "local-provider"
    assert args.data_dir == Path(".venv-live-smoke/custom")


def test_live_smoke_has_no_direct_storage_access():
    source = LIVE_SMOKE_PATH.read_text(encoding="utf-8")
    forbidden_fragments = (
        "from dsm." + "core",
        "import dsm." + "core",
        "Stor" + "age",
        "DSMReadRelay",
        "read_recent",
        "core." + "storage",
    )

    for fragment in forbidden_fragments:
        assert fragment not in source


def test_live_smoke_is_not_in_kernel_path():
    assert "src/dsm/core" not in LIVE_SMOKE_PATH.as_posix()


def _run_conformant_provider(
    tmp_path: Path,
    provider: "ConformantProposalProvider",
    *,
    data_dir_name: str = "conformant-smoke",
) -> dict:
    return run_agent_proposal_gateway(
        load_records(RECORDS_PATH),
        provider=provider,
        data_dir=tmp_path / data_dir_name,
        user_id="mohamed",
        domain="omari_ai",
        skill_id="omari_ai.lead_capture_reliability",
        task_type="prioritization_decision",
        known_inputs={
            "customer_name": "Before",
            "interruption_detected": True,
        },
    )


def _issue_codes(issues: list[dict]) -> set[str]:
    return {issue["code"] for issue in issues}


class ConformantProposalProvider:
    metadata = {
        "kind": "mock",
        "name": "conformant-acceptability",
        "model": "conformant-no-network",
        "base_url_label": "local-test",
    }

    def __init__(
        self,
        *,
        omit_checks: set[str] | None = None,
        limitations: list[str] | None = None,
        alternative_phrasing: bool = False,
    ):
        self.omit_checks = set(omit_checks or set())
        self.limitations = list(
            _alternative_limitations()
            if alternative_phrasing and limitations is None
            else _default_limitations()
            if limitations is None
            else limitations
        )
        self.alternative_phrasing = alternative_phrasing

    def propose(self, context: dict) -> dict:
        required_checks = [
            check
            for check in context["required_checks"]
            if check not in self.omit_checks
        ]
        narrative = (
            "The scaffold accounts for each DSM check supplied in the context "
            "and keeps the provider output as an auditable proposal only."
            if self.alternative_phrasing
            else "Proposal scaffold explicitly covers the DSM-required checks "
            "while leaving final business judgment outside this provider."
        )
        action = (
            "Send the proposal to audit with all required checks claimed and "
            "with limits stated; do not finalize a business outcome."
            if self.alternative_phrasing
            else "Prepare an audit-ready proposal for human or downstream review; "
            "do not treat it as a final business decision."
        )
        structured = {
            "narrative": narrative,
            "model_proposed_action": action,
            "claimed_checks": required_checks,
            "limitations": self.limitations,
        }
        return {
            "raw_output": json.dumps(structured, sort_keys=True),
            "structured_output": structured,
        }


def _default_limitations() -> list[str]:
    return [
        "This proposal is validated for form and honesty only.",
        "It does not establish factual truth or reasoning validity.",
        "Candidate rules remain candidate unless DSM marks them validated.",
        "External evidence must be represented through DSM-verifiable records.",
    ]


def _alternative_limitations() -> list[str]:
    return [
        "Audit admission is not a truth claim.",
        "A separate verifier must still evaluate facts and reasoning quality.",
        "Candidate material stays candidate unless represented as validated DSM data.",
        "External sources must be imported into DSM before they become evidence.",
    ]
