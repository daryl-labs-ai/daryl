# -*- coding: utf-8 -*-
"""
DSM v2 - Experimental block layer.

Uses DSM Storage API without modifying core. Blocks group multiple entries
into single append units for configurable batching while preserving
append-only semantics.
"""

from .manager import BlockManager, BlockConfig

__all__ = ["BlockManager", "BlockConfig"]
