"""Shared helpers for P0 adversarial security tests."""

import uuid
from datetime import datetime, timezone

from dsm.core.models import Entry


def make_entry(content: str, shard: str = "sessions") -> Entry:
    return Entry(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        session_id="p0_sess",
        source="agent",
        content=content,
        shard=shard,
        hash="",
        prev_hash=None,
        metadata={},
        version="v2.0",
    )


def append_n(storage, n: int, shard: str = "sessions"):
    """Append n well-formed entries via the public API and return them."""
    out = []
    for i in range(n):
        out.append(storage.append(make_entry(f"decision-{i}", shard)))
    return out


def truncate_last_segment(storage, shard_id: str, n: int):
    """Delete the last n JSONL lines from the newest segment file.

    Simulates an attacker silently removing the most recent entries from an
    append-only shard. Returns (lines_before, lines_after).
    """
    segments = storage.segment_manager.get_segment_files_ordered(shard_id, reverse=True)
    target = segments[0]
    lines = [ln for ln in target.read_text(encoding="utf-8").splitlines() if ln.strip()]
    keep = lines[:-n] if n else lines
    target.write_text(("\n".join(keep) + "\n") if keep else "", encoding="utf-8")
    return len(lines), len(keep)


def read_pin(storage, shard_id: str) -> dict:
    """Read the integrity pin file ({shard}_last_hash.json) as a dict, or {}."""
    import json

    f = storage.integrity_dir / f"{shard_id}_last_hash.json"
    if not f.exists():
        return {}
    return json.loads(f.read_text(encoding="utf-8"))
