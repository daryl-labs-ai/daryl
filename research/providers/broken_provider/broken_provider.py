#!/usr/bin/env python3
"""Broken DCP Provider — deliberately non-conformant."""
from __future__ import annotations
import json, hashlib, os, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

def _wrong_hash(entry, prev_hash):
    """B1: md5 instead of sha256, no canonical JSON."""
    raw = str(entry.get("content","")) + str(prev_hash)
    return "v1:" + hashlib.md5(raw.encode()).hexdigest()

@dataclass
class ParticipationContext:
    project_id: str; authorized: bool; project_exists: bool; entry_count: int
    last_activity: Optional[str] = None; context_bundle: Optional[dict] = None

@dataclass
class ContextBundle:
    project_id: str; integrity_ok: bool; integrity_status: str; total_decisions: int
    decisions: list = field(default_factory=list); catch_up_time_ms: float = 0.0

@dataclass
class Receipt:
    entry_id: str; entry_hash: str; agent_id: str; task: str
    project_id: str; timestamp: str; receipt_hash: str

@dataclass
class IntegrityReport:
    status: str; entry_count: int; chain_continuous: bool

class BrokenDCPProvider:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        (self.data_dir / "shards").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "integrity").mkdir(parents=True, exist_ok=True)

    def _sd(self, pid):
        d = self.data_dir / "shards" / pid.replace("shard_","")
        d.mkdir(parents=True, exist_ok=True); return d

    def _segs(self, pid): return sorted(self._sd(pid).glob("*.jsonl"))
    def _aseg(self, pid):
        s = self._segs(pid)
        return s[-1] if s else self._sd(pid) / f"{pid.replace('shard_','')}_0001.jsonl"

    def _read(self, pid):
        out = []
        for seg in self._segs(pid):
            for line in open(seg):
                if line.strip():
                    try: out.append(json.loads(line))
                    except: pass
        return out

    def _rpin(self, pid):
        p = self.data_dir / "integrity" / f"{pid}_last_hash.json"
        if p.exists():
            try: return json.load(open(p))
            except: pass
        return None

    def _wpin(self, pid, h, c):
        json.dump({"last_hash": h, "entry_count": c},
                  open(self.data_dir / "integrity" / f"{pid}_last_hash.json", "w"))

    def join_project(self, project_id, agent_id, owner_id="owner", public_key="", provider_type="active"):
        entries = self._read(project_id)
        ctx = self.catch_up(project_id) if entries else None
        return ParticipationContext(project_id, True, len(entries)>0, len(entries),
                                    context_bundle=ctx.__dict__ if ctx else None)

    def catch_up(self, project_id):
        t0 = time.monotonic()
        ir = self.verify(project_id)
        entries = self._read(project_id)
        decisions = [{"agent": e.get("source","?"), "content": e.get("content",""),
                      "action": (e.get("metadata") or {}).get("action_name","?"),
                      "timestamp": e.get("timestamp","")} for e in entries]
        return ContextBundle(project_id, ir.status=="OK", ir.status, len(decisions),
                             decisions, round((time.monotonic()-t0)*1000,1))

    def publish_receipt(self, project_id, agent_id, task, result, prev_hash=None):
        """B1-B4: breaks hash, fields, timestamp, receipt."""
        entries = self._read(project_id)
        computed_prev = entries[-1].get("hash") if entries else None
        if prev_hash is None: prev_hash = computed_prev
        entry = {
            "id": f"{agent_id}_broken",
            "timestamp": "not-a-timestamp",  # B3
            "source": agent_id, "content": result, "shard": project_id,
            "prev_hash": prev_hash,
            # B2: MISSING session_id, metadata, version
        }
        entry_hash = _wrong_hash(entry, prev_hash)  # B1
        entry["hash"] = entry_hash
        with open(self._aseg(project_id), "a") as f:
            f.write(json.dumps(entry) + "\n")
        self._wpin(project_id, entry_hash, len(entries)+1)
        return Receipt(entry["id"], entry_hash, agent_id,
                       "", "", "not-a-timestamp", "broken")  # B4

    def verify(self, project_id):
        entries = self._read(project_id)
        if not entries: return IntegrityReport("OK", 0, True)
        prev = None
        for i, e in enumerate(entries):
            stored = e.get("hash","")
            expected = _wrong_hash(e, e.get("prev_hash"))
            if expected != stored: return IntegrityReport("TAMPERED", len(entries), False)
            if i > 0 and e.get("prev_hash") != prev:
                return IntegrityReport("TAMPERED", len(entries), False)
            prev = stored
        return IntegrityReport("OK", len(entries), True)

    def project_context(self, project_id):
        entries = self._read(project_id)
        return {"project_id": project_id,
                "entry_hashes": [e.get("hash","") for e in entries[-20:]],
                "entry_count": len(entries), "integrity": "OK",
                "agents": list(set(e.get("source","?") for e in entries))}
