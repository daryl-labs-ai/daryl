import json
import subprocess
import sys
from pathlib import Path

from dsm.core.storage import Storage
from dsm.memory import (
    record_decision,
    record_fact,
    record_hypothesis,
    record_inference,
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
EXPLAIN_SCHEMA_VERSION = "agent_memory.explain.v1"


def _run_dsm(*args):
    return subprocess.run(
        [sys.executable, "-m", "dsm", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )


def _build_memory_chain(data_dir: Path):
    storage = Storage(data_dir=str(data_dir))
    fact = record_fact(
        "Downtime costs $50,000 per day.",
        confidence=1.0,
        storage=storage,
    )
    hypothesis = record_hypothesis(
        "The used board can be sourced and installed quickly.",
        source_refs=[{"shard": fact.shard, "entry_hash": fact.hash}],
        confidence=0.7,
        storage=storage,
    )
    inference = record_inference(
        "Immediate replacement is economically justified if service resumes within one day.",
        depends_on=[fact.hash, hypothesis.hash],
        confidence=0.85,
        storage=storage,
    )
    decision = record_decision(
        "Recommend replacing the board immediately.",
        depends_on=[inference.hash],
        confidence=0.8,
        storage=storage,
    )
    return {
        "fact": fact,
        "hypothesis": hypothesis,
        "inference": inference,
        "decision": decision,
    }


def test_agent_memory_explain_command_exists():
    result = _run_dsm("memory", "explain", "--help")

    assert result.returncode == 0
    assert "decision_hash" in result.stdout
    assert "--json" in result.stdout


def test_agent_memory_explain_cli_outputs_justification_chain(tmp_path):
    data_dir = tmp_path / "data"
    chain = _build_memory_chain(data_dir)

    result = _run_dsm(
        "memory",
        "explain",
        chain["decision"].hash,
        "--data-dir",
        str(data_dir),
    )

    assert result.returncode == 0, result.stderr
    output = result.stdout.lower()
    assert "decision:" in output
    assert "fact:" in output
    assert "hypothesis:" in output
    assert "inference:" in output
    assert "v1:" in result.stdout
    assert chain["decision"].hash in result.stdout
    assert chain["inference"].hash in result.stdout
    assert chain["fact"].hash in result.stdout
    assert chain["hypothesis"].hash in result.stdout
    assert "source refs:" in output
    assert "local tamper-evident" in output


def test_agent_memory_explain_cli_outputs_json(tmp_path):
    data_dir = tmp_path / "data"
    chain = _build_memory_chain(data_dir)

    result = _run_dsm(
        "memory",
        "explain",
        chain["decision"].hash,
        "--data-dir",
        str(data_dir),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == EXPLAIN_SCHEMA_VERSION
    assert payload["status"] == "ok"
    assert payload["query"]["decision_hash"] == chain["decision"].hash
    assert payload["query"]["shard"] == "agent_memory"
    assert payload["query"]["depth"] == 2
    assert payload["decision"]["entry_hash"] == chain["decision"].hash
    assert payload["decision"]["kind"] == "decision"
    assert payload["decision"]["depends_on"] == [chain["inference"].hash]

    supporting_chain = payload["supporting_chain"]
    assert [entry["entry_hash"] for entry in supporting_chain["facts"]] == [chain["fact"].hash]
    assert [entry["entry_hash"] for entry in supporting_chain["hypotheses"]] == [
        chain["hypothesis"].hash
    ]
    assert [entry["entry_hash"] for entry in supporting_chain["inferences"]] == [
        chain["inference"].hash
    ]
    assert payload["source_refs"] == [
        {
            "owner_kind": "hypothesis",
            "owner_entry_hash": chain["hypothesis"].hash,
            "shard": "agent_memory",
            "entry_hash": chain["fact"].hash,
        }
    ]
    assert payload["verification"]["scope"] == "local tamper-evident; not external anchoring"
    assert payload["verification"]["hint"] == "dsm verify --shard agent_memory"
    assert payload["warnings"] == []


def test_agent_memory_explain_unknown_decision_fails_cleanly(tmp_path):
    result = _run_dsm(
        "memory",
        "explain",
        "v1:missing",
        "--data-dir",
        str(tmp_path / "data"),
    )

    assert result.returncode == 1
    assert "decision not found" in result.stderr.lower()
    assert "traceback" not in result.stderr.lower()


def test_agent_memory_explain_unknown_decision_outputs_json_error(tmp_path):
    result = _run_dsm(
        "memory",
        "explain",
        "v1:missing",
        "--data-dir",
        str(tmp_path / "data"),
        "--json",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload == {
        "schema_version": EXPLAIN_SCHEMA_VERSION,
        "status": "error",
        "error": {
            "code": "decision_not_found",
            "message": "Decision not found",
        },
        "query": {
            "decision_hash": "v1:missing",
            "shard": "agent_memory",
            "depth": 2,
        },
    }
    assert "traceback" not in result.stderr.lower()


def test_agent_memory_cli_does_not_modify_kernel_files():
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "--", *KERNEL_FILES],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == ""
