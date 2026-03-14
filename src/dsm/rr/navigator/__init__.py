# -*- coding: utf-8 -*-
"""
RR Navigator — memory navigation using the RR Index.

Uses index lookups only; does not scan shards directly.
Full entry retrieval uses Storage.read() when required.
"""

from .rr_navigator import RRNavigator

__all__ = ["RRNavigator"]
