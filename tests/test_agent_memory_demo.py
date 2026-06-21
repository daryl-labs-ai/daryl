import subprocess
import sys
from pathlib import Path

from demo.demo_agent_memory_justified_answer import run_demo


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_justified_answer_demo_writes_and_explains_chain(tmp_path):
    result = run_demo(data_dir=str(tmp_path / "memory"), print_output=False)

    entries = result["entries"]
    facts = entries["facts"]
    hypothesis = entries["hypothesis"]
    inference = entries["inference"]
    decision = entries["decision"]

    assert len(facts) >= 1
    assert hypothesis.hash
    assert inference.hash
    assert decision.hash

    inference_depends = set(result["explanation"]["dependency_map"][inference.hash][i]["entry_hash"] for i in range(3))
    expected_inference_refs = {facts[0].hash, facts[1].hash, hypothesis.hash}
    assert inference_depends == expected_inference_refs

    decision_dependencies = result["explanation"]["dependencies"]
    assert [item["entry_hash"] for item in decision_dependencies] == [inference.hash]

    decision_record = result["explanation"]["decision"]
    assert decision_record["kind"] == "decision"
    assert decision_record["entry_hash"] == decision.hash

    supporting_hashes = {item["entry_hash"] for item in result["explanation"]["supporting_entries"]}
    assert expected_inference_refs.issubset(supporting_hashes)
    assert inference.hash in supporting_hashes
    assert all(value for value in supporting_hashes)

    output = result["output"]
    assert result["question"] in output
    assert decision.hash in output
    assert inference.hash in output
    assert f"Data dir: {result['data_dir']}" in output
    assert f"Decision hash: {decision.hash}" in output
    assert "python -m dsm memory explain" in output
    assert f"--data-dir {result['data_dir']}" in output
    assert "--shard agent_memory --markdown" in output
    assert "DSM currently provides tamper-evidence in local trust" in output


def test_justified_answer_demo_output_can_be_reused_by_cli(tmp_path):
    data_dir = tmp_path / "demo-memory"
    demo_result = subprocess.run(
        [
            sys.executable,
            "demo/demo_agent_memory_justified_answer.py",
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
    assert "# Agent Memory Audit Report" in explain_result.stdout
    assert decision_hash in explain_result.stdout


def _extract_line_value(output: str, prefix: str) -> str:
    for line in output.splitlines():
        if line.startswith(prefix):
            return line.removeprefix(prefix).strip()
    raise AssertionError(f"Missing line prefix: {prefix}")
