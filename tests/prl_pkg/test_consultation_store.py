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


# --- R-consult v2: read/display via ConsultationQuery + CLI (kernel) --------

def test_consultation_query_reads_via_rr(tmp_path):
    from prl.query.consultation_read import ConsultationQuery

    store = _store(tmp_path)
    a = ConsultationAdapter()
    store.commit_act(a.to_act(subject_id="ko-A", answer="obs",
                              producer="claude via adapter v1", confidence=0.6))
    store.commit_act(a.to_act(subject_id="ko-B", answer="prop",
                              producer="gpt via adapter v1", confidence=0.8, propose=True))

    views = ConsultationQuery(store._storage, tmp_path / "rr").list()
    by_subj = {v.subject_id: v for v in views}
    assert {"ko-A", "ko-B"} <= set(by_subj)
    assert by_subj["ko-A"].mode == "observation" and by_subj["ko-B"].mode == "proposal"
    assert by_subj["ko-A"].receipt and by_subj["ko-B"].receipt  # DSM receipt = entry hash

    only_b = ConsultationQuery(store._storage, tmp_path / "rr2").list(subject_id="ko-B")
    assert [v.subject_id for v in only_b] == ["ko-B"]


def test_cli_consultations_e2e(tmp_path, capsys):
    from prl.config import PRLConfig
    from prl.query import cli
    from prl.store import open_store

    config = PRLConfig(declared_projects=[tmp_path], storage_dir=tmp_path / "dsm")
    open_store(config).commit_act(
        ConsultationAdapter().to_act(subject_id="ko-Z", answer="hi",
                                     producer="claude via adapter v1", confidence=0.7)
    )
    rc = cli.main(["consultations", "--storage-dir", str(tmp_path / "dsm"),
                   "--rr-index-dir", str(tmp_path / "rr")])
    out = capsys.readouterr().out
    assert rc == 0
    assert "OBSERVATION on ko-Z" in out and "DSM receipt:" in out
