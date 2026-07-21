"""PRL Swarm subpackage (v0.1) — grounding layer for multi-agent runs.

Pure models + the ``to_swarm_entry`` / ``from_swarm_entry`` envelope mapping.
NO kernel import anywhere under this package: the single physical
``Storage.append`` call site for swarm records is the registered PRL writer
(``PRLStore.commit_swarm_entry`` in ``prl/store/dsm_commit.py``), which
validates against the closed action set defined here and stamps the real
kernel version at the append boundary.
"""

from __future__ import annotations

from .types import (
    ACTION_TO_MODEL,
    SCHEMA_VERSION,
    SWARM_ACTION,
    SWARM_ACTIONS,
    SwarmRecord,
    SwarmRun,
    TaskNode,
    from_swarm_entry,
    swarm_shard_name,
    to_swarm_entry,
)

__all__ = [
    "ACTION_TO_MODEL",
    "SCHEMA_VERSION",
    "SWARM_ACTION",
    "SWARM_ACTIONS",
    "SwarmRecord",
    "SwarmRun",
    "TaskNode",
    "from_swarm_entry",
    "swarm_shard_name",
    "to_swarm_entry",
]
