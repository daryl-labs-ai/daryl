"""Linked Projections v1 — typed link annotations (display) shared by every projection renderer.

O-004 found the web of projections already exists; its edges were printed as bare text with no
affordance. This module makes those edges **visible** (a printed ``[go <type> <id>]`` affordance) so
they become **actionable** by the stateless ``prl go`` dispatcher — with **no graph, no entity, no
index, no state**. Typing is by **declaration, never inference**: a link's ``<type>`` is one of the
four ``go`` landing types; nothing is resolved, verified, or stored to print it. The free strings stay
free — the type comes from the annotation site (or the ``go`` command), not from guessing an id's kind.
"""

from __future__ import annotations

# The link / `go` landing types (doctrine: an id is typed by declaration, never inferred). `receipt`
# (Receipt Hop v1) lands on the certified act behind a receipt — the last edge of the web.
LINK_TYPES = ("object", "agent", "org", "claim", "receipt")


class LinkAnnotator:
    """Per-**page** first-occurrence annotator (the noise rule). Stateful only within one render pass;
    nothing persisted. Annotating only the first occurrence of each distinct ``(type, id)`` keeps a rich
    page (a long History) from drowning in repeated links — subsequent occurrences stay bare."""

    def __init__(self) -> None:
        self._seen: set[tuple[str, str]] = set()

    def tag(self, link_type: str, ident: str) -> str:
        """Return ``   [go <type> <id>]`` on the **first** occurrence of ``(type, id)`` this page, else
        ``""``. Leading spaces so a caller can append it directly to a line; an empty id is never
        annotated (an unknown/legacy id has no landing). Pure — records only in-page occurrence."""
        if not ident:
            return ""
        key = (link_type, ident)
        if key in self._seen:
            return ""
        self._seen.add(key)
        return f"   [go {link_type} {ident}]"
