# -*- coding: utf-8 -*-
"""
RR Query Engine — high-level query interface over RR Navigator.

Accepts session_id, agent, shard_id, time range; returns metadata records
or resolved Entry objects. Uses only the navigator (index + optional resolution).
"""

from .rr_query_engine import RRQueryEngine

__all__ = ["RRQueryEngine"]
