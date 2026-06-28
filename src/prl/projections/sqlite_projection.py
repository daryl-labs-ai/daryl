"""A second registry projection backed by SQLite (Identity across projections v1).

Goal (Second epoch #3): prove the **existing** identity model survives a *second registry
projection*. ``SqliteProjection`` implements the same :class:`RegistryProjection` seam as
RR (``navigate_action`` / ``resolve_entries``), so the unchanged ``StandingQuery`` /
``ExplainQuery`` run on it and must produce the **identical** result — same ``claim_id``,
same decisions, same standing, same explanation.

Invariants:
- **DSM stays the certifier.** Acts are read via RR (ADR-0001) and materialized into a
  separate SQLite store. No ``Storage`` import, no new ``LEGITIMATE_WRITERS`` entry.
- **No re-mint.** Acts are stored **generically** (``entry_id`` / ``action_name`` /
  ``content`` / ``receipt``); ``claim_id`` is never extracted or regenerated — it stays in
  ``content`` and is parsed by ``from_entry`` exactly as with RR.
- **Receipt is projection-relative.** The stored ``receipt`` is the DSM ``Entry.hash``
  carried verbatim (v1 keeps DSM as certifier); a *substrate* swap would re-issue it.

Uses stdlib ``sqlite3`` (no new dependency).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any

from dsm.rr.index import RRIndexBuilder
from dsm.rr.navigator import RRNavigator

# The act kinds that make up the identity chain (Proposal/Observation + Resolution).
_PROJECTED_ACTIONS = ("prl.consultation", "prl.resolution")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS acts (
    ord         INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id    TEXT NOT NULL,
    action_name TEXT NOT NULL,
    content     TEXT NOT NULL,
    receipt     TEXT
);
"""


@dataclass(frozen=True)
class _ProjectedEntry:
    """An Entry-shaped object satisfying what the query layer + ``from_entry`` need."""

    id: str
    hash: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


def build_sqlite_projection(storage: Any, index_dir: Any, db_path: Any) -> int:
    """Materialize the certified identity-chain acts into ``db_path`` (SQLite), read via RR.
    Returns the number of acts written. Read-only w.r.t. DSM; idempotent. Acts are stored
    generically — ``claim_id`` and ``receipt`` are carried inside ``content`` / verbatim,
    never re-minted."""
    builder = RRIndexBuilder(storage=storage, index_dir=str(index_dir))
    builder.build()
    nav = RRNavigator(builder, storage)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(_SCHEMA)
        conn.execute("DELETE FROM acts")
        n = 0
        for action in _PROJECTED_ACTIONS:
            records = nav.navigate_action(action)
            entries = nav.resolve_entries(records)
            by_id = {getattr(e, "id", None): e for e in entries}
            for rec in records:  # authoritative record order
                eid = rec.get("entry_id") if isinstance(rec, dict) else getattr(rec, "entry_id", None)
                entry = by_id.get(eid)
                if entry is None:
                    continue
                conn.execute(
                    "INSERT INTO acts (entry_id, action_name, content, receipt) VALUES (?,?,?,?)",
                    (str(getattr(entry, "id", "") or ""), action,
                     getattr(entry, "content", "") or "",
                     str(getattr(entry, "hash", "") or "")),
                )
                n += 1
        conn.commit()
        return n
    finally:
        conn.close()


class SqliteProjection:
    """A :class:`RegistryProjection` served from the SQLite store. Same retrieval surface
    as ``RRNavigator`` — the unchanged query layer runs on it."""

    def __init__(self, db_path: Any):
        self._db = str(db_path)

    def navigate_action(self, action_name: str, limit: int | None = None) -> list[dict[str, Any]]:
        conn = sqlite3.connect(self._db)
        try:
            rows = conn.execute(
                "SELECT entry_id FROM acts WHERE action_name = ? ORDER BY ord",
                (action_name,),
            ).fetchall()
        finally:
            conn.close()
        records = [{"entry_id": eid, "action_name": action_name} for (eid,) in rows]
        return records[:limit] if limit is not None else records

    def resolve_entries(self, records: list[Any], limit: int | None = None) -> list[_ProjectedEntry]:
        ids = [r.get("entry_id") if isinstance(r, dict) else getattr(r, "entry_id", None)
               for r in records]
        ids = [i for i in ids if i is not None]
        if not ids:
            return []
        conn = sqlite3.connect(self._db)
        try:
            # placeholders is only "?" (one per id); every value is a bound parameter,
            # so this is not a string-interpolated SQL injection vector (bandit B608).
            placeholders = ",".join("?" for _ in ids)
            sql = (
                "SELECT entry_id, action_name, content, receipt FROM acts "
                f"WHERE entry_id IN ({placeholders})"  # nosec B608
            )
            rows = conn.execute(sql, ids).fetchall()
        finally:
            conn.close()
        out = [
            _ProjectedEntry(id=eid, hash=receipt or "", content=content,
                            metadata={"action_name": action})
            for (eid, action, content, receipt) in rows
        ]
        return out[:limit] if limit is not None else out
