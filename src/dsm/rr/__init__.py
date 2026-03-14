# -*- coding: utf-8 -*-
"""
DSM Read Relay (DSM-RR) — read-only layer over DSM Storage.

Uses only the DSM Storage API (Storage.read()). No core modifications.
Works with classic shards and block shards (expands block entries in memory).
"""

from .relay import DSMReadRelay

__all__ = ["DSMReadRelay"]
