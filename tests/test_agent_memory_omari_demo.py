import subprocess
import sys
from pathlib import Path

from demo.demo_agent_memory_omari_lead_capture import (
    DECISION_FIX_CAPTURE,
    EXTERNAL_EVIDENCE_LIMITATION,
    FACT_LOSS_RATE,
    FACT_SINGLE_ENTRY,
    HYPOTHESIS_STABLE_VOLUME,
    INFERENCE_FIX_FIRST,
    run_demo,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
KERNEL_FILES = [
    "src/dsm/core/storage.py",
    "src/dsm/core/shard_segments.py",
    "src/dsm/core/models.py",
    "src/dsm/core/signing.py",
    "src/dsm/core/replay.py",
    "src/dsm/core/security.py",
    "src/dsm/core/KERNEL_VERSION",
]
DANGEROUS_WORDING = (
    "tamper-proof",
    "verified truth",
    "proof of truth",
    "guaranteed",
)


def test_omari_demo_writes_to_supplied_data_dir(tmp_path):
    data_dir = tmp_path / "omari-memory"
    result = run_demo(data_dir=str(data_dir), print_output=False)
    decision = result["entries"]["decision"]
    output = result["output"]

    assert data_dir.exists()
    assert f"Data dir: {data_dir}" in output
    assert f"Decision hash: {decision.hash}" in output
    assert "CLI markdown command:" in output
    assert "python -m dsm memory explain" in output
    assert f"--data-dir {data_dir}" in output
    assert "--shard agent_memory --markdown" in output
    assert EXTERNAL_EVIDENCE_LIMITATION in output
    assert "source_refs:" in output
    assert decision.hash.startswith("v1:")


def test_omari_demo_output_can_be_explained_by_cli_markdown(tmp_path):
    data_dir = tmp_path / "omari-memory"
    demo_result = subprocess.run(
        [
            sys.executable,
            "demo/demo_agent_memory_omari_lead_capture.py",
            "--data-dir",
            str(data_dir),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert demo_result.returncode == 0, demo_result.stderr
    assert f"Data dir: {data_dir}" in demo_result.stdout
    assert "CLI markdown command:" in demo_result.stdout
    decision_hash = _extract_line_value(demo_result.stdout, "Decision hash: ")
    assert decision_hash.startswith("v1:")

    explain_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "dsm",
            "memory",
            "explain",
            decision_hash,
            "--data-dir",
            str(data_dir),
            "--shard",
            "agent_memory",
            "--markdown",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert explain_result.returncode == 0, explain_result.stderr
    output = explain_result.stdout
    lower_output = output.lower()
    assert "# Agent Memory Audit Report" in output
    assert DECISION_FIX_CAPTURE in output
    assert FACT_LOSS_RATE in output
    assert FACT_SINGLE_ENTRY in output
    assert HYPOTHESIS_STABLE_VOLUME in output
    assert INFERENCE_FIX_FIRST in output
    assert "v1:" in output
    assert "## Source References" in output
    assert "## Trust Model / Limitations" in output
    assert "self-estimate, not calibrated" in output
    assert "does not prove factual truth" in output
    assert "does not prove reasoning validity" in output
    assert all(wording not in lower_output for wording in DANGEROUS_WORDING)


def test_omari_demo_does_not_modify_kernel_files():
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "--", *KERNEL_FILES],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == ""


def _extract_line_value(output: str, prefix: str) -> str:
    for line in output.splitlines():
        if line.startswith(prefix):
            return line.removeprefix(prefix).strip()
    raise AssertionError(f"Missing line prefix: {prefix}")
