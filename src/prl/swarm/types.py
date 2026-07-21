"""DSM Swarm — record models and the DSM-Entry mapping (v0.1, minimal slice).

Single source of truth for the shape of every Swarm record and for how those
records are encoded into / decoded from the **existing** DSM ``Entry`` envelope,
so Read Relay (RR) can index and replay them — exactly as :mod:`prl.types` does
for PRL nodes.

Contract (mirrors ``prl.types``, transplanted from the Swarm v0.1 candidate
package after reconciliation against this repository):

* One **discriminated envelope** (kernel ``Entry``): ``content`` = canonical
  JSON (via :mod:`prl._canonical`, which composes the repository primitive
  ``dsm_primitives.canonical_json``) of a payload model;
  ``metadata['action_name']`` = ``"swarm.<kind>"`` (RR ``action_index`` hook);
  ``metadata['schema_version']`` = the payload contract version;
  ``session_id`` = ``swarm_run_id`` (run-scoped replay).
* Identity is **reused** from :mod:`prl.types` (``Carrier``, ADR-PRL-0009): a
  logical ``agent_id`` and an execution carrier (``provider``/``model``/
  ``adapter``). ``agent_id`` is never derived from the carrier —
  ``agent_id != model_id`` is structural, not conventional.
* **No kernel import.** This module is pure models + the ``to_swarm_entry`` /
  ``from_swarm_entry`` mapping. It never writes; the one physical append call
  site for swarm records is the registered ``prl.store`` writer
  (``PRLStore.commit_swarm_entry`` in ``prl/store/dsm_commit.py``), which also
  stamps ``metadata['kernel_version']`` at the kernel boundary.

The action set below is CLOSED and centralized here: the bounded writer refuses
any ``action_name`` outside :data:`SWARM_ACTIONS`, and every action maps to
exactly one model (:data:`ACTION_TO_MODEL`). v0.1 minimal slice ships ``run``
and ``task`` only; further record kinds are added here (and only here) with
their models.
"""

from __future__ import annotations

import json
from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .._canonical import canonical_bytes, utc_now_ms
from ..exceptions import PRLEntryMappingError, PRLValidationError
from ..types import Carrier, EntryDraft

# Contract version stamped on every record + envelope.
SCHEMA_VERSION = "swarm.v0.1"

# ---------------------------------------------------------------------------
# Enumerated string literals
# ---------------------------------------------------------------------------

SwarmKind = Literal["run", "task"]
Role = Literal["planner", "worker", "reviewer", "reconciler", "other"]
RunStatus = Literal["open", "closed", "aborted"]
TaskStatus = Literal[
    "delegated", "in_progress", "claimed_done", "accepted", "abandoned", "blocked",
]

# kind -> metadata["action_name"] (RR action_index hook). THE closed action set:
# the bounded writer validates against SWARM_ACTIONS derived from this mapping.
SWARM_ACTION: dict[str, str] = {
    "run": "swarm.run",
    "task": "swarm.task",
}
SWARM_ACTIONS: frozenset[str] = frozenset(SWARM_ACTION.values())
ACTION_TO_MODEL: dict[str, type[BaseModel]] = {}  # filled after model definitions


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


class SwarmRun(BaseModel):
    """One coordinated multi-agent execution (opens the run's shard)."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["run"] = "run"
    schema_version: str = SCHEMA_VERSION
    swarm_run_id: str
    subject_id: str
    orchestrator_id: str
    objective: str
    started_at: str = Field(default_factory=utc_now_ms)
    ended_at: str | None = None
    status: RunStatus = "open"
    trace_id: str | None = None
    budget_constraints: dict[str, Any] = Field(default_factory=dict)
    environment_ref: str | None = None
    org_id: str | None = None  # owning org (ADR-PRL-0010); declared, never derived


class TaskNode(BaseModel):
    """A delegated unit of work. Parentage is recorded delegation, not causal
    certainty (``task parentage != causal certainty``)."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["task"] = "task"
    schema_version: str = SCHEMA_VERSION
    task_node_id: str
    swarm_run_id: str
    role: Role
    objective: str
    status: TaskStatus
    parent_task_node_id: str | None = None
    assigned_agent_id: str | None = None     # logical contributor (never from carrier)
    assigned_carrier: Carrier | None = None  # execution carrier-of-record (ADR-0009)
    acceptance_criteria: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    created_at: str = Field(default_factory=utc_now_ms)


SwarmRecord = Union[SwarmRun, TaskNode]

ACTION_TO_MODEL.update(
    {
        "swarm.run": SwarmRun,
        "swarm.task": TaskNode,
    }
)


# ---------------------------------------------------------------------------
# Envelope mapping (mirrors prl.types.to_entry / from_entry)
# ---------------------------------------------------------------------------


def swarm_shard_name(swarm_run_id: str) -> str:
    """Filesystem-safe per-run shard name: ``swarm_<slug16>``.

    Same construction rule as ``prl.store.prl_shard_name``: first 16
    alphanumeric characters of the id tail. Deterministic; one shard = one hash
    chain to verify per run.
    """
    tail = swarm_run_id.split(":")[-1]
    safe = "".join(ch for ch in tail if ch.isalnum())[:16]
    if not safe:
        raise PRLValidationError(
            f"swarm_run_id has no alphanumeric tail: {swarm_run_id!r}"
        )
    return f"swarm_{safe}"


def to_swarm_entry(record: SwarmRecord, *, shard: str | None = None) -> EntryDraft:
    """Encode a Swarm record into an :class:`EntryDraft` (does not write).

    ``content`` is the canonical JSON of the record; ``metadata['action_name']``
    is ``swarm.<kind>`` (RR hook) and ``metadata['schema_version']`` the
    contract version. ``session_id`` groups by run (``swarm_run_id``) so RR can
    replay a run. ``shard`` defaults to ``swarm_shard_name(run_id)``.
    ``metadata['kernel_version']`` is deliberately NOT stamped here: the
    registered writer stamps the real kernel version at the append boundary.
    """
    run_id = getattr(record, "swarm_run_id", None)
    if not run_id:
        raise PRLValidationError(
            f"{type(record).__name__} has no swarm_run_id; cannot place it in a run shard"
        )
    payload = record.model_dump(mode="json", exclude_none=True)
    content = canonical_bytes(payload).decode("utf-8")
    return EntryDraft(
        session_id=run_id,
        source="swarm",
        content=content,
        shard=shard or swarm_shard_name(run_id),
        metadata={
            "action_name": SWARM_ACTION[record.kind],
            "schema_version": record.schema_version,
        },
        timestamp=getattr(record, "created_at", None)
        or getattr(record, "started_at", None)
        or utc_now_ms(),
        version=SCHEMA_VERSION,
    )


def _read_attr(entry: Any, name: str) -> Any:
    """Duck-typed accessor: works for a dict, an EntryDraft, or a kernel Entry."""
    if isinstance(entry, dict):
        return entry.get(name)
    return getattr(entry, name, None)


def from_swarm_entry(entry: Any) -> SwarmRecord:
    """Decode a DSM Entry (kernel ``Entry``, :class:`EntryDraft`, or dict) back
    into the corresponding Swarm record. Inverse of :func:`to_swarm_entry`.

    Raises
    ------
    PRLEntryMappingError
        Unknown / missing ``metadata['action_name']`` or non-decodable content.
    PRLValidationError
        ``content`` decodes but does not satisfy the target model.
    """
    metadata = _read_attr(entry, "metadata") or {}
    action = metadata.get("action_name") if isinstance(metadata, dict) else None
    model = ACTION_TO_MODEL.get(action) if action is not None else None
    if model is None:
        raise PRLEntryMappingError(f"unknown or missing swarm action_name: {action!r}")

    content = _read_attr(entry, "content")
    try:
        data = json.loads(content)
    except (TypeError, ValueError) as exc:
        raise PRLEntryMappingError(
            f"content is not decodable canonical JSON: {exc}"
        ) from exc

    try:
        return model(**data)
    except (ValidationError, ValueError) as exc:
        raise PRLValidationError(str(exc)) from exc
