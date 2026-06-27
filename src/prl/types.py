"""PRL type definitions — nodes, edges, and the DSM-Entry mapping (P0).

This module is the single source of truth for the shape of every PRL object,
and for how those objects are encoded into / decoded from a DSM ``Entry`` so
that Read Relay (RR) can index and resolve them.

Contract (see ``deliverable/ADR_PRL_RR_BINDING.md``)
---------------------------------------------------
RR is **not** a graph store: it is a read-only index over a flat append-only
log of ``Entry`` objects, keyed on fixed axes (session / agent / timeline /
shard / action). Therefore PRL:

* **D-1** — encodes each node/edge as an ``Entry`` whose ``content`` is the
  canonical payload (via :mod:`prl._canonical`, which composes the repository
  primitive ``dsm_primitives.canonical_json``) and whose
  ``metadata['action_name']`` is the PRL record kind (``prl.project``,
  ``prl.file``, ``prl.commit``, ``prl.session``, ``prl.edge``). That
  ``action_name`` is the hook RR's ``action_index`` uses for retrieval.
* ``project_id`` and ``content_hash`` live **inside the payload**, not in any
  RR metadata axis (RR has no such axes). They are only available after a
  ``resolve_entries()`` + :func:`from_entry`.

P0 scope
--------
Pure models + the ``to_entry`` / ``from_entry`` mapping only. **No** filesystem
scan, **no** DSM write, **no** RR access, **no** kernel import. :func:`to_entry`
returns an :class:`EntryDraft` (a plain, not-yet-persisted record); the kernel
assigns ``id`` / ``hash`` / ``prev_hash`` at append time in a later milestone.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ._canonical import canonical_bytes, utc_now_ms
from .exceptions import PRLEntryMappingError, PRLValidationError

# ---------------------------------------------------------------------------
# Enumerated string literals
# ---------------------------------------------------------------------------

NodeType = Literal["project", "file", "commit", "session", "consultation"]
EdgeType = Literal["produced", "modified", "references", "follows", "belongs_to"]
ToolName = Literal["chatgpt", "claude", "cursor", "vscode", "terminal", "other"]

# Consultation mode (ADR-PRL-0008): Observation by default; Proposal only by explicit adapter flag.
ConsultationMode = Literal["observation", "proposal"]

# node_type / edge → metadata["action_name"] (RR action_index hook, D-1)
PRL_ACTION: dict[str, str] = {
    "project": "prl.project",
    "file": "prl.file",
    "commit": "prl.commit",
    "session": "prl.session",
    "edge": "prl.edge",
    "consultation": "prl.consultation",  # ADR-PRL-0008 (R-consult v1)
}
ACTION_TO_MODEL: dict[str, type[BaseModel]] = {}  # filled after model definitions


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


class ProjectNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_type: Literal["project"] = "project"
    project_id: str  # sha256_uri of the declared root path (deterministic)
    root_path: str
    name: str

    @classmethod
    def from_root(cls, root_path: str, name: str | None = None) -> "ProjectNode":
        """Build a ProjectNode with a deterministic ``project_id`` derived purely
        from the path string (no filesystem access — no ``resolve()``)."""
        from ._canonical import sha256_uri

        pid = sha256_uri(canonical_bytes(str(root_path)))
        derived_name = name if name is not None else str(root_path).rstrip("/").split("/")[-1]
        return cls(project_id=pid, root_path=str(root_path), name=derived_name)


class FileNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_type: Literal["file"] = "file"
    path: str  # path relative to the project root
    content_hash: str  # sha256_uri(bytes) — universal join key
    size: int
    mtime_ms: int
    project_id: str


class CommitNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_type: Literal["commit"] = "commit"
    sha: str
    author: str
    ts_ms: int
    message: str
    files: tuple[str, ...] = ()
    project_id: str


class SessionNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_type: Literal["session"] = "session"
    session_id: str
    tool: ToolName
    title: str | None = None
    started_ms: int
    ended_ms: int | None = None
    text_preview: str = ""
    project_id: str | None = None  # None until bound (P7)


class Edge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edge_type: EdgeType
    src_id: str
    dst_id: str
    confidence: float = 1.0  # < 1.0 for probabilistic links (binder, P7)
    evidence: dict[str, str] = Field(default_factory=dict)

    @field_validator("confidence")
    @classmethod
    def _check_confidence(cls, value: float) -> float:
        if not (0.0 <= value <= 1.0):
            raise ValueError(
                f"Edge.confidence must be within [0, 1], got {value!r}"
            )
        return value


class MEF(BaseModel):
    """Minimal Epistemic Frame (ADR-PRL-0004 Ch2) — the non-strippable transport
    contract. All fields are required: a record cannot be constructed without a
    complete MEF, so "MEF complete or refuse" is enforced by the type, not by a
    convention. ``regime`` is a free string here (its exact taxonomy is ADR-0003 /
    open question 8.a — not canonized at this layer)."""

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    regime: str          # e.g. "observed.declared" | "derived.proposed" (v1; see ADR-0003 / 8.a)
    confidence: float
    contested: bool
    producer: str        # attribution: "model via adapter vN" (mandatory, ADR-0007/0008)

    @field_validator("confidence")
    @classmethod
    def _check_confidence(cls, value: float) -> float:
        if not (0.0 <= value <= 1.0):
            raise ValueError(f"MEF.confidence must be within [0, 1], got {value!r}")
        return value

    @field_validator("claim_id", "regime", "producer")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not str(value).strip():
            raise ValueError("MEF claim_id / regime / producer must be non-empty")
        return value


class ConsultationNode(BaseModel):
    """A live agent consultation recorded as an attributed Knowledge Act
    (ADR-PRL-0008). Default ``mode`` is ``observation``; ``proposal`` is set only by
    an explicit adapter decision. Carries a complete :class:`MEF` (non-strippable)."""

    model_config = ConfigDict(extra="forbid")

    node_type: Literal["consultation"] = "consultation"
    consultation_id: str
    subject_id: str                       # the consulted Knowledge Object / session id
    mode: ConsultationMode = "observation"  # default = Observation (ADR-0008 invariant)
    answer: str                           # the agent's answer payload
    mef: MEF                              # complete or the record cannot be built


PRLNode = Union[ProjectNode, FileNode, CommitNode, SessionNode, Edge, ConsultationNode]

ACTION_TO_MODEL.update(
    {
        "prl.project": ProjectNode,
        "prl.file": FileNode,
        "prl.commit": CommitNode,
        "prl.session": SessionNode,
        "prl.edge": Edge,
        "prl.consultation": ConsultationNode,
    }
)


# ---------------------------------------------------------------------------
# DSM Entry draft (not yet persisted) and the mapping
# ---------------------------------------------------------------------------


class EntryDraft(BaseModel):
    """A draft DSM ``Entry`` — the shape P0 produces, *before* any write.

    Mirrors the kernel ``Entry`` fields that PRL is responsible for
    (``session_id`` / ``source`` / ``content`` / ``shard`` / ``metadata`` /
    ``version``). The kernel assigns ``id`` / ``hash`` / ``prev_hash`` at append
    time, so they are intentionally absent here. P0 never writes this anywhere.
    """

    model_config = ConfigDict(extra="forbid")

    session_id: str  # harvest-run id (groups one indexing pass)
    source: str = "prl"
    content: str  # canonical JSON (UTF-8), inline
    shard: str
    metadata: dict[str, Any]  # carries action_name (RR hook)
    timestamp: str  # ISO-8601 ms Z (kernel Entry uses datetime; assigned at append)
    version: str = "prl.v1"


def _kind(node: PRLNode) -> str:
    """Return the PRL record kind for a node/edge (the ``action_name`` value)."""
    if isinstance(node, Edge):
        return PRL_ACTION["edge"]
    return PRL_ACTION[node.node_type]


def _ms_to_iso(ms: int) -> str:
    dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    return f"{dt:%Y-%m-%dT%H:%M:%S}.{dt.microsecond // 1000:03d}Z"


def _fact_timestamp(node: PRLNode) -> str:
    """Timestamp of the fact the node represents, when the node carries one;
    otherwise the current UTC time. Pure — no I/O."""
    if isinstance(node, FileNode):
        return _ms_to_iso(node.mtime_ms)
    if isinstance(node, CommitNode):
        return _ms_to_iso(node.ts_ms)
    if isinstance(node, SessionNode):
        return _ms_to_iso(node.started_ms)
    return utc_now_ms()


def to_entry(node: PRLNode, *, shard: str, session_id: str) -> EntryDraft:
    """Encode a PRL node/edge into an :class:`EntryDraft` (D-1).

    ``content`` is the canonical JSON of the node; ``metadata['action_name']``
    is the PRL kind so RR's ``action_index`` can retrieve it. Does not write
    anything.
    """
    payload = node.model_dump(mode="json", exclude_none=True)
    content = canonical_bytes(payload).decode("utf-8")
    return EntryDraft(
        session_id=session_id,
        content=content,
        shard=shard,
        metadata={"action_name": _kind(node)},
        timestamp=_fact_timestamp(node),
    )


def _read_attr(entry: Any, name: str) -> Any:
    """Duck-typed accessor: works for a dict, an EntryDraft, or a kernel Entry."""
    if isinstance(entry, dict):
        return entry.get(name)
    return getattr(entry, name, None)


def from_entry(entry: Any) -> PRLNode:
    """Decode a DSM Entry (kernel ``Entry``, :class:`EntryDraft`, or dict) back
    into the corresponding PRL node/edge. Inverse of :func:`to_entry`.

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
        raise PRLEntryMappingError(
            f"unknown or missing action_name: {action!r}"
        )

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
