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
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
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
DANGEROUS_MARKDOWN_WORDING = ("tamper-proof", "verified truth", "proof of truth")


def _load_fixture(name: str):
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def _normalize_contract(value):
    if isinstance(value, dict):
        return {key: _normalize_contract(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_contract(item) for item in value]
    if isinstance(value, str) and value.startswith("v1:"):
        return "v1:<hash>"
    return value


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
    assert "--markdown" in result.stdout


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
    assert _normalize_contract(payload) == _load_fixture("agent_memory_explain_v1_ok.json")


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
    assert _normalize_contract(payload) == _load_fixture("agent_memory_explain_v1_error.json")
    assert "traceback" not in result.stderr.lower()


def test_agent_memory_explain_json_warns_on_missing_dependency(tmp_path):
    data_dir = tmp_path / "data"
    storage = Storage(data_dir=str(data_dir))
    missing_ref = "v1:missing-dependency"
    decision = record_decision(
        "Make a decision with one dangling dependency.",
        depends_on=[missing_ref],
        storage=storage,
    )

    result = _run_dsm(
        "memory",
        "explain",
        decision.hash,
        "--data-dir",
        str(data_dir),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["warnings"] == [
        {
            "code": "missing_dependency",
            "message": f"Dependency not found: {missing_ref}",
            "ref": missing_ref,
        }
    ]
    assert payload["supporting_chain"]["facts"] == []
    assert payload["supporting_chain"]["hypotheses"] == []
    assert payload["supporting_chain"]["inferences"] == []


def test_agent_memory_explain_json_warns_when_depth_limit_reached(tmp_path):
    data_dir = tmp_path / "data"
    chain = _build_memory_chain(data_dir)

    result = _run_dsm(
        "memory",
        "explain",
        chain["decision"].hash,
        "--data-dir",
        str(data_dir),
        "--depth",
        "1",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["query"]["depth"] == 1
    assert payload["supporting_chain"]["facts"] == []
    assert payload["supporting_chain"]["hypotheses"] == []
    assert [entry["entry_hash"] for entry in payload["supporting_chain"]["inferences"]] == [
        chain["inference"].hash
    ]
    assert payload["warnings"] == [
        {
            "code": "depth_limit_reached",
            "message": "Traversal stopped at depth 1; some dependencies may remain unexplored.",
            "entry_hashes": [chain["inference"].hash],
        }
    ]


def test_agent_memory_explain_cli_outputs_markdown(tmp_path):
    data_dir = tmp_path / "data"
    chain = _build_memory_chain(data_dir)

    result = _run_dsm(
        "memory",
        "explain",
        chain["decision"].hash,
        "--data-dir",
        str(data_dir),
        "--markdown",
    )

    assert result.returncode == 0, result.stderr
    output = result.stdout
    lower_output = output.lower()
    assert "# Agent Memory Audit Report" in output
    assert "## Decision" in output
    assert "## Supporting Facts" in output
    assert "## Hypotheses" in output
    assert "## Inferences" in output
    assert "## Trust Model / Limitations" in output
    assert chain["decision"].hash in output
    assert chain["fact"].hash in output
    assert chain["hypothesis"].hash in output
    assert chain["inference"].hash in output
    assert "self-estimate, not calibrated" in output
    assert "local tamper-evident" in output
    assert "does not prove factual truth" in output
    assert "not external anchoring" in output
    assert all(wording not in lower_output for wording in DANGEROUS_MARKDOWN_WORDING)


def test_agent_memory_explain_markdown_displays_warnings(tmp_path):
    data_dir = tmp_path / "data"
    storage = Storage(data_dir=str(data_dir))
    missing_ref = "v1:missing-dependency"
    decision = record_decision(
        "Make a decision with one dangling dependency.",
        depends_on=[missing_ref],
        storage=storage,
    )

    result = _run_dsm(
        "memory",
        "explain",
        decision.hash,
        "--data-dir",
        str(data_dir),
        "--markdown",
    )

    assert result.returncode == 0, result.stderr
    output = result.stdout
    assert "## Warnings" in output
    assert "`missing_dependency`" in output
    assert f"Dependency not found: {missing_ref}" in output
    assert missing_ref in output


def test_agent_memory_explain_unknown_decision_outputs_markdown_error(tmp_path):
    result = _run_dsm(
        "memory",
        "explain",
        "v1:missing",
        "--data-dir",
        str(tmp_path / "data"),
        "--markdown",
    )

    assert result.returncode == 1
    output = result.stdout
    assert "# Agent Memory Audit Report" in output
    assert "## Error" in output
    assert "- Code: `decision_not_found`" in output
    assert "- Message: Decision not found" in output
    assert "traceback" not in output.lower()
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
