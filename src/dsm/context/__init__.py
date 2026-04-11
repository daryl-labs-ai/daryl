"""DSM Consumption Layer — Context (daryl port).

Phase 4 port of ``dsm_v0.context``. Same public API, same section
order, same token-budget semantics, same provenance delegation.
Only the read path (``dsm.recall.search_memory`` in daryl) changes.

Namespace note
--------------
daryl already has a package at ``dsm.rr.context`` (the
``RRContextBuilder``). That is a lower-level RR context helper and is
unrelated to this module. ``dsm.context`` is the consumption-layer
facade — it sits above ``dsm.recall`` and ``dsm.provenance``, not
above RR directly.
"""

from .builder import (
    DEFAULT_MAX_TOKENS,
    SECTION_ORDER,
    build_context,
    build_prompt_context,
)

__all__ = [
    "build_context",
    "build_prompt_context",
    "SECTION_ORDER",
    "DEFAULT_MAX_TOKENS",
]
