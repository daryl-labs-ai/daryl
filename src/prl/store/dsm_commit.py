"""Commit a ProjectMap into DSM as tamper-evident Entries (P3).

Decision record: ADR_PRL_RR_BINDING §8.

* Write path = ``Storage.append`` (not ``SessionGraph.execute_action``).
* One shard per project: ``prl_<short_project_id>`` (filesystem-safe slug).
* Timestamp bridge: ``EntryDraft.timestamp`` (ISO-8601 ``"…Z"`` string) →
  ``Entry.timestamp`` (datetime) via ``fromisoformat(ts.replace("Z","+00:00"))``.
* ``run_id`` (harvest run) is generated here and carried as ``Entry.session_id``.
* No ``SessionGraph`` session, no ``Storage.read`` (reads are RR's job, P5).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import resources

from dsm.core.models import Entry
from dsm.core.storage import Storage

from ..config import PRLConfig
from ..exceptions import PRLValidationError
from ..index.mapper import ProjectMap
from ..swarm.types import SCHEMA_VERSION as SWARM_SCHEMA_VERSION
from ..swarm.types import SWARM_ACTION, SWARM_ACTIONS, from_swarm_entry
from ..types import EntryDraft, PRLNode, to_entry


def prl_shard_name(project_id: str) -> str:
    """Filesystem-safe per-project shard name.

    ``project_id`` is ``"sha256:<hex>"``; the ``:`` is unsafe in a path, so we
    take the first 16 alphanumeric characters of the hash tail:
    ``prl_<hex16>``. Deterministic; collision-negligible for personal use.
    """
    tail = project_id.split(":")[-1]
    safe = "".join(ch for ch in tail if ch.isalnum())[:16]
    return f"prl_{safe}"


def new_run_id() -> str:
    """A unique harvest-run id, carried as ``Entry.session_id`` for the run."""
    return f"prl_run_{int(datetime.now(timezone.utc).timestamp())}_{uuid.uuid4().hex[:8]}"


def open_store(config: PRLConfig) -> "PRLStore":
    """Build a :class:`PRLStore` backed by a ``Storage`` at ``config.storage_dir``.

    Kept in this module (the registered ``LEGITIMATE_WRITERS`` entry) so callers
    such as the CLI never import ``dsm.core.storage.Storage`` directly and thus
    never need their own writer registration.
    """
    return PRLStore(Storage(data_dir=str(config.storage_dir)))


def open_storage(config: PRLConfig) -> Storage:
    """Raw ``Storage`` at ``config.storage_dir``, for **RR read consumers** (e.g.
    ``ConsultationQuery`` in R-consult v2). Kept here (the registered writer module) so
    read callers never import ``dsm.core.storage.Storage`` directly — they receive the
    instance and pass it to RR, which is the only read path (ADR-0001). Not a new writer."""
    return Storage(data_dir=str(config.storage_dir))


def _draft_to_entry(draft: EntryDraft) -> Entry:
    """Bridge an :class:`EntryDraft` (P0) to a kernel ``Entry``.

    The only real conversion is the timestamp: the draft carries an ISO-8601
    ``"…Z"`` string; the kernel ``Entry`` wants a ``datetime``. ``id`` is freshly
    minted; ``hash`` / ``prev_hash`` are assigned by ``Storage.append``.
    """
    ts = datetime.fromisoformat(draft.timestamp.replace("Z", "+00:00"))
    return Entry(
        id=str(uuid.uuid4()),
        timestamp=ts,
        session_id=draft.session_id,
        source=draft.source,
        content=draft.content,
        shard=draft.shard,
        hash="",
        prev_hash=None,
        metadata=dict(draft.metadata),
        version=draft.version,
    )


# Dedicated shard for consultation acts (ADR-PRL-0008). RR reads by action_name across
# shards, so the shard choice does not affect read; it just groups the acts.
CONSULTATION_SHARD = "prl_consultations"


@dataclass(frozen=True)
class CommitResult:
    run_id: str
    project_id: str
    shard: str
    n_entries: int
    tip_hash: str  # hash of the last appended entry (shard chain tip after commit)


# ---------------------------------------------------------------------------
# Swarm bounded append (v0.1) — the ONE physical Storage.append call site for
# swarm records, kept in this already-registered LEGITIMATE_WRITERS module.
# ---------------------------------------------------------------------------

_kernel_version_cache: str | None = None


def _dsm_kernel_version() -> str:
    """Read the real frozen-kernel version from the packaged marker file
    ``dsm/core/KERNEL_VERSION`` (line ``DSM_KERNEL_VERSION = "<v>"``).

    The value is stamped into ``metadata['kernel_version']`` of every swarm
    entry at the append boundary — the writer is the kernel-facing module, so
    the kernel version is a write-time fact, not a pure-model concern. Cached
    after first read; raises :class:`PRLValidationError` if the marker cannot
    be resolved (never silently ``"unknown"``).
    """
    global _kernel_version_cache
    if _kernel_version_cache is None:
        try:
            text = (resources.files("dsm.core") / "KERNEL_VERSION").read_text()
            line = next(
                ln for ln in text.splitlines() if ln.startswith("DSM_KERNEL_VERSION")
            )
            _kernel_version_cache = line.split("=", 1)[1].strip().strip('"')
        except (OSError, StopIteration, IndexError) as exc:
            raise PRLValidationError(
                f"cannot resolve DSM_KERNEL_VERSION from dsm/core/KERNEL_VERSION: {exc}"
            ) from exc
    return _kernel_version_cache


@dataclass(frozen=True)
class SwarmActResult:
    """Result of committing a single swarm record (bounded write path v0.1)."""

    swarm_run_id: str
    shard: str
    action_name: str
    entry_id: str
    tip_hash: str  # hash of the appended entry (certification: hash + prev_hash chain)


def _validate_swarm_draft(draft: EntryDraft) -> str:
    """Bounded-writer gate: refuse anything that is not a validated swarm
    draft. Returns the draft's ``action_name``. Raises
    :class:`PRLValidationError` BEFORE any append on the first violation.

    Checks (closed by construction — the action set lives in
    ``prl.swarm.types`` only):
      * ``source == "swarm"`` — no PRL/arbitrary source may borrow this path;
      * ``version`` and ``metadata['schema_version']`` == ``swarm.v0.1``;
      * ``metadata['action_name']`` ∈ the closed ``SWARM_ACTIONS`` set;
      * ``content`` re-validates against the swarm model for that action
        (``from_swarm_entry`` — the payload is proven, not trusted);
      * the decoded record's kind maps back to the same action, and its
        ``swarm_run_id`` matches ``session_id`` (run-scoped replay integrity).
    """
    if draft.source != "swarm":
        raise PRLValidationError(
            f"commit_swarm_entry: draft.source must be 'swarm', got {draft.source!r}"
        )
    if draft.version != SWARM_SCHEMA_VERSION:
        raise PRLValidationError(
            f"commit_swarm_entry: draft.version must be {SWARM_SCHEMA_VERSION!r}, "
            f"got {draft.version!r}"
        )
    metadata = draft.metadata or {}
    action = metadata.get("action_name")
    if action not in SWARM_ACTIONS:
        raise PRLValidationError(
            f"commit_swarm_entry: action_name {action!r} is not in the closed "
            f"swarm action set {sorted(SWARM_ACTIONS)}"
        )
    if metadata.get("schema_version") != SWARM_SCHEMA_VERSION:
        raise PRLValidationError(
            f"commit_swarm_entry: metadata['schema_version'] must be "
            f"{SWARM_SCHEMA_VERSION!r}, got {metadata.get('schema_version')!r}"
        )
    record = from_swarm_entry(draft)  # raises if the payload fails its model
    if SWARM_ACTION[record.kind] != action:
        raise PRLValidationError(
            f"commit_swarm_entry: payload kind {record.kind!r} does not match "
            f"action_name {action!r}"
        )
    run_id = getattr(record, "swarm_run_id", None)
    if run_id != draft.session_id:
        raise PRLValidationError(
            f"commit_swarm_entry: session_id {draft.session_id!r} must equal the "
            f"record's swarm_run_id {run_id!r}"
        )
    return action


@dataclass(frozen=True)
class ActResult:
    """Result of committing a single Knowledge Act (e.g. a consultation, ADR-PRL-0008)."""

    run_id: str
    shard: str
    act_id: str
    tip_hash: str  # hash of the appended entry (certification: hash + prev_hash chain)


class PRLStore:
    """Persists a :class:`ProjectMap` into DSM. Write-only."""

    def __init__(self, storage: Storage):
        self._storage = storage

    def commit_map(self, pmap: ProjectMap, *, run_id: str | None = None) -> CommitResult:
        """Append every node/edge of *pmap* to the project's PRL shard.

        Order: project, files, commits, edges. Each becomes one ``Entry`` whose
        ``metadata['action_name']`` is the PRL kind (RR ``action_index`` hook) and
        whose ``content`` is the canonical payload. Returns the run id, shard,
        entry count, and the shard chain tip hash after the commit.
        """
        run_id = run_id or new_run_id()
        shard = prl_shard_name(pmap.project.project_id)
        nodes: list[PRLNode] = [pmap.project, *pmap.files, *pmap.commits, *pmap.edges]
        tip_hash = ""
        count = 0
        for node in nodes:
            draft: EntryDraft = to_entry(node, shard=shard, session_id=run_id)
            written = self._storage.append(_draft_to_entry(draft))
            tip_hash = written.hash
            count += 1
        return CommitResult(
            run_id=run_id,
            project_id=pmap.project.project_id,
            shard=shard,
            n_entries=count,
            tip_hash=tip_hash,
        )

    def commit_act(
        self, node: PRLNode, *, run_id: str | None = None, shard: str = CONSULTATION_SHARD
    ) -> ActResult:
        """Append a single Knowledge Act (e.g. a ``ConsultationNode``) to its shard.

        Same write path as :meth:`commit_map` (one ``Entry`` via ``Storage.append``,
        ``metadata['action_name']`` = the PRL kind), so the act is certified (hash +
        prev_hash chain) and readable via RR by its ``action_name``. Lives in this
        already-registered writer module, so no new ``LEGITIMATE_WRITERS`` entry.
        """
        run_id = run_id or new_run_id()
        draft: EntryDraft = to_entry(node, shard=shard, session_id=run_id)
        written = self._storage.append(_draft_to_entry(draft))
        act_id = getattr(node, "consultation_id", "") or ""
        return ActResult(run_id=run_id, shard=shard, act_id=act_id, tip_hash=written.hash)

    def commit_swarm_entry(self, draft: EntryDraft) -> SwarmActResult:
        """Append ONE validated swarm :class:`EntryDraft` (bounded path, v0.1).

        This is deliberately NOT a general ``commit_draft``: it accepts only
        drafts produced by ``prl.swarm.types.to_swarm_entry`` — source
        ``"swarm"``, contract version ``swarm.v0.1``, an ``action_name`` from
        the closed swarm set, and a payload that re-validates against the
        corresponding swarm model (:func:`_validate_swarm_draft`). Any other
        draft is refused with :class:`PRLValidationError` before any append.

        The real ``DSM_KERNEL_VERSION`` is stamped into
        ``metadata['kernel_version']`` here, at the kernel boundary. Same write
        path as :meth:`commit_map` / :meth:`commit_act` (``Storage.append`` in
        this registered writer module), so the record is certified (hash +
        prev_hash chain) and readable via RR by its ``action_name``.
        """
        action = _validate_swarm_draft(draft)
        stamped = draft.model_copy(
            update={
                "metadata": {**draft.metadata, "kernel_version": _dsm_kernel_version()}
            }
        )
        written = self._storage.append(_draft_to_entry(stamped))
        return SwarmActResult(
            swarm_run_id=draft.session_id,
            shard=draft.shard,
            action_name=action,
            entry_id=written.id,
            tip_hash=written.hash,
        )
