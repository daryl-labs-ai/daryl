#!/usr/bin/env python3
"""Toy DCP Provider — implements DCP v1.1 from SPECIFICATION ONLY.

NO imports from dsm, dsm_primitives, or any Daryl SDK.
The only dependencies are: json, hashlib, pathlib, datetime.

This provider reads/writes the SAME JSONL format as the DSM kernel,
but implements the 5 DCP primitives independently.

If this provider passes the DCP conformance suite, the specification
is sufficient to implement the protocol without the reference SDK.
"""
from __future__ import annotations
import json
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field


# =====================================================================
# DCP v1.1 Primitives — implemented from spec, not from SDK
# =====================================================================

# The DSM JSONL format (reverse-engineered from the spec, not imported):
# Each line: {"id":..., "timestamp":..., "session_id":..., "source":...,
#             "content":..., "shard":..., "hash":..., "prev_hash":...,
#             "metadata":..., "version":...}

# The DSM canonical hash (from ADR-0002 spec):
# hash_canonical({session_id, source, timestamp, metadata, content, prev_hash})


def _canonical_hash(entry: dict, prev_hash: Optional[str]) -> str:
    """Compute the DSM v1 canonical hash from the ADR-0002 spec.

    v1: = sha256(json.dumps({sort_keys, separators=(",",":"), ensure_ascii=True}).encode())
    """
    payload = {
        "session_id": entry.get("session_id", ""),
        "source": entry.get("source", ""),
        "timestamp": entry.get("timestamp", ""),
        "metadata": entry.get("metadata", {}),
        "content": entry.get("content", ""),
        "prev_hash": prev_hash,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"v1:{digest}"


def _verify_hash(entry: dict, stored_hash: str) -> bool:
    """Verify a stored hash against recomputed canonical hash."""
    # Support both v1: prefixed and bare hex (v0 legacy)
    prev_hash = entry.get("prev_hash")
    expected = _canonical_hash(entry, prev_hash)
    if stored_hash.startswith("v1:"):
        return expected == stored_hash
    if ":" not in stored_hash:
        # v0 legacy: bare hex, same canonical computation
        return expected.replace("v1:", "") == stored_hash
    return False


@dataclass
class ParticipationContext:
    project_id: str
    authorized: bool
    project_exists: bool
    entry_count: int
    last_activity: Optional[str] = None
    context_bundle: Optional[dict] = None


@dataclass
class ContextBundle:
    project_id: str
    integrity_ok: bool
    integrity_status: str
    total_decisions: int
    decisions: list = field(default_factory=list)
    catch_up_time_ms: float = 0.0


@dataclass
class Receipt:
    entry_id: str
    entry_hash: str
    agent_id: str
    task: str
    project_id: str
    timestamp: str
    receipt_hash: str


@dataclass
class IntegrityReport:
    status: str  # OK | TAMPERED | TRUNCATED
    entry_count: int
    chain_continuous: bool


class ToyDCPProvider:
    """A DCP v1.1 provider implemented from specification only.

    Reads/writes DSM-format JSONL files directly.
    No dependency on the Daryl SDK.
    """

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.shards_dir = self.data_dir / "shards"
        self.integrity_dir = self.data_dir / "integrity"
        self.shards_dir.mkdir(parents=True, exist_ok=True)
        self.integrity_dir.mkdir(parents=True, exist_ok=True)

    def _shard_dir(self, project_id: str) -> Path:
        family = project_id.replace("shard_", "")
        d = self.shards_dir / family
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _segment_files(self, project_id: str) -> list:
        d = self._shard_dir(project_id)
        return sorted(d.glob("*.jsonl"))

    def _active_segment(self, project_id: str) -> Path:
        segs = self._segment_files(project_id)
        if not segs:
            first = self._shard_dir(project_id) / f"{project_id.replace('shard_','')}_0001.jsonl"
            return first
        return segs[-1]

    def _read_all_entries(self, project_id: str) -> list:
        """Read all entries from all segments (chronological order)."""
        entries = []
        for seg in self._segment_files(project_id):
            with open(seg, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return entries

    def _read_pin(self, project_id: str) -> Optional[dict]:
        pin_path = self.integrity_dir / f"{project_id}_last_hash.json"
        if not pin_path.exists():
            return None
        try:
            with open(pin_path) as f:
                return json.load(f)
        except Exception:
            return None

    def _write_pin(self, project_id: str, last_hash: str, entry_count: int):
        pin_path = self.integrity_dir / f"{project_id}_last_hash.json"
        pin = {
            "shard_id": project_id,
            "last_hash": last_hash,
            "entry_count": entry_count,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        tmp = pin_path.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump(pin, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, pin_path)

    # == DCP Primitive 0: join_project ==

    def join_project(self, project_id: str, agent_id: str,
                     owner_id: str = "owner",
                     public_key: str = "",
                     provider_type: str = "active") -> ParticipationContext:
        """Join a project. Idempotent. Returns participation context."""
        entries = self._read_all_entries(project_id)
        project_exists = len(entries) > 0
        last_activity = entries[-1].get("timestamp") if entries else None

        # Authorization: in this toy provider, all actors are authorized.
        # A real provider would check the sovereignty policy.
        authorized = True

        # Auto-catch_up for convenience
        ctx = self.catch_up(project_id) if project_exists else None

        return ParticipationContext(
            project_id=project_id,
            authorized=authorized,
            project_exists=project_exists,
            entry_count=len(entries),
            last_activity=last_activity,
            context_bundle=ctx.__dict__ if ctx else None,
        )

    # == DCP Primitive 1: catch_up ==

    def catch_up(self, project_id: str) -> ContextBundle:
        import time
        t0 = time.monotonic()

        ir = self.verify(project_id)
        entries = self._read_all_entries(project_id)

        decisions = []
        for e in entries:  # already chronological
            decisions.append({
                "agent": e.get("source", "?"),
                "action": (e.get("metadata") or {}).get("action_name", "?"),
                "content": e.get("content", ""),
                "timestamp": e.get("timestamp", ""),
            })

        elapsed = (time.monotonic() - t0) * 1000

        return ContextBundle(
            project_id=project_id,
            integrity_ok=(ir.status == "OK"),
            integrity_status=ir.status,
            total_decisions=len(decisions),
            decisions=decisions,
            catch_up_time_ms=round(elapsed, 1),
        )

    # == DCP Primitive 2: publish_receipt ==

    def publish_receipt(self, project_id: str, agent_id: str,
                        task: str, result: str,
                        prev_hash: Optional[str] = None) -> Receipt:
        """Write an entry to the project shard + issue a receipt."""
        entries = self._read_all_entries(project_id)
        computed_prev = entries[-1].get("hash") if entries else None
        if prev_hash is None:
            prev_hash = computed_prev

        now = datetime.now(timezone.utc)
        entry = {
            "id": f"{agent_id}_{now.strftime('%H%M%S%f')}",
            "timestamp": now.isoformat(),
            "session_id": f"dcp_{agent_id}",
            "source": agent_id,
            "content": result,
            "shard": project_id,
            "prev_hash": prev_hash,
            "metadata": {"event_type": "decision", "action_name": task},
            "version": "v2.0",
        }
        entry_hash = _canonical_hash(entry, prev_hash)
        entry["hash"] = entry_hash

        # Append to active segment
        seg = self._active_segment(project_id)
        with open(seg, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        # Update pin
        self._write_pin(project_id, entry_hash, len(entries) + 1)

        # Create receipt
        receipt_payload = {
            "entry_id": entry["id"],
            "entry_hash": entry_hash,
            "agent_id": agent_id,
            "task": task,
            "project_id": project_id,
            "timestamp": now.isoformat(),
        }
        receipt_hash = "v1:" + hashlib.sha256(
            json.dumps(receipt_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

        return Receipt(
            entry_id=entry["id"],
            entry_hash=entry_hash,
            agent_id=agent_id,
            task=task,
            project_id=project_id,
            timestamp=now.isoformat(),
            receipt_hash=receipt_hash,
        )

    # == DCP Primitive 3: verify ==

    def verify(self, project_id: str) -> IntegrityReport:
        """Verify the hash chain of the project shard."""
        entries = self._read_all_entries(project_id)
        if not entries:
            return IntegrityReport(status="OK", entry_count=0, chain_continuous=True)

        prev_hash = None
        for i, entry in enumerate(entries):
            stored_hash = entry.get("hash", "")
            # Check hash validity
            if not _verify_hash(entry, stored_hash):
                return IntegrityReport(status="TAMPERED", entry_count=len(entries), chain_continuous=False)
            # Check chain continuity
            entry_prev = entry.get("prev_hash")
            if i == 0:
                if entry_prev is not None:
                    return IntegrityReport(status="TAMPERED", entry_count=len(entries), chain_continuous=False)
            else:
                if entry_prev != prev_hash:
                    return IntegrityReport(status="TAMPERED", entry_count=len(entries), chain_continuous=False)
            prev_hash = stored_hash

        # Check pin (truncation detection)
        pin = self._read_pin(project_id)
        if pin:
            expected_last = pin.get("last_hash")
            expected_count = pin.get("entry_count", 0)
            if expected_last and prev_hash != expected_last:
                return IntegrityReport(status="TRUNCATED", entry_count=len(entries), chain_continuous=True)
            if expected_count and len(entries) < expected_count:
                return IntegrityReport(status="TRUNCATED", entry_count=len(entries), chain_continuous=True)

        return IntegrityReport(status="OK", entry_count=len(entries), chain_continuous=True)

    # == DCP Primitive 4: project_context ==

    def project_context(self, project_id: str) -> dict:
        """Return a prompt-ready provenance block."""
        entries = self._read_all_entries(project_id)
        ir = self.verify(project_id)

        return {
            "project_id": project_id,
            "entry_hashes": [e.get("hash", "") for e in entries[-20:]],
            "entry_count": len(entries),
            "integrity": ir.status,
            "agents": list(set(e.get("source", "?") for e in entries)),
            "verification_hint": f"dsm verify --shard {project_id}" if ir.status == "OK" else "INTEGRITY FAILURE",
        }
