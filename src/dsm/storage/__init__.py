#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSM v2 - Storage Package (thin facade)

Re-exports ShardSegmentManager from core. The real implementation
lives in dsm.core.shard_segments.
"""

from dsm.core.shard_segments import ShardSegmentManager

__all__ = ["ShardSegmentManager"]
