"""Ensure the agent-mesh root is on sys.path so `dashboard.*` imports resolve
when pytest is launched from anywhere.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
