# -*- coding: utf-8 -*-
"""
RR Index — derived index over DSM shards.

Builds and maintains session, agent, timeline, and shard indexes
using only the public Storage API. Index files live under data/index/.
"""

from .rr_index_builder import RRIndexBuilder

__all__ = ["RRIndexBuilder"]
