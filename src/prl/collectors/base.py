"""Collector framework (P6) — protocol + registry.

A ``Collector`` parses one external session source into ``SessionNode`` records.
Collectors are pure read-only producers (no DSM / RR / Storage). The registry is
keyed by ``Collector.name`` and holds the collector *class* (collectors are
constructed with source-specific arguments, e.g. an export path).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..exceptions import PRLError
from ..types import SessionNode


class CollectorError(PRLError):
    """Raised for an unknown collector name or a source that cannot be parsed."""


@runtime_checkable
class Collector(Protocol):
    """A session-source parser. Implementations set a class-level ``name`` and
    return ``SessionNode`` records from :meth:`collect`."""

    name: str

    def collect(self) -> list[SessionNode]: ...


@runtime_checkable
class FullTextSource(Protocol):
    """Optional capability (Retrieval v2 / ADR-PRL-0006, R1): yield the **full**
    transcript text per session, keyed by ``session_id``.

    Deliberately separate from :meth:`Collector.collect` so the P6 ``SessionNode``
    schema stays frozen (preview-only). Only sources that can provide full text
    implement this; the passage (chunk) index consumes the returned map. A source
    is checked for this capability with ``isinstance(src, FullTextSource)``."""

    def full_texts(self) -> dict[str, str]: ...


COLLECTOR_REGISTRY: dict[str, type] = {}


def register(collector_cls: type) -> type:
    """Register a collector class by its ``name``. Returns the class (usable as
    a decorator)."""
    name = getattr(collector_cls, "name", None)
    if not name:
        raise CollectorError(f"collector {collector_cls!r} has no 'name'")
    COLLECTOR_REGISTRY[name] = collector_cls
    return collector_cls


def get_collector(name: str) -> type:
    """Return the registered collector class for *name*."""
    try:
        return COLLECTOR_REGISTRY[name]
    except KeyError as exc:
        raise CollectorError(f"unknown collector: {name!r}") from exc


def list_collectors() -> list[str]:
    """Sorted list of registered collector names."""
    return sorted(COLLECTOR_REGISTRY)
