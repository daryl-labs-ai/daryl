"""Source-ref integrity v0 — existence reporting only.

Closes the one adversarial finding where DSM already held enough information
to detect an objective defect in the registry but reported nothing: a
`source_ref` pointing at an entry that does not exist.

The scope is deliberately narrow. DSM reports whether a referenced
`{shard, entry_hash}` pair EXISTS. It does not, and must not, report whether
the source is relevant, supporting, causal, or true. The `It's sunny in Paris`
case below is the standing proof that DSM makes no semantic judgement: an
off-topic but real entry resolves exactly like a genuinely supporting one.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from dsm.core.storage import Storage
from dsm.memory import (
    SOURCE_REF_MISSING,
    SOURCE_REF_RESOLVED,
    explain_decision,
    record_decision,
    record_fact,
    render_explain_markdown,
)


REPO_ROOT = Path(__file__).resolve().parents[1]

# The two adversarial inputs from the independent audit, reproduced verbatim
# as fixtures so the regression is anchored to the original experiment.
GROK_NONEXISTENT_HASH = (
    "v1:deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
)
GROK_OFF_TOPIC_STATEMENT = "It's sunny in Paris"


@pytest.fixture
def storage(tmp_path):
    return Storage(data_dir=str(tmp_path / "data"))


def _run_dsm(*args):
    return subprocess.run(
        [sys.executable, "-m", "dsm", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )


def _statuses(explanation):
    return {
        (item["shard"], item["entry_hash"]): item["status"]
        for item in explanation["source_ref_status"]
    }


# ---------------------------------------------------------------------------
# 1. A real source_ref resolves
# ---------------------------------------------------------------------------

def test_real_source_ref_is_resolved(storage):
    fact = record_fact("Downtime costs $50,000 per day.", storage=storage)
    decision = record_decision(
        "Replace the board immediately.",
        source_refs=[{"shard": fact.shard, "entry_hash": fact.hash}],
        storage=storage,
    )

    explanation = explain_decision(decision.hash, storage=storage)

    assert _statuses(explanation) == {
        (fact.shard, fact.hash): SOURCE_REF_RESOLVED
    }


# ---------------------------------------------------------------------------
# 2. A nonexistent source_ref is MISSING (Grok adversarial input 1)
# ---------------------------------------------------------------------------

def test_nonexistent_source_ref_is_missing(storage):
    decision = record_decision(
        "Ship the migration on Friday.",
        source_refs=[
            {"shard": "agent_memory", "entry_hash": GROK_NONEXISTENT_HASH}
        ],
        storage=storage,
    )

    explanation = explain_decision(decision.hash, storage=storage)

    assert _statuses(explanation) == {
        ("agent_memory", GROK_NONEXISTENT_HASH): SOURCE_REF_MISSING
    }


def test_source_ref_into_an_absent_shard_is_missing(storage):
    decision = record_decision(
        "Approve the vendor contract.",
        source_refs=[
            {"shard": "no_such_shard", "entry_hash": GROK_NONEXISTENT_HASH}
        ],
        storage=storage,
    )

    explanation = explain_decision(decision.hash, storage=storage)

    assert _statuses(explanation) == {
        ("no_such_shard", GROK_NONEXISTENT_HASH): SOURCE_REF_MISSING
    }


# ---------------------------------------------------------------------------
# 3. A missing ref surfaces in warnings and in every rendered report
# ---------------------------------------------------------------------------

def test_missing_source_ref_appears_in_json_warnings(tmp_path):
    data_dir = tmp_path / "data"
    storage = Storage(data_dir=str(data_dir))
    decision = record_decision(
        "Ship the migration on Friday.",
        source_refs=[
            {"shard": "agent_memory", "entry_hash": GROK_NONEXISTENT_HASH}
        ],
        storage=storage,
    )

    result = _run_dsm(
        "memory", "explain", decision.hash, "--data-dir", str(data_dir), "--json"
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)

    codes = [warning["code"] for warning in payload["warnings"]]
    assert "unresolved_source_ref" in codes

    warning = next(
        w for w in payload["warnings"] if w["code"] == "unresolved_source_ref"
    )
    assert warning["shard"] == "agent_memory"
    assert warning["entry_hash"] == GROK_NONEXISTENT_HASH

    assert payload["source_refs"][0]["status"] == SOURCE_REF_MISSING


# ---------------------------------------------------------------------------
# 4. `Warnings: None` is unreachable while a ref is unresolved
# ---------------------------------------------------------------------------

def test_warnings_none_is_impossible_when_a_source_ref_is_missing(tmp_path):
    """The exact adversarial state that must no longer be reachable.

    Before this fix the audit could obtain `Status: ok` + `Warnings: None` +
    `Local status: OK` while citing a hash that does not exist anywhere.
    """
    data_dir = tmp_path / "data"
    storage = Storage(data_dir=str(data_dir))
    decision = record_decision(
        "Ship the migration on Friday.",
        source_refs=[
            {"shard": "agent_memory", "entry_hash": GROK_NONEXISTENT_HASH}
        ],
        storage=storage,
    )

    markdown = _run_dsm(
        "memory",
        "explain",
        decision.hash,
        "--data-dir",
        str(data_dir),
        "--markdown",
    )
    assert markdown.returncode == 0, markdown.stderr

    warnings_section = markdown.stdout.split("## Warnings", 1)[1].split("##", 1)[0]
    assert "- None" not in warnings_section
    assert "unresolved_source_ref" in warnings_section
    assert f"-> {SOURCE_REF_MISSING}" in markdown.stdout

    plain = _run_dsm(
        "memory", "explain", decision.hash, "--data-dir", str(data_dir)
    )
    assert plain.returncode == 0, plain.stderr
    assert "unresolved_source_ref" in plain.stdout
    assert f"-> {SOURCE_REF_MISSING}" in plain.stdout


# ---------------------------------------------------------------------------
# 5. Existence is not relevance (Grok adversarial input 2)
# ---------------------------------------------------------------------------

def test_off_topic_but_real_source_ref_stays_resolved_with_no_relevance_claim(
    tmp_path,
):
    """A real entry that has nothing to do with the decision still RESOLVES.

    DSM has no mechanism for judging semantic support and must not imply one.
    This test pins that: the report may not describe the ref as relevant,
    valid, supporting, or true.
    """
    data_dir = tmp_path / "data"
    storage = Storage(data_dir=str(data_dir))
    off_topic = record_fact(GROK_OFF_TOPIC_STATEMENT, storage=storage)
    decision = record_decision(
        "Roll back the payment gateway.",
        source_refs=[{"shard": off_topic.shard, "entry_hash": off_topic.hash}],
        storage=storage,
    )

    explanation = explain_decision(decision.hash, storage=storage)
    assert _statuses(explanation) == {
        (off_topic.shard, off_topic.hash): SOURCE_REF_RESOLVED
    }

    result = _run_dsm(
        "memory", "explain", decision.hash, "--data-dir", str(data_dir), "--json"
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)

    assert payload["source_refs"][0]["status"] == SOURCE_REF_RESOLVED
    assert payload["warnings"] == []

    markdown = render_explain_markdown(payload)

    # The only verdict attached to a source ref is its existence state. No
    # line about a ref may label it relevant, valid, supporting, or true.
    ref_lines = [
        line.lower()
        for line in markdown.splitlines()
        if "entry_hash=" in line
    ]
    assert ref_lines
    for line in ref_lines:
        assert "resolved" in line
        for overclaim in ("relevant", "valid", "supporting", "trusted", "true"):
            assert overclaim not in line, f"source ref line over-claims: {line!r}"

    # And the report states the boundary explicitly.
    assert (
        "RESOLVED does not mean relevant, supporting, or true" in markdown
    )


# ---------------------------------------------------------------------------
# 6. Legacy behaviour without source_refs is unchanged
# ---------------------------------------------------------------------------

def test_decision_without_source_refs_is_unchanged(tmp_path):
    data_dir = tmp_path / "data"
    storage = Storage(data_dir=str(data_dir))
    fact = record_fact("DSM entries are hash-chained.", storage=storage)
    decision = record_decision(
        "Answer with a DSM-backed justification.",
        depends_on=[fact.hash],
        storage=storage,
    )

    explanation = explain_decision(decision.hash, storage=storage)
    assert explanation["source_ref_status"] == []

    result = _run_dsm(
        "memory", "explain", decision.hash, "--data-dir", str(data_dir), "--json"
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)

    assert payload["source_refs"] == []
    assert payload["warnings"] == []
    assert render_explain_markdown(payload).count("- None") >= 1


# ---------------------------------------------------------------------------
# 7. Resolution is read-only: verify and the hash chain are untouched
# ---------------------------------------------------------------------------

def test_source_ref_resolution_does_not_mutate_the_shard(tmp_path):
    """Resolution reads. It must not append, rewrite, or re-pin anything."""
    from dsm import verify as dsm_verify

    data_dir = tmp_path / "data"
    storage = Storage(data_dir=str(data_dir))
    record_fact(GROK_OFF_TOPIC_STATEMENT, storage=storage)
    decision = record_decision(
        "Ship the migration on Friday.",
        source_refs=[
            {"shard": "agent_memory", "entry_hash": GROK_NONEXISTENT_HASH}
        ],
        storage=storage,
    )

    before = dsm_verify.verify_shard(storage, "agent_memory")
    before_tip = [e.hash for e in storage.read("agent_memory", limit=1000)]

    explain_decision(decision.hash, storage=storage)
    explain_decision(decision.hash, storage=storage)

    after = dsm_verify.verify_shard(storage, "agent_memory")
    after_tip = [e.hash for e in storage.read("agent_memory", limit=1000)]

    assert before_tip == after_tip
    assert str(before["status"]) == str(after["status"])
    assert before["total_entries"] == after["total_entries"]
    assert after["tampered"] == 0
    assert after["chain_breaks"] == 0
