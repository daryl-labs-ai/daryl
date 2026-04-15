"""Exchange adapter — issues receipts. Raises if no WrittenEntry present."""
from __future__ import annotations

from datetime import datetime, timezone

from ulid import ULID

from ...dsm.writer import WrittenEntry


class ExchangeAdapter:
    def issue_receipt(
        self,
        written_entry: WrittenEntry | None,
        agent_id: str,
        task_id: str,
        mission_id: str,
    ) -> dict:
        if written_entry is None:
            raise ValueError("cannot issue receipt before DSM write succeeds")
        return {
            "receipt_id": str(ULID()),
            "issuer_agent_id": agent_id,
            "task_id": task_id,
            "mission_id": mission_id,
            "entry_hash": written_entry.entry_hash,
            "event_id": written_entry.event_id,
            "issued_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
