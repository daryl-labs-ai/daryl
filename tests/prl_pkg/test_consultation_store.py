"""R-consult v1 (ADR-PRL-0008) — kernel-backed tests: commit a consultation act via
PRLStore (Storage.append, certified chain) and read it back through RR by action_name.

Requires the real DSM kernel (dsm.core.storage / dsm.verify / dsm.rr) — same as
test_dsm_store.py and test_structural.py. No new writer is introduced: the act is
written through the already-registered prl/store module.
"""

from __future__ import annotations

from dsm.core.storage import Storage
from dsm.rr.index import RRIndexBuilder
from dsm.rr.navigator import RRNavigator
from dsm.verify import verify_shard

from prl.collectors import ConsultationAdapter
from prl.store import CONSULTATION_SHARD, ActResult, PRLStore
from prl.types import ConsultationNode, from_entry


def _store(tmp_path) -> PRLStore:
    return PRLStore(Storage(data_dir=str(tmp_path)))


def _act():
    return ConsultationAdapter().to_act(
        subject_id="ko-42", answer="use chunk_primary", producer="claude via adapter v1",
        confidence=0.7,
    )


# --- commit_act: certified, in the consultation shard, no new writer --------

def test_commit_act_certifies(tmp_path):
    store = _store(tmp_path)
    res = store.commit_act(_act())
    assert isinstance(res, ActResult)
    assert res.shard == CONSULTATION_SHARD
    assert res.act_id and res.tip_hash  # certification = chain tip hash
    report = verify_shard(store._storage, res.shard)
    assert str(report["status"]).endswith("OK")


def test_committed_act_has_action_name_and_round_trips(tmp_path):
    store = _store(tmp_path)
    act = _act()
    res = store.commit_act(act)
    entries = store._storage.read(res.shard, limit=100)
    assert entries and all(e.metadata.get("action_name") == "prl.consultation" for e in entries)
    back = from_entry(entries[0])
    assert isinstance(back, ConsultationNode)
    assert back.answer == act.answer and back.mode == "observation"
    assert back.mef.producer == "claude via adapter v1"


# --- RR-only read path by action_name --------------------------------------

def test_consultation_readable_via_rr(tmp_path):
    store = _store(tmp_path)
    res = store.commit_act(_act())

    builder = RRIndexBuilder(storage=store._storage, index_dir=str(tmp_path / "rr"))
    builder.build()
    nav = RRNavigator(builder, store._storage)

    records = nav.navigate_action("prl.consultation")
    entries = nav.resolve_entries(records)
    acts = [from_entry(e) for e in entries]
    assert any(getattr(a, "consultation_id", None) == res.act_id for a in acts)
