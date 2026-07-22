"""B3 — deterministic runner + FakeProvider: the G2 recomposition gate.

G2 is a RECOMPOSITION check (frozen at B2 validation), not a difference check:
    effective_prompt(B) == base_prompt + delimited(declared block)
    base_prompt_hash(A) == base_prompt_hash(B′) == base_prompt_hash(B)
so a business-prompt change can never hide inside "the declared block".

Also proves: G1 holds with prompts wired (B′ trace == A trace exactly), the
trace of B differs from A ONLY by effective prompt hashes on agent steps,
full-run determinism at the artifact-byte level, manifest validity per
condition, and the audited artifact set (no mutated/"corrected" file feeds
anything).
"""

from __future__ import annotations

import json

import pytest

from benchmarks.swarm.harness.cases import load_cases
from benchmarks.swarm.harness.prompts import (
    DEFAULT_GROUNDING_BLOCK,
    GroundingBlock,
    base_prompt,
    effective_prompt,
    prompt_hash,
)
from benchmarks.swarm.harness.runner import AGENT_ROLES, run_case

CASES = {c.case_id: c for c in load_cases()}
NOMINAL = CASES["c01-nominal"]
ARTIFACTS = {
    "manifest.json", "eventlog.jsonl", "provider_calls.jsonl", "receipts.jsonl",
    "prompt_records.json", "provider_stats.json",
}


def _run_all(tmp_path, case=NOMINAL):
    return {
        cond: run_case(case, cond, tmp_path / cond)
        for cond in ("A", "Bprime", "B")
    }


# --- G2: three-level hashes + recomposition ----------------------------------


def test_g2_base_hashes_identical_across_conditions(tmp_path):
    results = _run_all(tmp_path)
    base_maps = {
        cond: {pr.step_key: pr.base_prompt_hash for pr in r.prompt_records}
        for cond, r in results.items()
    }
    assert base_maps["A"] == base_maps["Bprime"] == base_maps["B"]
    assert len(base_maps["A"]) == sum(1 for e in NOMINAL.events if e.role in AGENT_ROLES)


def test_g2_effective_is_exact_recomposition(tmp_path):
    result_b = run_case(NOMINAL, "B", tmp_path / "B")
    block = DEFAULT_GROUNDING_BLOCK
    by_key = {pr.step_key: pr for pr in result_b.prompt_records}
    for event in NOMINAL.events:
        if event.role not in AGENT_ROLES:
            continue
        key = f"{event.role}|{event.step_kind}|{event.task_ref}|{event.attempt}"
        base = base_prompt(NOMINAL, event, NOMINAL.seed)
        pr = by_key[key]
        # recomposition, recomputed independently of the runner
        assert pr.base_prompt_hash == prompt_hash(base)
        assert pr.effective_prompt_hash == prompt_hash(base + block.delimited())
        assert pr.grounding_block_hash == block.block_hash()
    # manifest carries the declared block verbatim + its separate hash
    assert result_b.manifest.grounding_block_text == block.text
    assert result_b.manifest.grounding_block_hash == block.block_hash()


def test_g2_a_and_bprime_effective_equals_base(tmp_path):
    for cond in ("A", "Bprime"):
        result = run_case(NOMINAL, cond, tmp_path / cond)
        for pr in result.prompt_records:
            assert pr.effective_prompt_hash == pr.base_prompt_hash
            assert pr.grounding_block_hash == ""
        assert result.manifest.grounding_block_text == ""
        assert result.manifest.grounding_block_hash == ""


def test_g2_business_change_cannot_hide_in_the_block():
    # the block is delimited canonically and refuses nested delimiters,
    # so smuggling "extra business instructions + fake delimiters" fails
    with pytest.raises(Exception, match="delimiters"):
        GroundingBlock(text="do the task differently\n<<<DSM-GROUNDING v0.1>>>")
    with pytest.raises(Exception, match="grounding block"):
        effective_prompt("base", "B", None)  # B without a declared block
    with pytest.raises(Exception, match="must not carry"):
        effective_prompt("base", "A", DEFAULT_GROUNDING_BLOCK)


# --- G1 with prompts wired ---------------------------------------------------


def test_g1_holds_with_prompts(tmp_path):
    results = _run_all(tmp_path)
    assert results["Bprime"].log.trace() == results["A"].log.trace()
    assert results["Bprime"].log.trace_hash() == results["A"].log.trace_hash()


def test_b_trace_differs_only_by_effective_prompt_hashes(tmp_path):
    results = _run_all(tmp_path)
    trace_a, trace_b = results["A"].log.trace(), results["B"].log.trace()
    assert len(trace_a) == len(trace_b)
    diffs = 0
    for entry_a, entry_b in zip(trace_a, trace_b):
        # structure identical: (role, step_kind, task_ref, attempt, ..., tools)
        assert entry_a[:4] == entry_b[:4]
        assert entry_a[5] == entry_b[5]
        if entry_a[4] != entry_b[4]:
            diffs += 1
            assert entry_a[4] != "" and entry_b[4] != ""  # only agent steps differ
    assert diffs == sum(1 for e in NOMINAL.events if e.role in AGENT_ROLES)


# --- determinism at artifact level -------------------------------------------


def test_full_run_deterministic_to_the_byte(tmp_path):
    r1 = run_case(NOMINAL, "B", tmp_path / "r1")
    r2 = run_case(NOMINAL, "B", tmp_path / "r2")
    # harness-owned artifacts: byte-identical
    for name in sorted(ARTIFACTS - {"receipts.jsonl"}):
        assert (r1.out_dir / name).read_bytes() == (r2.out_dir / name).read_bytes(), name
    # DSM receipts: entry ids / chain hashes are freshly minted by the kernel
    # at append time (uuid) — deterministic MODULO those fields, and the
    # decoded content is identical (projection equality below)
    def _stable(receipts):
        return [
            {k: v for k, v in json.loads(line).items() if k not in ("entry_id", "tip_hash")}
            for line in receipts.read_text().splitlines()
        ]

    assert _stable(r1.out_dir / "receipts.jsonl") == _stable(r2.out_dir / "receipts.jsonl")
    assert r1.projection == r2.projection


def test_fake_provider_tokens_deterministic(tmp_path):
    r1 = run_case(NOMINAL, "A", tmp_path / "a1")
    r2 = run_case(NOMINAL, "A", tmp_path / "a2")
    assert [c.model_dump() for c in r1.calls] == [c.model_dump() for c in r2.calls]
    assert all(c.tokens_in > 0 and c.tokens_out > 0 for c in r1.calls)


# --- manifests + artifacts ---------------------------------------------------


def test_manifests_validate_per_condition(tmp_path):
    results = _run_all(tmp_path)
    assert results["A"].manifest.grounding is None
    assert results["Bprime"].manifest.grounding.emitter == "orchestrator_emitter"
    assert results["B"].manifest.grounding.emitter == "swarm_recorder"
    for cond in ("Bprime", "B"):
        g = results[cond].manifest.grounding
        assert g.kernel_version == "1.0"
        assert g.verify_status == "OK"
        assert g.replay_success is True


def test_artifact_set_complete_and_audit_only(tmp_path):
    results = _run_all(tmp_path)
    for cond, result in results.items():
        names = {p.name for p in result.out_dir.iterdir() if p.is_file()}
        assert ARTIFACTS <= names, (cond, names)
        if cond == "A":
            assert "projection.json" not in names and "verify.json" not in names
            assert not (result.out_dir / "dsm").exists()
        else:
            assert {"projection.json", "verify.json"} <= names
        # raw provider outputs persisted verbatim
        lines = (result.out_dir / "provider_calls.jsonl").read_text().splitlines()
        assert len(lines) == len(result.calls)
        assert all("response_text" in json.loads(line) for line in lines)


def test_runner_works_on_a_faulted_case_and_projection_carries_diagnostics(tmp_path):
    case = CASES["c03-reviewers-disagree"]
    result = run_case(case, "B", tmp_path / "b")
    assert result.projection is not None
    assert any(d.kind == "reviews_divergent" for d in result.projection.derived_conflicts)
    dumped = json.loads((result.out_dir / "projection.json").read_text())
    assert any(d["kind"] == "reviews_divergent" for d in dumped["derived_conflicts"])
