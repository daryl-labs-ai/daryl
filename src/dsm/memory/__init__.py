"""Agent Memory API V1.

Minimal, append-only reasoning records stored in DSM outside the kernel.
"""

from .agent_memory import (
    DEFAULT_MEMORY_SHARD,
    MEMORY_SCHEMA_VERSION,
    explain_decision,
    record_decision,
    record_fact,
    record_hypothesis,
    record_inference,
)
from .report import render_explain_markdown

__all__ = [
    "DEFAULT_MEMORY_SHARD",
    "MEMORY_SCHEMA_VERSION",
    "record_fact",
    "record_hypothesis",
    "record_inference",
    "record_decision",
    "explain_decision",
    "render_explain_markdown",
]
