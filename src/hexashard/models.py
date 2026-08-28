"""Core records.

Plain dataclasses with explicit ``to_dict`` / ``from_dict``.  No ORM, no
schema library, no inheritance hierarchy.  Every record round-trips through
JSON exactly, so a project directory is inspectable with ``cat``.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


# --------------------------------------------------------------------------
# Enumerations
# --------------------------------------------------------------------------

class SourceStatus(str, Enum):
    """Authority state of a primary source.

    Ordering matters: :func:`authority_rank` turns this into the primary
    retrieval sort key so a non-CURRENT source can never outrank a CURRENT one
    on lexical score alone.
    """

    CURRENT = "CURRENT"
    DRAFT = "DRAFT"
    UNVERIFIED = "UNVERIFIED"
    SUPERSEDED = "SUPERSEDED"


_AUTHORITY_RANK = {
    SourceStatus.CURRENT: 3,
    SourceStatus.DRAFT: 2,
    SourceStatus.UNVERIFIED: 1,
    SourceStatus.SUPERSEDED: 0,
}


def authority_rank(status: SourceStatus) -> int:
    return _AUTHORITY_RANK[SourceStatus(status)]


class HexType(str, Enum):
    """Initial vocabulary.  Deliberately small; not an exhaustive ontology."""

    SOURCE = "SOURCE"
    SUMMARY = "SUMMARY"
    DECISION = "DECISION"
    CONSTRAINT = "CONSTRAINT"
    TASK = "TASK"
    TEST = "TEST"
    ARTIFACT = "ARTIFACT"
    REFERENCE = "REFERENCE"


class HexStatus(str, Enum):
    ACTIVE = "ACTIVE"
    RESOLVED = "RESOLVED"
    ARCHIVED = "ARCHIVED"


class Temperature(str, Enum):
    """Loading policy only.  Carries no claim about truth or importance."""

    HOT = "HOT"
    WARM = "WARM"
    COLD = "COLD"


class SizeClass(str, Enum):
    S = "S"
    M = "M"
    L = "L"
    XL = "XL"


class PinStatus(str, Enum):
    ACTIVE = "ACTIVE"
    #: source_ref resolves, but the source is no longer CURRENT
    STALE = "STALE"
    #: repointed to the successor source, but the value could not be re-derived
    NEEDS_REVIEW = "NEEDS_REVIEW"
    #: replaced by a newer pin on the same key
    SUPERSEDED = "SUPERSEDED"
    #: source_ref does not resolve at all
    BROKEN = "BROKEN"


#: Relation types are an open vocabulary; these are the suggested starting set.
RELATION_TYPES = (
    "DEPENDS_ON",
    "SUPERSEDES",
    "SUPPORTS",
    "CONTRADICTS",
    "DERIVED_FROM",
    "TESTS",
    "DECIDES",
    "REFERENCES",
)


# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------

def _enum_value(v: Any) -> Any:
    return v.value if isinstance(v, Enum) else v


@dataclass
class Source:
    """A primary source.  Authoritative for project grounding."""

    source_id: str
    source_type: str
    title: str
    version: int = 1
    status: SourceStatus = SourceStatus.CURRENT
    supersedes: str | None = None
    superseded_by: str | None = None
    tags: list[str] = field(default_factory=list)
    #: Optional stable identifier of the *claim* this source is authoritative
    #: for.  Two CURRENT sources sharing a claim_key are an explicit authority
    #: conflict (see retrieval ambiguity).
    claim_key: str | None = None
    #: Optional machine-readable value of that claim, used when reconciling
    #: pins across a supersession.
    claim_value: str | None = None
    created_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    #: Content is held separately on disk; populated on load.
    content: str = ""

    def to_dict(self, include_content: bool = False) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = _enum_value(self.status)
        if not include_content:
            d.pop("content")
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any], content: str = "") -> "Source":
        d = dict(d)
        d.pop("content", None)
        d["status"] = SourceStatus(d.get("status", "CURRENT"))
        return cls(content=content, **d)

    @property
    def is_current(self) -> bool:
        return self.status is SourceStatus.CURRENT


@dataclass
class Hex:
    """An addressable bounded context unit.

    A Hex is not an agent.  It holds no behaviour and may exist for the whole
    life of a project without any model call ever being made against it.
    """

    hex_id: str
    title: str
    type: HexType
    epoch: int
    status: HexStatus = HexStatus.ACTIVE
    temperature: Temperature = Temperature.COLD
    size_class: SizeClass = SizeClass.S
    summary: str = ""
    source_refs: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    #: Optional layering metadata for a future UI.  Never used by the core.
    parent_hex: str | None = None
    depth: int = 0
    position: list[float] | None = None
    uuid: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for k in ("type", "status", "temperature", "size_class"):
            d[k] = _enum_value(getattr(self, k))
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Hex":
        d = dict(d)
        d["type"] = HexType(d["type"])
        d["status"] = HexStatus(d.get("status", "ACTIVE"))
        d["temperature"] = Temperature(d.get("temperature", "COLD"))
        d["size_class"] = SizeClass(d.get("size_class", "S"))
        return cls(**d)

    def header(self) -> dict[str, Any]:
        """The cheap projection used for map scans and active state."""
        return {
            "hex_id": self.hex_id,
            "type": _enum_value(self.type),
            "status": _enum_value(self.status),
            "temperature": _enum_value(self.temperature),
            "size_class": _enum_value(self.size_class),
            "title": self.title,
        }


@dataclass
class Pin:
    """A durable pointer to binding information.

    Pins point.  Sources ground.  A pin's ``value`` is a convenience copy for
    the active context; ``source_ref`` is what makes it checkable.
    """

    pin_id: str
    key: str
    value: str
    source_ref: str | None
    status: PinStatus = PinStatus.ACTIVE
    supersedes: str | None = None
    critical: bool = False
    hex_id: str | None = None
    updated_at: str | None = None
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = _enum_value(self.status)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Pin":
        d = dict(d)
        d["status"] = PinStatus(d.get("status", "ACTIVE"))
        return cls(**d)


@dataclass
class Relation:
    """A directed edge in a generic graph.  No degree constraint."""

    src: str
    type: str
    dst: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Relation":
        return cls(**d)

    def key(self) -> tuple[str, str, str]:
        return (self.src, self.type, self.dst)
