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

from dsm.core.models import Entry
from dsm.core.storage import Storage

from ..index.mapper import ProjectMap
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


@dataclass(frozen=True)
class CommitResult:
    run_id: str
    project_id: str
    shard: str
    n_entries: int
    tip_hash: str  # hash of the last appended entry (shard chain tip after commit)


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
