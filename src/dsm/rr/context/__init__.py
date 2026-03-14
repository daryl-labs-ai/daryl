# -*- coding: utf-8 -*-
"""
RR Context Builder — transforms query results into structured context for agents/LLMs.

Uses only RRQueryEngine; does not touch DSM kernel or Storage.
"""

from .rr_context_builder import RRContextBuilder

__all__ = ["RRContextBuilder"]
