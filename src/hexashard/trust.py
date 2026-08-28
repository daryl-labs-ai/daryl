"""Optional trust backend boundary.

The namespace experiment concluded that DSM is OPTIONAL, FOR AUDIT AND
PROVENANCE ONLY -- not working memory.  This module is therefore an interface
and a no-op default, and nothing in the core depends on it.

Deliberately absent: any DSM import, any hash chain, signature, receipt or
Merkle structure.  Those belong to a backend, not to HexaShard core.  A
backend that wants them implements :class:`TrustBackend` outside this package.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class TrustBackend(Protocol):
    name: str

    def record(self, event: str, payload: dict[str, Any]) -> str | None: ...
    def verify(self, receipt_id: str) -> bool: ...
    def lookup(self, receipt_id: str) -> dict[str, Any] | None: ...


@dataclass
class NullTrustBackend:
    """The default.  Records nothing, verifies nothing, claims nothing."""

    name: str = "null"

    def record(self, event: str, payload: dict[str, Any]) -> str | None:
        return None

    def verify(self, receipt_id: str) -> bool:
        return False

    def lookup(self, receipt_id: str) -> dict[str, Any] | None:
        return None


@dataclass
class InMemoryTrustBackend:
    """A test double proving the seam is usable.  Not a durability claim."""

    name: str = "memory"
    events: list[dict[str, Any]] = field(default_factory=list)

    def record(self, event: str, payload: dict[str, Any]) -> str | None:
        rid = f"R{len(self.events) + 1:04d}"
        self.events.append({"receipt_id": rid, "event": event, "payload": payload})
        return rid

    def verify(self, receipt_id: str) -> bool:
        return any(e["receipt_id"] == receipt_id for e in self.events)

    def lookup(self, receipt_id: str) -> dict[str, Any] | None:
        for e in self.events:
            if e["receipt_id"] == receipt_id:
                return e
        return None
