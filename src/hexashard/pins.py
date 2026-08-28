"""Pin lifecycle: pins point, sources ground.

A pin's ``value`` is a copy kept for cheap inclusion in the active context.
It is never authority.  Every question about whether a pin is still true is
answered by resolving ``source_ref`` against the source store, so a pin that
has drifted is *detectable* rather than quietly wrong.

Nothing here fabricates grounding.  When a source cannot be reached the pin is
reported BROKEN and the caller is told so.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Pin, PinStatus, Source, SourceStatus
from .store import PinStore, SourceStore


@dataclass
class PinResolution:
    """The result of following a pin to its primary source."""

    pin: Pin
    source: Source | None
    status: PinStatus
    grounded: bool
    detail: str

    def to_dict(self) -> dict:
        return {
            "pin_id": self.pin.pin_id,
            "key": self.pin.key,
            "value": self.pin.value,
            "source_ref": self.pin.source_ref,
            "source_status": self.source.status.value if self.source else None,
            "status": self.status.value,
            "grounded": self.grounded,
            "detail": self.detail,
        }


@dataclass
class PinReconciliation:
    pin_id: str
    key: str
    before: PinStatus
    after: PinStatus
    old_source_ref: str | None
    new_source_ref: str | None
    value_changed: bool
    detail: str

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["before"] = self.before.value
        d["after"] = self.after.value
        return d


def resolve(pin: Pin, sources: SourceStore) -> PinResolution:
    """Evaluate a pin against the source store without changing anything."""
    if not pin.source_ref:
        return PinResolution(pin, None, PinStatus.BROKEN, False,
                             "pin carries no source_ref, so it cannot be grounded")
    src = sources.try_get(pin.source_ref)
    if src is None:
        return PinResolution(pin, None, PinStatus.BROKEN, False,
                             f"source {pin.source_ref} is not present in the store")
    if src.status is SourceStatus.CURRENT:
        return PinResolution(pin, src, PinStatus.ACTIVE, True, "grounded in a CURRENT source")
    if src.status is SourceStatus.SUPERSEDED:
        return PinResolution(pin, src, PinStatus.STALE, True,
                             f"source {src.source_id} was superseded by {src.superseded_by}")
    return PinResolution(pin, src, PinStatus.NEEDS_REVIEW, True,
                         f"source {src.source_id} is {src.status.value}, not authoritative")


def check_all(pins: PinStore, sources: SourceStore) -> list[PinResolution]:
    return [resolve(p, sources) for p in pins.live()]


def stale(pins: PinStore, sources: SourceStore) -> list[PinResolution]:
    return [r for r in check_all(pins, sources) if r.status is not PinStatus.ACTIVE]


def reconcile(pins: PinStore, sources: SourceStore) -> list[PinReconciliation]:
    """Repoint pins whose source has been superseded.

    A pin is moved to the head of its supersession chain.  Its *value* is only
    adopted from the new source when that source explicitly declares itself
    authoritative for the pin's key (``claim_key``); otherwise the pin keeps
    its old value and is flagged NEEDS_REVIEW.  The system never invents a new
    value from prose.
    """
    out: list[PinReconciliation] = []
    for pin in pins.live():
        before = resolve(pin, sources)
        if before.status is PinStatus.ACTIVE:
            continue
        if before.status is PinStatus.BROKEN:
            prior, pin.status = pin.status, PinStatus.BROKEN
            out.append(PinReconciliation(pin.pin_id, pin.key, prior, PinStatus.BROKEN,
                                         pin.source_ref, pin.source_ref, False, before.detail))
            continue
        head = sources.current_chain_head(pin.source_ref) if pin.source_ref else None
        if head is None or head.source_id == pin.source_ref:
            prior, pin.status = pin.status, before.status
            out.append(PinReconciliation(pin.pin_id, pin.key, prior, before.status,
                                         pin.source_ref, pin.source_ref, False, before.detail))
            continue
        old_ref, old_value = pin.source_ref, pin.value
        pin.source_ref = head.source_id
        if (head.claim_key == pin.key and head.claim_value is not None
                and head.status is SourceStatus.CURRENT):
            pin.value = head.claim_value
            pin.status = PinStatus.ACTIVE
            detail = f"repointed to {head.source_id} and adopted its declared value for {pin.key}"
        else:
            pin.status = PinStatus.NEEDS_REVIEW
            why = ("is not CURRENT" if head.status is not SourceStatus.CURRENT
                   else f"declares no value for {pin.key}")
            detail = (f"repointed to {head.source_id}, which {why}; "
                      "value left unchanged for human review")
        out.append(PinReconciliation(pin.pin_id, pin.key, before.status, pin.status,
                                     old_ref, pin.source_ref, pin.value != old_value, detail))
    return out
