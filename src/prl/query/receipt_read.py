"""Receipt Hop v1 — `prl receipt <hash>`: the last edge of the projection web.

O-005's separately-emerging candidate surface. A receipt is already a **sufficient identifier** in its
projection; what was missing is only the receipt→Entry lookup and an honest view of the certified act.
This module adds **one derived lookup** — walk the action buckets in declared order, match the **full**
hash against each entry's ``hash``, ``from_entry`` → the typed node — and renders a **uniform Certified
Act card** for all seven kinds. Read-only, zero entity, zero persistent index (no reverse hash index).

Boundary (printed on every card and on not-found): the card is a **reconstruction** from the certified
act, **not a re-certification** (hash-chain verification is kernel domain); the receipt and the lookup
are **projection-relative** — *not found here ≠ does not exist elsewhere*.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dsm.rr.index import RRIndexBuilder
from dsm.rr.navigator import RRNavigator

from ..types import (
    CommitNode,
    ConsultationNode,
    Edge,
    FileNode,
    PRLNode,
    ProjectNode,
    ResolutionNode,
    SessionNode,
    from_entry,
)
from .links import LinkAnnotator
from .standing_read import RegistryProjection

# Scan order: decision-layer buckets first (the common case), then the code-graph kinds (fallback).
BUCKET_ORDER: tuple[str, ...] = (
    "prl.consultation", "prl.resolution",
    "prl.project", "prl.file", "prl.commit", "prl.session", "prl.edge",
)

_BOUNDARY = (
    "  note: reconstruction from the certified act — not a re-certification (hash-chain\n"
    "        verification is kernel domain) · receipt and lookup are projection-relative ·\n"
    "        not found here ≠ does not exist elsewhere"
)

NOT_FOUND_MSG = "no act with this receipt in this projection's PRL buckets"


@dataclass(frozen=True)
class ReceiptCard:
    """One certified act, reconstructed from its receipt. Derived, never stored."""

    receipt: str
    kind: str          # the matched action_name (the PRL record kind)
    node: PRLNode      # the reconstructed typed node


def _val(x: Any, empty: str = "(none)") -> str:
    return str(x) if x else empty


def _act_and_content(n: PRLNode, ann: LinkAnnotator) -> tuple[str, str]:
    """Kind-appropriate identifying fields (``act``) + the canonical payload (``content``). The act line
    links onward where ids map to a projection landing type (`[go object|agent|org|claim …]`) — the
    receipt lands back into the web. Code-graph kinds have no decision-layer landing, so no onward link."""
    if isinstance(n, ConsultationNode):
        m = n.mef
        act = (f"subject={n.subject_id}{ann.tag('object', n.subject_id)}  mode={n.mode}  "
               f"claim={m.claim_id}{ann.tag('claim', m.claim_id)}  "
               f"agent={_val(m.agent_id, '(unknown)')}{ann.tag('agent', m.agent_id or '')}  "
               f"org={_val(n.org_id)}{ann.tag('org', n.org_id or '')}")
        return act, f"answer={n.answer!r}"
    if isinstance(n, ResolutionNode):
        m = n.mef
        act = (f"decision={n.decision}  target_claim={n.target_claim_id}{ann.tag('claim', n.target_claim_id)}  "
               f"agent={_val(m.agent_id, '(unknown)')}{ann.tag('agent', m.agent_id or '')}  "
               f"org={_val(n.org_id)}{ann.tag('org', n.org_id or '')}")
        return act, f"regime={m.regime}  confidence={m.confidence}  producer={m.producer}"
    if isinstance(n, ProjectNode):
        act = f"project_id={n.project_id}  name={n.name}  org={_val(n.org_id)}{ann.tag('org', n.org_id or '')}"
        return act, f"root_path={n.root_path}"
    if isinstance(n, FileNode):
        return (f"path={n.path}  content_hash={n.content_hash}  project={n.project_id}",
                f"size={n.size}  mtime_ms={n.mtime_ms}")
    if isinstance(n, CommitNode):
        return (f"sha={n.sha}  author={n.author}  project={n.project_id}",
                f"message={n.message!r}  files={len(n.files)}")
    if isinstance(n, SessionNode):
        return (f"session_id={n.session_id}  tool={n.tool}  project={_val(n.project_id)}",
                f"title={_val(n.title)}  preview={n.text_preview[:60]!r}")
    if isinstance(n, Edge):
        return (f"edge_type={n.edge_type}  src={n.src_id}  dst={n.dst_id}", f"confidence={n.confidence}")
    return "(unrecognized node)", ""  # pragma: no cover — all 7 kinds handled above


def render_receipt_card(card: ReceiptCard) -> str:
    """Pure display — the uniform Certified Act card (same shape for all seven kinds). Reconstruction,
    never a re-certification; the boundary note is printed on every card."""
    ann = LinkAnnotator()
    act, content = _act_and_content(card.node, ann)
    lines = [f"Certified act — {card.receipt}",
             f"  kind:       {card.kind}",
             f"  act:        {act}"]
    if content:
        lines.append(f"  content:    {content}")
    lines += [f"  receipt:    {card.receipt}   (this projection's certification)", "", _BOUNDARY]
    return "\n".join(lines)


def render_not_found(receipt: str) -> str:
    """Pure display — the honest not-found state + the same boundary note (never inferred, never a
    claim about global non-existence)."""
    return "\n".join([f"{NOT_FOUND_MSG}",
                      f"  receipt:    {receipt}", "", _BOUNDARY])


class ReceiptQuery:
    """Resolves a receipt to its certified act over a registry projection (read-only). One derived
    lookup, per call, nothing stored; no reverse hash index (the standing doctrine — measure first)."""

    def __init__(self, storage: Any, index_dir: Any, *, _navigator: RegistryProjection | None = None):
        if _navigator is None:
            builder = RRIndexBuilder(storage=storage, index_dir=str(index_dir))
            builder.build()
            _navigator = RRNavigator(builder, storage)
        self._nav: RegistryProjection = _navigator

    def find(self, receipt: str) -> ReceiptCard | None:
        """Walk the action buckets in declared order; match the **full** receipt against each entry's
        ``hash``; reconstruct the typed node. Short-circuits on the first match (decision-layer buckets
        first → the common case is cheap). Returns ``None`` if no entry in **this projection** matches."""
        for action in BUCKET_ORDER:
            records = self._nav.navigate_action(action)
            for entry in self._nav.resolve_entries(records):
                if str(getattr(entry, "hash", "") or "") == receipt:
                    return ReceiptCard(receipt=receipt, kind=action, node=from_entry(entry))
        return None
