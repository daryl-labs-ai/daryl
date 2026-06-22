from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from tools.agent_proposal_gateway_v0 import live_smoke


REPO_ROOT = Path(__file__).resolve().parents[1]
LIVE_SMOKE_PATH = REPO_ROOT / "tools" / "agent_proposal_gateway_v0" / "live_smoke.py"
MAIN_MEMORY_PATH = REPO_ROOT / ".dsm-data"


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
