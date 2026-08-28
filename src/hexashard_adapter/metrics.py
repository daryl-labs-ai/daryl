"""JSONL instrumentation. Adapter-owned; not a second project store."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def append_metric(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
