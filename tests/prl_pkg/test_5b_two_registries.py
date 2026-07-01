"""#5b-A experiment (repo-side proof) — two *independent* DSM registries, no shared tip.

The single question: can two independent DSM registries, with **no shared tip**, certify and
reconcile the *same acts* while preserving identity, `standing`, `governed_standing`,
`object_standing`, and receipt verifiability?

The crux (so the gate reads right): across two independent registries the **receipts are NOT
identical** — each mints its own `prev_hash` chain and tip, so the same act gets a **different
`Entry.hash`** in each. That is expected and correct (receipts are substrate-relative, #3
reserve). The proof is three things together: **(i) semantic identity** by value-identity
(`claim_id`/`subject_id`), **(ii) cross-registry verifiability** by portable receipts
(`exchange`, verified against the issuer's DSM), and **(iii) proof-space membership** by
attestation (`witness`) — with **no single global tip**.

Read/proof-side only: no core kernel change (`Storage.append` / `Entry.hash` / `prev_hash` /
`verify_shard` untouched); no global/cross-registry tip; no quorum/consensus/CAS; no signatures
added to the append/verify path. Uses the existing kernel primitives (`verify_shard`,
`exchange`, `witness`) + the PRL read queries. **No credential** (human resolutions only).
The run IS the proof: it asserts the 8-point gate, green, no credential.
"""

from __future__ import annotations

import json

from dsm.core.storage import Storage
from dsm.exchange import (
    TaskReceipt,
    issue_receipt,
    verify_receipt,
    verify_receipt_against_storage,
)
from dsm.status import ReceiptStatus, StorageReceiptStatus
from dsm.verify import verify_shard
from dsm.witness import ShardWitness

from prl.collectors import ConsultationAdapter, make_resolution
from prl.query.standing_read import StandingQuery
from prl.query.subject_read import SubjectStandingsQuery
from prl.store import CONSULTATION_SHARD, PRLStore


def _materialize(store: PRLStore) -> None:
    """The *identical* act set (value-identical `claim_id`/`subject_id`; human resolutions, no
    credential). Each registry certifies it on its OWN chain, minting its own receipts:
    - K1 contested — two distinct authorities opposed (alice:accepted, bob:rejected);
    - subject S = {K1 (contested), K2 (accepted)} → ADR-0012 precedence ⇒ object contested;
    - K3 clean — a single accepted ⇒ governed == raw == accepted.
    """
    a = ConsultationAdapter()
    for cid, subj in (("K1", "S"), ("K2", "S"), ("K3", "S3")):
        store.commit_act(a.to_act(
            subject_id=subj, answer=f"proposal {cid}", producer="p",
            agent_id="agent.x", claim_id=cid, confidence=0.7, propose=True))
    store.commit_act(make_resolution(target_claim_id="K1", decision="accepted", agent_id="alice"))
    store.commit_act(make_resolution(target_claim_id="K1", decision="rejected", agent_id="bob"))
    store.commit_act(make_resolution(target_claim_id="K2", decision="accepted", agent_id="carol"))
    store.commit_act(make_resolution(target_claim_id="K3", decision="accepted", agent_id="dave"))


def _readings(store: PRLStore, index_dir) -> dict:
    """The PRL governed readings over this registry's own RR (value-identity join, #3)."""
    sq = StandingQuery(store._storage, index_dir)
    subj = SubjectStandingsQuery(store._storage, index_dir).standings_of_subject("S")
    return {
        "K1_governed": sq.standing_of("K1").governed_standing,
        "K3_governed": sq.standing_of("K3").governed_standing,
        "S_object": subj.object_standing,
    }


def test_5b_two_independent_registries(tmp_path):
    # --- Setup: two independent DSM instances, separate storage roots ⇒ separate tips ---
    root_a, root_b = tmp_path / "R_A", tmp_path / "R_B"
    store_a = PRLStore(Storage(data_dir=str(root_a)))
    store_b = PRLStore(Storage(data_dir=str(root_b)))
    _materialize(store_a)
    _materialize(store_b)

    # === Gate 1 — two separate DSM instances (distinct roots, distinct integrity dirs) ===
    assert root_a != root_b
    tip_file_a = root_a / "integrity" / f"{CONSULTATION_SHARD}_last_hash.json"
    tip_file_b = root_b / "integrity" / f"{CONSULTATION_SHARD}_last_hash.json"
    assert tip_file_a.exists() and tip_file_b.exists()  # each registry has its OWN tip file

    # === Gate 2 — different tips, NO shared {shard}_last_hash.json ===
    tip_a = store_a._storage.read(CONSULTATION_SHARD, limit=1)[0].hash
    tip_b = store_b._storage.read(CONSULTATION_SHARD, limit=1)[0].hash
    assert tip_a and tip_b and tip_a != tip_b  # substrate-relative receipts differ (expected)
    assert (json.loads(tip_file_a.read_text())["last_hash"]
            != json.loads(tip_file_b.read_text())["last_hash"])

    # === Gate 3 — each chain verify_shard-valid (internal integrity holds per registry) ===
    rep_a = verify_shard(store_a._storage, CONSULTATION_SHARD)
    rep_b = verify_shard(store_b._storage, CONSULTATION_SHARD)
    assert str(rep_a["status"]).endswith("OK") and str(rep_b["status"]).endswith("OK")

    # === Gate 4 + 5 — same claim_id/subject_id reconciled by value-identity; identical
    #     governed standings from EITHER registry (the #3 join, no shared tip, no new rule) ===
    read_a = _readings(store_a, tmp_path / "rr_a")
    read_b = _readings(store_b, tmp_path / "rr_b")
    assert read_a == read_b  # identical across the two independent registries
    assert read_a["K1_governed"] == "contested"
    assert read_a["K3_governed"] == "accepted"
    assert read_a["S_object"] == "contested"  # ADR-0012 precedence (a contested claim)

    # === Gate 6 — a receipt for an R_A act is portable and verifiable against R_A's DSM ===
    entry_a = store_a._storage.read(CONSULTATION_SHARD, limit=1)[0]  # newest act in R_A
    receipt = issue_receipt(
        store_a._storage, agent_id="R_A", entry_id=entry_a.id,
        shard_id=CONSULTATION_SHARD, task_description="an R_A act")
    portable = TaskReceipt.from_json(receipt.to_json())  # carried to B's context
    assert verify_receipt(portable)["status"] == ReceiptStatus.INTACT  # self-integrity
    confirmed = verify_receipt_against_storage(store_a._storage, portable)  # against R_A's DSM
    assert confirmed["status"] == StorageReceiptStatus.CONFIRMED and confirmed["hash_matches"]

    # receipts differ across registries by design (same semantic act, different Entry.hash)
    entry_b = store_b._storage.read(CONSULTATION_SHARD, limit=1)[0]
    assert entry_a.hash != entry_b.hash

    # === Gate 7 — a tampered act/receipt fails verification ===
    tampered = TaskReceipt.from_json(receipt.to_json())
    tampered.entry_hash = "v1:" + "0" * 64  # forge the certified act hash
    assert verify_receipt(tampered)["status"] == ReceiptStatus.TAMPERED  # receipt integrity broken
    assert (verify_receipt_against_storage(store_a._storage, tampered)["status"]
            == StorageReceiptStatus.HASH_MISMATCH)  # act does not match the forged receipt

    # === Gate 8 — tips attested without a merged chain (witness on each; membership by
    #     attestation, no global tip). The PAIR of attestations establishes one proof-space ===
    w_a = ShardWitness(witness_dir=str(tmp_path / "witness_a"))
    w_b = ShardWitness(witness_dir=str(tmp_path / "witness_b"))
    rec_a = w_a.capture(store_a._storage, CONSULTATION_SHARD)
    rec_b = w_b.capture(store_b._storage, CONSULTATION_SHARD)
    assert w_a.verify_record(rec_a) and w_b.verify_record(rec_b)  # both attestations valid
    assert rec_a["tip_hash"] != rec_b["tip_hash"]  # distinct tips — no merged chain / global tip
    assert str(w_a.verify_shard_against_witness(store_a._storage, CONSULTATION_SHARD)["status"]).endswith("OK")
    assert str(w_b.verify_shard_against_witness(store_b._storage, CONSULTATION_SHARD)["status"]).endswith("OK")


def test_5b_metadata_report(tmp_path, capsys):
    """Emit the experiment metadata (the two distinct tips, the two differing receipts for the
    same semantic act, the portable-receipt verification + tamper-fail, the two attestations).
    Titles/hashes/statuses only — no conversation bodies."""
    store_a = PRLStore(Storage(data_dir=str(tmp_path / "R_A")))
    store_b = PRLStore(Storage(data_dir=str(tmp_path / "R_B")))
    _materialize(store_a)
    _materialize(store_b)

    ea = store_a._storage.read(CONSULTATION_SHARD, limit=1)[0]
    eb = store_b._storage.read(CONSULTATION_SHARD, limit=1)[0]
    ra = issue_receipt(store_a._storage, "R_A", ea.id, CONSULTATION_SHARD, "act")
    rb = issue_receipt(store_b._storage, "R_B", eb.id, CONSULTATION_SHARD, "act")
    conf = verify_receipt_against_storage(store_a._storage, ra)
    tampered = TaskReceipt.from_json(ra.to_json())
    tampered.entry_hash = "v1:" + "0" * 64
    tamper_status = verify_receipt_against_storage(store_a._storage, tampered)["status"]
    wa = ShardWitness(witness_dir=str(tmp_path / "wa")).capture(store_a._storage, CONSULTATION_SHARD)
    wb = ShardWitness(witness_dir=str(tmp_path / "wb")).capture(store_b._storage, CONSULTATION_SHARD)

    print("\n=== #5b-A metadata (two independent registries) ===")
    print(f"R_A tip: {ea.hash}")
    print(f"R_B tip: {eb.hash}   (distinct — no shared tip)")
    print(f"same-act receipts differ: {ra.entry_hash[:20]}… vs {rb.entry_hash[:20]}…")
    print(f"portable receipt vs R_A DSM: {conf['status']}   | tampered: {tamper_status}")
    print(f"witness R_A tip={wa['tip_hash'][:16]}… count={wa['entry_count']} | "
          f"witness R_B tip={wb['tip_hash'][:16]}… count={wb['entry_count']}")

    assert ea.hash != eb.hash
    assert conf["status"] == StorageReceiptStatus.CONFIRMED
    assert tamper_status == StorageReceiptStatus.HASH_MISMATCH
