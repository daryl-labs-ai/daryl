"""PRL collectors subpackage (Phase 2, P6).

Collectors turn external session sources (chat / coding tools) into PRL
``SessionNode`` records. P6 V1 ships the framework (``base``) plus the ChatGPT
collector only. Claude/Cowork and Cursor/VS Code collectors are deferred until
their real export formats are inspected (no fragile parsers).

Collectors are *read-only producers*: they parse files / sources into
``SessionNode`` objects. They never touch DSM, RR, or Storage. Binding sessions
to files/commits (with confidence) is the binder's job in P7.
"""

from __future__ import annotations

from .base import (
    COLLECTOR_REGISTRY,
    Collector,
    get_collector,
    list_collectors,
    register,
)
from .binder import bind_sessions
from .chatgpt import ChatGPTCollector

__all__ = [
    "Collector",
    "COLLECTOR_REGISTRY",
    "register",
    "get_collector",
    "list_collectors",
    "ChatGPTCollector",
    "bind_sessions",
]
