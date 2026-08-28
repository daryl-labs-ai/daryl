"""Persistence: plain files, atomic writes, no database.

Layout (see ARCHITECTURE.md):

    project/
      project.json        run configuration + epoch counter
      active_state.json   the bounded working set
      hexmap.jsonl        one Hex record per line
      pins.jsonl          one Pin record per line
      relations.jsonl     one edge per line
      epochs/             one checkpoint + one transition record per rotation
      sources/            <source_id>.json  (record) + <source_id>.txt (content)
      artifacts/          reserved for caller-produced outputs

Sequence counters are *derived* from the highest address already present
rather than stored, so there is no counter file that can drift away from the
records it numbers.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Iterable, Iterator

from .ids import (
    hex_address,
    machine_uuid,
    parse_hex_address,
    parse_source_address,
    pin_address,
    source_address,
)
from .models import (
    Hex,
    HexStatus,
    HexType,
    Pin,
    PinStatus,
    Relation,
    SizeClass,
    Source,
    SourceStatus,
    Temperature,
)

# --------------------------------------------------------------------------
# Atomic file primitives
# --------------------------------------------------------------------------


def atomic_write_text(path: Path, text: str) -> None:
    """Write via a temp file in the same directory, then ``os.replace``.

    The file's existing mode is preserved (``mkstemp`` creates at 0600, which
    would otherwise silently tighten permissions on every save), and the parent
    directory is fsynced so the rename itself is durable, not just the bytes.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else (0o666 & ~_umask())
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".part")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
        dir_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _umask() -> int:
    current = os.umask(0)
    os.umask(current)
    return current


def address_sort_key(address: str) -> tuple:
    """Sort addresses by their numeric parts, not lexically.

    ``P1.E10.H001`` must come after ``P1.E9.H001``; a plain string sort puts it
    between E1 and E2.  Falls back to the raw string for anything unparsed, so
    ordering is always total and deterministic.
    """
    parts = address.split(".")
    key: list = []
    for part in parts:
        m = re.match(r"^([A-Za-z]*)(\d+)$", part)
        key.append((m.group(1), int(m.group(2))) if m else (part, -1))
    return (len(parts), tuple(key))


def atomic_write_json(path: Path, obj: Any) -> None:
    atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    body = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)
    atomic_write_text(path, body)


def read_jsonl(path: Path) -> Iterator[dict]:
    if not path.exists():
        return iter(())

    def _gen() -> Iterator[dict]:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield json.loads(line)

    return _gen()


# --------------------------------------------------------------------------
# Source store
# --------------------------------------------------------------------------


class SourceStore:
    """Authoritative store of primary sources.

    Content lives beside the record as plain text so the corpus is greppable.
    Write order is content-then-record: the ``.json`` record is what makes a
    source exist, so a crash between the two writes leaves an unreferenced
    ``.txt`` rather than a record pointing at missing content.
    """

    def __init__(self, root: Path, project_prefix: str) -> None:
        self.root = Path(root)
        self.prefix = project_prefix
        self.root.mkdir(parents=True, exist_ok=True)
        self._records: dict[str, Source] = {}
        self._load()

    def _record_path(self, source_id: str) -> Path:
        return self.root / f"{source_id}.json"

    def _content_path(self, source_id: str) -> Path:
        return self.root / f"{source_id}.txt"

    def _load(self) -> None:
        for rec_path in sorted(self.root.glob("*.json")):
            d = json.loads(rec_path.read_text(encoding="utf-8"))
            src = Source.from_dict(d)
            self._records[src.source_id] = src

    def _next_id(self) -> str:
        seq = 0
        for sid in self._records:
            try:
                seq = max(seq, parse_source_address(sid)[1])
            except ValueError:
                continue
        return source_address(self.prefix, seq + 1)

    # -- writes ----------------------------------------------------------
    def add(
        self,
        source_type: str,
        title: str,
        content: str,
        *,
        status: SourceStatus = SourceStatus.CURRENT,
        tags: list[str] | None = None,
        claim_key: str | None = None,
        claim_value: str | None = None,
        created_at: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Source:
        source_id = self._next_id()
        src = Source(
            source_id=source_id,
            source_type=source_type,
            title=title,
            status=status,
            tags=list(tags or []),
            claim_key=claim_key,
            claim_value=claim_value,
            created_at=created_at,
            metadata=dict(metadata or {}),
            content=content,
        )
        self._persist(src)
        self._records[source_id] = src
        return src

    def _persist(self, src: Source) -> None:
        atomic_write_text(self._content_path(src.source_id), src.content)
        atomic_write_json(self._record_path(src.source_id), src.to_dict())

    def set_status(self, source_id: str, status: SourceStatus) -> Source:
        src = self.get(source_id)
        src.status = SourceStatus(status)
        self._persist(src)
        return src

    def supersede(self, old_id: str, new_id: str) -> tuple[Source, Source]:
        """Mark ``old_id`` SUPERSEDED by ``new_id``.  Both remain retrievable."""
        old, new = self.get(old_id), self.get(new_id)
        if old_id == new_id:
            raise ValueError("a source cannot supersede itself")
        if new_id in self._ancestors(old_id):
            raise ValueError(
                f"{new_id} already appears in the supersession chain of {old_id}; "
                "this would create a cycle and leave authority undefined"
            )
        old.status = SourceStatus.SUPERSEDED
        old.superseded_by = new_id
        new.status = SourceStatus.CURRENT
        new.supersedes = old_id
        new.superseded_by = None      # it is the head of the chain again
        new.version = old.version + 1
        self._persist(old)
        self._persist(new)
        return old, new

    def _ancestors(self, source_id: str) -> set[str]:
        """Everything ``source_id`` supersedes, transitively."""
        seen: set[str] = set()
        cur = self.try_get(source_id)
        while cur is not None and cur.supersedes and cur.supersedes not in seen:
            seen.add(cur.supersedes)
            cur = self.try_get(cur.supersedes)
        return seen

    # -- reads -----------------------------------------------------------
    def exists(self, source_id: str) -> bool:
        return source_id in self._records

    def get(self, source_id: str) -> Source:
        if source_id not in self._records:
            raise KeyError(source_id)
        src = self._records[source_id]
        if not src.content:
            path = self._content_path(source_id)
            src.content = path.read_text(encoding="utf-8") if path.exists() else ""
        return src

    def try_get(self, source_id: str) -> Source | None:
        return self.get(source_id) if self.exists(source_id) else None

    def all(self) -> list[Source]:
        return [self.get(sid) for sid in sorted(self._records, key=address_sort_key)]

    def current_chain_head(self, source_id: str) -> Source | None:
        """Follow ``superseded_by`` to the newest source in the chain."""
        seen: set[str] = set()
        cur = self.try_get(source_id)
        while cur is not None and cur.superseded_by and cur.source_id not in seen:
            seen.add(cur.source_id)
            nxt = self.try_get(cur.superseded_by)
            if nxt is None:
                break
            cur = nxt
        return cur

    def total_tokens(self, counter) -> int:
        return sum(counter(s.content) for s in self.all())


# --------------------------------------------------------------------------
# Hex map
# --------------------------------------------------------------------------

_SIZE_THRESHOLDS = ((2_000, SizeClass.S), (10_000, SizeClass.M), (50_000, SizeClass.L))


class HexMap:
    """A lightweight project map.

    The whole map is held in memory and rewritten atomically on save.  At
    prototype scale that is far simpler than append-plus-compact and removes a
    class of partial-write bugs; the trade-off is documented in
    DESIGN_DECISIONS.md.
    """

    def __init__(self, path: Path, project_prefix: str) -> None:
        self.path = Path(path)
        self.prefix = project_prefix
        self._hexes: dict[str, Hex] = {}
        for d in read_jsonl(self.path):
            h = Hex.from_dict(d)
            self._hexes[h.hex_id] = h

    def __len__(self) -> int:
        return len(self._hexes)

    def __contains__(self, hex_id: object) -> bool:
        return hex_id in self._hexes

    def _next_id(self, epoch: int) -> str:
        seq = 0
        for hid in self._hexes:
            try:
                seq = max(seq, parse_hex_address(hid)[2])
            except ValueError:
                continue
        return hex_address(self.prefix, epoch, seq + 1)

    def add(
        self,
        title: str,
        type: HexType,
        epoch: int,
        *,
        summary: str = "",
        source_refs: list[str] | None = None,
        tags: list[str] | None = None,
        temperature: Temperature = Temperature.COLD,
        parent_hex: str | None = None,
        depth: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> Hex:
        hex_id = self._next_id(epoch)
        h = Hex(
            hex_id=hex_id,
            title=title,
            type=HexType(type),
            epoch=epoch,
            summary=summary,
            source_refs=list(source_refs or []),
            tags=list(tags or []),
            temperature=Temperature(temperature),
            parent_hex=parent_hex,
            depth=depth,
            uuid=machine_uuid(hex_id),
            metadata=dict(metadata or {}),
        )
        self._hexes[hex_id] = h
        return h

    def get(self, hex_id: str) -> Hex:
        return self._hexes[hex_id]

    def try_get(self, hex_id: str) -> Hex | None:
        return self._hexes.get(hex_id)

    def all(self) -> list[Hex]:
        return [self._hexes[k] for k in sorted(self._hexes, key=address_sort_key)]

    def find(
        self,
        *,
        hex_ids: Iterable[str] | None = None,
        types: Iterable[HexType | str] | None = None,
        statuses: Iterable[HexStatus | str] | None = None,
        temperatures: Iterable[Temperature | str] | None = None,
        tags: Iterable[str] | None = None,
        epoch: int | None = None,
        source_ref: str | None = None,
    ) -> list[Hex]:
        """Structured lookup.  All supplied criteria must match (AND)."""
        out = self.all()
        if hex_ids is not None:
            want = set(hex_ids)
            out = [h for h in out if h.hex_id in want]
        if types is not None:
            want = {HexType(t).value for t in types}
            out = [h for h in out if h.type.value in want]
        if statuses is not None:
            want = {HexStatus(s).value for s in statuses}
            out = [h for h in out if h.status.value in want]
        if temperatures is not None:
            want = {Temperature(t).value for t in temperatures}
            out = [h for h in out if h.temperature.value in want]
        if tags is not None:
            want = set(tags)
            out = [h for h in out if want & set(h.tags)]
        if epoch is not None:
            out = [h for h in out if h.epoch == epoch]
        if source_ref is not None:
            out = [h for h in out if source_ref in h.source_refs]
        return out

    def hex_for_source(self, source_id: str) -> Hex | None:
        matches = self.find(source_ref=source_id)
        return matches[0] if matches else None

    def index_view(self) -> list[dict[str, Any]]:
        """Header-only projection -- the cheap thing to scan or serialise."""
        return [h.header() for h in self.all()]

    # -- deterministic derived attributes --------------------------------
    def set_temperature(self, hex_id: str, temperature: Temperature) -> Hex:
        h = self.get(hex_id)
        h.temperature = Temperature(temperature)
        return h

    def retemper(self, hot: Iterable[str], warm: Iterable[str]) -> dict[str, int]:
        """Recompute every temperature from two explicit id sets.

        Pure bookkeeping: no model call, no scoring, no inference.  Anything
        not named is COLD.
        """
        hot_set, warm_set = set(hot), set(warm) - set(hot)
        counts = {"HOT": 0, "WARM": 0, "COLD": 0}
        for h in self._hexes.values():
            if h.hex_id in hot_set:
                h.temperature = Temperature.HOT
            elif h.hex_id in warm_set:
                h.temperature = Temperature.WARM
            else:
                h.temperature = Temperature.COLD
            counts[h.temperature.value] += 1
        return counts

    def recompute_size(self, hex_id: str, sources: SourceStore, pins: "PinStore",
                       relations: "RelationStore", counter) -> SizeClass:
        h = self.get(hex_id)
        weight = counter(h.summary)
        for sid in h.source_refs:
            src = sources.try_get(sid)
            if src is not None:
                weight += counter(src.content)
        weight += 200 * len(pins.for_hex(hex_id))
        weight += 100 * len(relations.of(hex_id))
        size = SizeClass.XL
        for threshold, cls in _SIZE_THRESHOLDS:
            if weight < threshold:
                size = cls
                break
        h.size_class = size
        h.metadata["size_weight_tokens"] = weight
        return size

    def save(self) -> None:
        atomic_write_jsonl(self.path, (h.to_dict() for h in self.all()))


# --------------------------------------------------------------------------
# Pin store
# --------------------------------------------------------------------------


class PinStore:
    def __init__(self, path: Path, project_prefix: str) -> None:
        self.path = Path(path)
        self.prefix = project_prefix
        self._pins: dict[str, Pin] = {}
        for d in read_jsonl(self.path):
            p = Pin.from_dict(d)
            self._pins[p.pin_id] = p

    def __len__(self) -> int:
        return len(self._pins)

    def _next_id(self) -> str:
        seq = 0
        for pid in self._pins:
            tail = pid.rsplit(".K", 1)[-1]
            if tail.isdigit():
                seq = max(seq, int(tail))
        return pin_address(self.prefix, seq + 1)

    def add(
        self,
        key: str,
        value: str,
        source_ref: str | None,
        *,
        critical: bool = False,
        hex_id: str | None = None,
        updated_at: str | None = None,
        note: str | None = None,
    ) -> Pin:
        """Create a pin.  An existing ACTIVE pin on the same key is superseded."""
        prior = self.by_key(key)
        pin = Pin(
            pin_id=self._next_id(),
            key=key,
            value=value,
            source_ref=source_ref,
            critical=critical,
            hex_id=hex_id,
            updated_at=updated_at,
            note=note,
            supersedes=prior.pin_id if prior else None,
        )
        if prior is not None:
            prior.status = PinStatus.SUPERSEDED
        self._pins[pin.pin_id] = pin
        return pin

    def get(self, pin_id: str) -> Pin:
        return self._pins[pin_id]

    def by_key(self, key: str) -> Pin | None:
        """The one live pin for a key, if any."""
        live = [p for p in self.all() if p.key == key and p.status is not PinStatus.SUPERSEDED]
        return live[-1] if live else None

    def all(self) -> list[Pin]:
        return [self._pins[k] for k in sorted(self._pins, key=address_sort_key)]

    def live(self) -> list[Pin]:
        return [p for p in self.all() if p.status is not PinStatus.SUPERSEDED]

    def critical(self) -> list[Pin]:
        return [p for p in self.live() if p.critical]

    def for_hex(self, hex_id: str) -> list[Pin]:
        return [p for p in self.all() if p.hex_id == hex_id]

    def save(self) -> None:
        atomic_write_jsonl(self.path, (p.to_dict() for p in self.all()))


# --------------------------------------------------------------------------
# Relation store
# --------------------------------------------------------------------------


class RelationStore:
    """A generic directed graph.  No degree limit, no geometry."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._edges: dict[tuple[str, str, str], Relation] = {}
        for d in read_jsonl(self.path):
            r = Relation.from_dict(d)
            self._edges[r.key()] = r

    def __len__(self) -> int:
        return len(self._edges)

    def add(self, src: str, type: str, dst: str) -> Relation:
        r = Relation(src=src, type=type, dst=dst)
        self._edges[r.key()] = r
        return r

    def all(self) -> list[Relation]:
        return [self._edges[k] for k in sorted(self._edges)]

    def of(self, node: str, *, direction: str = "both", type: str | None = None) -> list[Relation]:
        out = []
        for r in self.all():
            if type is not None and r.type != type:
                continue
            if direction in ("out", "both") and r.src == node:
                out.append(r)
            elif direction in ("in", "both") and r.dst == node:
                out.append(r)
        return out

    def neighbours(self, node: str, *, type: str | None = None) -> list[str]:
        seen: list[str] = []
        for r in self.of(node, type=type):
            other = r.dst if r.src == node else r.src
            if other not in seen:
                seen.append(other)
        return seen

    def save(self) -> None:
        atomic_write_jsonl(self.path, (r.to_dict() for r in self.all()))
