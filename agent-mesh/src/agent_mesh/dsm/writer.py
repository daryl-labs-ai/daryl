"""DSM writer — append-only events.jsonl sink with deterministic entry hashing."""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class WrittenEntry:
    event_id: str
    entry_hash: str
    written_at: str


def _canonical_json(event: dict) -> bytes:
    return json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


logger = logging.getLogger("agent_mesh.dsm.writer")


class DSMWriter:
    """Append-only JSONL writer. The only component that writes events.

    P0 / H7: writes are bounded. A single event larger than ``max_event_bytes``
    is refused, and once ``events.jsonl`` reaches ``max_log_bytes`` further
    writes are refused. ``0`` disables a given bound. Refusal returns ``None``,
    the same contract callers already handle as a write failure.
    """

    def __init__(
        self,
        data_dir: Path,
        max_event_bytes: int = 0,
        max_log_bytes: int = 0,
    ):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._path = self._data_dir / "events.jsonl"
        self._lock = threading.Lock()
        self._fail_next = False
        self._max_event_bytes = max_event_bytes
        self._max_log_bytes = max_log_bytes

    @property
    def path(self) -> Path:
        return self._path

    def inject_failure(self, fail: bool = True) -> None:
        """Test hook — makes next write() return None."""
        self._fail_next = fail

    def write(self, event: dict) -> WrittenEntry | None:
        with self._lock:
            if self._fail_next:
                self._fail_next = False
                return None
            canonical = _canonical_json(event)
            line_bytes = len(canonical) + 1  # trailing newline

            if self._max_event_bytes and len(canonical) > self._max_event_bytes:
                logger.warning(
                    "DSMWriter: refusing oversized event %s (%d bytes > max %d)",
                    event.get("event_id"), len(canonical), self._max_event_bytes,
                )
                return None

            if self._max_log_bytes:
                current = self._path.stat().st_size if self._path.exists() else 0
                if current + line_bytes > self._max_log_bytes:
                    logger.critical(
                        "DSMWriter: events.jsonl ceiling reached (%d + %d > max %d) — "
                        "refusing write; rotate/archive the log",
                        current, line_bytes, self._max_log_bytes,
                    )
                    return None

            entry_hash = hashlib.sha256(canonical).hexdigest()
            line = canonical.decode("utf-8") + "\n"
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(line)
            return WrittenEntry(
                event_id=event["event_id"],
                entry_hash=entry_hash,
                written_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            )

    def read_all(self) -> list[dict]:
        if not self._path.exists():
            return []
        out = []
        with self._path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                out.append(json.loads(line))
        return out
