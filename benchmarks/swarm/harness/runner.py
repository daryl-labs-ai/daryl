"""Local deterministic runner (B3) — one case × one condition → audited artifacts.

Composes the frozen pieces without redefining any semantics: the WALK owns the
common event log (B2), prompts follow the three-level hash contract (B3,
`prompts.py`), the FakeProvider is deterministic, and every Swarm append goes
through the bounded writer via the condition's recorder.

Artifacts written under ``out_dir`` (audit material, NEVER a second canonical
source — no manual mutation, no "corrected" file may feed scoring):

- ``manifest.json``          validated RunManifest
- ``eventlog.jsonl``         the common event log
- ``provider_calls.jsonl``   raw provider outputs, verbatim
- ``receipts.jsonl``         recorder receipts
- ``prompt_records.json``    the three-level hashes per agent step
- ``projection.json``        replay projection (B′/B)
- ``verify.json``            verify_shard report (B′/B)
- ``provider_stats.json``    deterministic token totals per role
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from dsm.status import VerifyStatus
from dsm.verify import verify_shard

from prl.store.dsm_commit import PRLStore
from prl.swarm import from_swarm_entry, project_run, swarm_shard_name
from prl.swarm.replay import RunProjection
from prl.types import Carrier

from .cases import BenchmarkCase, CaseEvent
from .eventlog import EventLog
from .manifest import (
    Budget,
    Condition,
    Grounding,
    InstanceRef,
    Models,
    Outcome,
    RunManifest,
    Topology,
)
from .prompts import (
    DEFAULT_GROUNDING_BLOCK,
    GroundingBlock,
    PromptRecord,
    base_prompt,
    effective_prompt,
    prompt_hash,
)
from .provider import FakeProvider, ProviderCall
from .recorder import (
    BaseRecorder,
    NoOpRecorder,
    OrchestratorEmitter,
    RecorderReceipt,
    SwarmRecorder,
)
from .walk import walk_case

AGENT_ROLES = frozenset({"planner", "worker", "reviewer", "reconciler"})

# Deterministic default timestamp: the runner is a fixture-driven instrument;
# live phases pass the real clock explicitly.
FIXED_STARTED_AT = "2026-07-22T12:00:00.000Z"


def _step_key(event: CaseEvent) -> str:
    return f"{event.role}|{event.step_kind}|{event.task_ref}|{event.attempt}"


def _build_recorder(condition: Condition, store: PRLStore | None) -> BaseRecorder:
    if condition == "A":
        return NoOpRecorder()
    assert store is not None
    return OrchestratorEmitter(store) if condition == "Bprime" else SwarmRecorder(store)


@dataclass(frozen=True)
class RunResult:
    manifest: RunManifest
    log: EventLog
    receipts: tuple[RecorderReceipt, ...]
    calls: tuple[ProviderCall, ...]
    prompt_records: tuple[PromptRecord, ...]
    projection: RunProjection | None
    out_dir: Path


def run_case(
    case: BenchmarkCase,
    condition: Condition,
    out_dir: Path,
    *,
    seed: int | None = None,
    grounding_block: GroundingBlock = DEFAULT_GROUNDING_BLOCK,
    started_at: str = FIXED_STARTED_AT,
    starting_commit: str = "0000000",
) -> RunResult:
    """Execute one case under one condition with the FakeProvider. Zero cost."""
    from dsm.core.storage import Storage  # benchmarks/ tier; recorders never see it

    seed = case.seed if seed is None else seed
    block = grounding_block if condition == "B" else None
    provider = FakeProvider(seed)
    out_dir.mkdir(parents=True, exist_ok=True)

    store: PRLStore | None = None
    if condition in ("Bprime", "B"):
        store = PRLStore(Storage(data_dir=str(out_dir / "dsm")))
    recorder = _build_recorder(condition, store)

    calls: list[ProviderCall] = []
    prompt_records: list[PromptRecord] = []

    def _prompt_hash_for(event: CaseEvent) -> str:
        if event.role not in AGENT_ROLES:
            return ""
        base = base_prompt(case, event, seed)
        effective = effective_prompt(base, condition, block)
        call = provider.complete(event.uid, effective)
        calls.append(call)
        prompt_records.append(
            PromptRecord(
                step_key=_step_key(event),
                base_prompt_hash=prompt_hash(base),
                effective_prompt_hash=prompt_hash(effective),
                grounding_block_hash=block.block_hash() if block else "",
            )
        )
        return prompt_hash(effective)

    log, receipts = walk_case(case, recorder, prompt_hash_fn=_prompt_hash_for)

    # -- replay + integrity (B′/B), from the store alone ----------------------
    projection: RunProjection | None = None
    verify_report: dict | None = None
    if store is not None:
        shard = swarm_shard_name(case.swarm_run_id)
        entries = list(reversed(store._storage.read(shard, limit=10_000)))
        records = [from_swarm_entry(e) for e in entries]
        projection = project_run(records, swarm_run_id=case.swarm_run_id)
        verify_report = verify_shard(store._storage, shard)

    # -- manifest --------------------------------------------------------------
    prompt_hashes: dict[str, str] = {}
    for pr in prompt_records:
        prompt_hashes[f"base::{pr.step_key}"] = pr.base_prompt_hash
        prompt_hashes[f"effective::{pr.step_key}"] = pr.effective_prompt_hash

    manifest = RunManifest(
        run_id=f"run:{case.case_id}:seed{seed}:{condition}",
        pair_id=f"{case.case_id}:seed{seed}",
        condition=condition,
        instance=InstanceRef(
            id=case.case_id,
            instance_ref=f"benchmarks/swarm/cases/{case.case_id}.json",
        ),
        starting_commit=starting_commit if len(starting_commit) >= 7 else "0000000",
        orchestrator_id="orch:bench-fake-v1",
        models=Models(
            planner=Carrier(provider="fake", model=f"fake-planner-s{seed}"),
            workers=(Carrier(provider="fake", model=f"fake-worker-s{seed}"),),
            reviewers=(Carrier(provider="fake", model=f"fake-reviewer-s{seed}"),),
        ),
        budget=Budget(max_total_tokens=1_000_000, max_usd=0.0, max_wall_seconds=600),
        seed=seed,
        topology=Topology(planners=1, workers=1, reviewers=1),
        prompt_hashes=prompt_hashes,
        grounding_block_text=block.text if block else "",
        grounding_block_hash=block.block_hash() if block else "",
        grounding=(
            None
            if condition == "A"
            else Grounding(
                emitter="orchestrator_emitter" if condition == "Bprime" else "swarm_recorder",
                shard=swarm_shard_name(case.swarm_run_id),
                verify_status=(
                    verify_report["status"].value if verify_report is not None else None
                ),
                replay_success=projection is not None,
            )
        ),
        outcome=Outcome(termination="success"),
        artifacts={
            "eventlog": "eventlog.jsonl",
            "provider_calls": "provider_calls.jsonl",
            "receipts": "receipts.jsonl",
            "prompt_records": "prompt_records.json",
            **({"projection": "projection.json", "verify": "verify.json"} if store else {}),
        },
        started_at=started_at,
    )

    # -- artifacts -------------------------------------------------------------
    (out_dir / "manifest.json").write_text(manifest.model_dump_json(indent=2) + "\n")
    (out_dir / "eventlog.jsonl").write_text(log.to_jsonl())
    (out_dir / "provider_calls.jsonl").write_text(
        "".join(c.model_dump_json() + "\n" for c in calls)
    )
    (out_dir / "receipts.jsonl").write_text(
        "".join(r.model_dump_json() + "\n" for r in receipts)
    )
    (out_dir / "prompt_records.json").write_text(
        json.dumps([pr.model_dump() for pr in prompt_records], indent=2) + "\n"
    )
    tokens_by_role: dict[str, dict[str, int]] = {}
    for c in calls:
        slot = tokens_by_role.setdefault(c.role, {"tokens_in": 0, "tokens_out": 0, "calls": 0})
        slot["tokens_in"] += c.tokens_in
        slot["tokens_out"] += c.tokens_out
        slot["calls"] += 1
    (out_dir / "provider_stats.json").write_text(json.dumps(tokens_by_role, indent=2) + "\n")
    if projection is not None and verify_report is not None:
        (out_dir / "projection.json").write_text(
            json.dumps(
                {
                    "swarm_run_id": projection.swarm_run_id,
                    "run_status": projection.run_status,
                    "tasks": {t: v.model_dump() if hasattr(v, "model_dump") else v.__dict__ for t, v in projection.tasks.items()},
                    "diagnostics": [d.__dict__ for d in projection.diagnostics],
                    "derived_conflicts": [d.__dict__ for d in projection.derived_conflicts],
                },
                indent=2,
                default=str,
            )
            + "\n"
        )
        assert verify_report["status"] == VerifyStatus.OK, "unreplayable run artifacts"
        (out_dir / "verify.json").write_text(
            json.dumps({k: str(v) for k, v in verify_report.items()}, indent=2) + "\n"
        )

    return RunResult(
        manifest=manifest,
        log=log,
        receipts=tuple(receipts),
        calls=tuple(calls),
        prompt_records=tuple(prompt_records),
        projection=projection,
        out_dir=out_dir,
    )
