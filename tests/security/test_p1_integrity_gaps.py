"""
P1 — Adversarial tests for the integrity gaps found by the code verification
of the feasibility study (main @ ea6f84f, v1.0.2).

Threat model: an attacker with write access to the agent's data directory
(shards, integrity pins, anchor log) but WITHOUT the verifier's out-of-band
material (a client-held checkpoint, a trusted public key).

Each test reproduces one defect as it existed at ea6f84f and asserts the
fixed behaviour:

  G1  anchor.verify_commitment said VERIFIED after the action name, the
      params hash, or the commitment hashes were altered/removed.
  G2  verify_shard said OK after truncation + deletion of the pin (the pin
      lives next to the data). A client-held checkpoint must catch it, and a
      non-empty shard without any completeness proof must not be OK.
  G3  Entries are an unkeyed hash chain: a full rewrite with recomputed
      hashes is invisible. A checkpoint signed by the agent key and checked
      against a trusted public key must catch it; DarylAgent signs by default.
  G4  issue_receipt did not sign; a receipt edited "refund 50" -> "refund
      5000" with a recomputed hash stayed INTACT; signatures were checked
      against the key embedded in the receipt itself.
"""

import json

import pytest

from dsm.anchor import (
    AnchorLog,
    post_commit,
    pre_commit,
    verify_all_commitments,
    verify_commitment,
)
from dsm.core.storage import Storage, _compute_canonical_entry_hash
from dsm.exchange import (
    TaskReceipt,
    _compute_receipt_hash,
    _receipt_payload,
    issue_receipt,
    verify_receipt,
)
from dsm.signing import AgentSigning
from dsm.checkpoint import make_checkpoint
from dsm.verify import verify_shard

from ._helpers import append_n, make_entry, truncate_last_segment

nacl = pytest.importorskip("nacl.signing")


def _status(result) -> str:
    s = result["status"]
    return getattr(s, "value", str(s))


# --------------------------------------------------------------------------
# G1 — anchor commitments
# --------------------------------------------------------------------------


def _rewrite_log(log: AnchorLog, mutate) -> None:
    records = log.read_log()
    for r in records:
        mutate(r)
    log.log_path.write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in records), encoding="utf-8"
    )


def _committed_pair(tmp_path):
    log = AnchorLog(str(tmp_path / "anchors"))
    pre = pre_commit(log, "intent-1", "refund", {"amount": 50})
    post_commit(log, "intent-1", {"ok": True}, commitment_hash=pre["commitment_hash"])
    return log, pre


class TestG1AnchorCommitments:
    def test_honest_pair_verifies(self, tmp_path):
        log, _ = _committed_pair(tmp_path)
        assert verify_commitment(log, "intent-1")["status"] == "VERIFIED"

    def test_action_name_edit_is_detected(self, tmp_path):
        log, _ = _committed_pair(tmp_path)

        def mutate(r):
            if r.get("type") == "pre_commit":
                r["action_name"] = "transfer_all"

        _rewrite_log(log, mutate)
        assert verify_commitment(log, "intent-1")["status"] != "VERIFIED"

    def test_params_hash_edit_is_detected(self, tmp_path):
        log, _ = _committed_pair(tmp_path)

        def mutate(r):
            if r.get("type") == "pre_commit":
                r["params_hash"] = "0" * 64

        _rewrite_log(log, mutate)
        assert verify_commitment(log, "intent-1")["status"] != "VERIFIED"

    def test_removed_commitment_hashes_are_detected(self, tmp_path):
        log, _ = _committed_pair(tmp_path)

        def mutate(r):
            r.pop("commitment_hash", None)

        _rewrite_log(log, mutate)
        result = verify_commitment(log, "intent-1")
        assert result["status"] != "VERIFIED"
        assert verify_all_commitments(log)["status"] == "VIOLATIONS_FOUND"

    def test_post_without_commitment_is_not_verified(self, tmp_path):
        log = AnchorLog(str(tmp_path / "anchors"))
        pre_commit(log, "intent-1", "refund", {"amount": 50})
        post_commit(log, "intent-1", {"ok": True})  # no binding
        assert verify_commitment(log, "intent-1")["status"] != "VERIFIED"

    def test_duplicate_pre_commit_is_detected(self, tmp_path):
        log, _ = _committed_pair(tmp_path)
        # A second, later pre_commit for the same intent (shadowing attempt).
        pre_commit(log, "intent-1", "transfer_all", {"amount": 5000})
        assert verify_commitment(log, "intent-1")["status"] != "VERIFIED"

    def test_full_recompute_is_caught_by_expected_params(self, tmp_path):
        """An attacker who rewrites the pair coherently (recomputing every hash)
        is only caught by material held elsewhere: the original action/params
        or the commitment hash."""
        log, pre = _committed_pair(tmp_path)
        log.log_path.unlink()
        forged = pre_commit(log, "intent-1", "refund", {"amount": 5000})
        post_commit(log, "intent-1", {"ok": True}, commitment_hash=forged["commitment_hash"])

        assert verify_commitment(log, "intent-1")["status"] == "VERIFIED"  # self-consistent
        by_params = verify_commitment(
            log, "intent-1", action_name="refund", params={"amount": 50}
        )
        assert by_params["status"] == "PARAMS_MISMATCH"
        by_hash = verify_commitment(
            log, "intent-1", expected_commitment_hash=pre["commitment_hash"]
        )
        assert by_hash["status"] == "HASH_MISMATCH"


# --------------------------------------------------------------------------
# G2 — completeness proof must not live only next to the data
# --------------------------------------------------------------------------


class TestG2ClientCheckpoint:
    def test_truncation_plus_pin_deletion_is_not_ok(self, tmp_path):
        storage = Storage(data_dir=str(tmp_path))
        append_n(storage, 10)
        truncate_last_segment(storage, "sessions", 4)
        (storage.integrity_dir / "sessions_last_hash.json").unlink()

        result = verify_shard(Storage(data_dir=str(tmp_path)), "sessions")
        assert _status(result) != "OK"
        assert result["pin_status"] == "UNPINNED"

    def test_client_checkpoint_catches_truncation_without_pin(self, tmp_path):
        storage = Storage(data_dir=str(tmp_path))
        append_n(storage, 10)
        cp = make_checkpoint(storage, "sessions")  # handed to the client
        truncate_last_segment(storage, "sessions", 4)
        (storage.integrity_dir / "sessions_last_hash.json").unlink()

        result = verify_shard(Storage(data_dir=str(tmp_path)), "sessions", checkpoint=cp)
        assert _status(result) == "TAMPERED"
        assert result["checkpoint_status"] == "TRUNCATED"

    def test_client_checkpoint_catches_full_deletion(self, tmp_path):
        storage = Storage(data_dir=str(tmp_path))
        append_n(storage, 5)
        cp = make_checkpoint(storage, "sessions")
        truncate_last_segment(storage, "sessions", 5)
        (storage.integrity_dir / "sessions_last_hash.json").unlink()

        result = verify_shard(Storage(data_dir=str(tmp_path)), "sessions", checkpoint=cp)
        assert _status(result) == "TAMPERED"

    def test_growth_after_checkpoint_is_ok(self, tmp_path):
        storage = Storage(data_dir=str(tmp_path))
        append_n(storage, 5)
        cp = make_checkpoint(storage, "sessions")
        append_n(storage, 3)

        result = verify_shard(Storage(data_dir=str(tmp_path)), "sessions", checkpoint=cp)
        assert _status(result) == "OK"
        assert result["checkpoint_status"] == "CHECKPOINT_OK"

    def test_checkpoint_from_another_shard_is_rejected(self, tmp_path):
        storage = Storage(data_dir=str(tmp_path))
        append_n(storage, 3, shard="other")
        append_n(storage, 3)
        cp = make_checkpoint(storage, "other")
        result = verify_shard(storage, "sessions", checkpoint=cp)
        assert _status(result) == "TAMPERED"
        assert result["checkpoint_status"] == "SHARD_MISMATCH"


# --------------------------------------------------------------------------
# G3 — unkeyed chain: full rewrite needs a signed checkpoint to be caught
# --------------------------------------------------------------------------


def _rewrite_whole_chain(storage, shard_id: str, new_contents):
    """Rewrite every entry of the shard and recompute the whole chain + pin,
    as an attacker with disk access (but no key) can do."""
    seg_files = storage.segment_manager.get_segment_files_ordered(shard_id)
    for f in seg_files:
        f.unlink()
    (storage.integrity_dir / f"{shard_id}_last_hash.json").unlink()
    fresh = Storage(data_dir=str(storage.data_dir))
    for c in new_contents:
        fresh.append(make_entry(c, shard_id))
    return fresh


class TestG3SignedCheckpoint:
    def test_full_rewrite_passes_plain_verification(self, tmp_path):
        """Documents the residual limit: without out-of-band material a
        coherent rewrite is indistinguishable from the original."""
        storage = Storage(data_dir=str(tmp_path))
        append_n(storage, 4)
        forged = _rewrite_whole_chain(storage, "sessions", [f"forged-{i}" for i in range(4)])
        assert _status(verify_shard(forged, "sessions")) == "OK"

    def test_signed_checkpoint_catches_full_rewrite(self, tmp_path):
        storage = Storage(data_dir=str(tmp_path))
        signer = AgentSigning(str(tmp_path / "keys"), "agent-b")
        signer.generate_keypair()
        trusted = signer.get_public_key()
        append_n(storage, 4)
        cp = make_checkpoint(storage, "sessions", signing=signer)

        forged = _rewrite_whole_chain(storage, "sessions", [f"forged-{i}" for i in range(4)])
        result = verify_shard(forged, "sessions", checkpoint=cp, trusted_public_key=trusted)
        assert _status(result) == "TAMPERED"
        assert result["checkpoint_status"] == "REWRITTEN"

    def test_forged_checkpoint_without_key_is_rejected(self, tmp_path):
        storage = Storage(data_dir=str(tmp_path))
        signer = AgentSigning(str(tmp_path / "keys"), "agent-b")
        signer.generate_keypair()
        trusted = signer.get_public_key()
        append_n(storage, 4)
        forged = _rewrite_whole_chain(storage, "sessions", ["x"] * 4)
        attacker = AgentSigning(str(tmp_path / "attacker"), "agent-b")
        attacker.generate_keypair()
        cp = make_checkpoint(forged, "sessions", signing=attacker)

        result = verify_shard(forged, "sessions", checkpoint=cp, trusted_public_key=trusted)
        assert _status(result) == "TAMPERED"
        assert result["checkpoint_status"] == "UNTRUSTED_KEY"

        # Same forgery, but the attacker embeds the trusted key in the checkpoint.
        cp["public_key"] = trusted
        result = verify_shard(forged, "sessions", checkpoint=cp, trusted_public_key=trusted)
        assert _status(result) == "TAMPERED"
        assert result["checkpoint_status"] == "SIGNATURE_INVALID"

    def test_trusted_key_requires_a_signed_checkpoint(self, tmp_path):
        storage = Storage(data_dir=str(tmp_path))
        append_n(storage, 2)
        cp = make_checkpoint(storage, "sessions")  # unsigned
        result = verify_shard(storage, "sessions", checkpoint=cp, trusted_public_key="00" * 32)
        assert _status(result) == "TAMPERED"
        assert result["checkpoint_status"] == "UNSIGNED"

    def test_agent_signs_by_default(self, tmp_path):
        from dsm.agent import DarylAgent

        agent = DarylAgent("agent-a", data_dir=str(tmp_path / "a"), startup_verify=False)
        assert agent.public_key() is not None
        agent.start()
        intent = agent.intend("refund", {"amount": 50})
        agent.confirm(intent, {"ok": True})
        cps = agent.checkpoint()
        assert cps and all(cp.get("signature") for cp in cps)
        for cp in cps:
            r = agent.verify(cp["shard_id"], checkpoint=cp, trusted_public_key=agent.public_key())
            assert _status(r) == "OK", r
        sigs = agent.verify_entry_signatures(trusted_public_key=agent.public_key())
        assert sigs["status"] == "ALL_VALID" and sigs["checked"] >= 1


# --------------------------------------------------------------------------
# G4 — receipts
# --------------------------------------------------------------------------


def _issuer(tmp_path):
    storage = Storage(data_dir=str(tmp_path / "b"))
    e = storage.append(make_entry("refund 50", "work"))
    signer = AgentSigning(str(tmp_path / "b_keys"), "agent-b")
    signer.generate_keypair()
    return storage, e, signer


def _forge(receipt: TaskReceipt, **changes) -> TaskReceipt:
    d = receipt.to_dict()
    d.update(changes)
    forged = TaskReceipt.from_dict(d)
    forged.receipt_hash = _compute_receipt_hash(_receipt_payload(forged))
    return forged


class TestG4Receipts:
    def test_issue_receipt_signs_when_given_a_key(self, tmp_path):
        storage, e, signer = _issuer(tmp_path)
        r = issue_receipt(storage, "agent-b", e.id, "work", "refund 50", signing=signer)
        assert r.signature and r.public_key == signer.get_public_key()
        v = verify_receipt(r, trusted_public_key=signer.get_public_key())
        assert _status(v) == "INTACT" and v["authenticated"] is True

    def test_edited_receipt_with_recomputed_hash_is_not_intact(self, tmp_path):
        storage, e, signer = _issuer(tmp_path)
        r = issue_receipt(storage, "agent-b", e.id, "work", "refund 50", signing=signer)
        forged = _forge(r, task_description="refund 5000")
        v = verify_receipt(forged, trusted_public_key=signer.get_public_key())
        assert _status(v) == "SIGNATURE_INVALID"
        assert v["authenticated"] is False

    def test_unsigned_forgery_is_not_intact(self, tmp_path):
        storage, e, _ = _issuer(tmp_path)
        r = issue_receipt(storage, "agent-b", e.id, "work", "refund 50")
        forged = _forge(r, task_description="refund 5000")
        v = verify_receipt(forged)
        assert _status(v) != "INTACT"
        assert v["authenticated"] is False

    def test_self_embedded_key_is_not_trusted(self, tmp_path):
        """Attacker re-signs the forged receipt with their own key and embeds it."""
        storage, e, signer = _issuer(tmp_path)
        r = issue_receipt(storage, "agent-b", e.id, "work", "refund 50", signing=signer)
        attacker = AgentSigning(str(tmp_path / "evil"), "agent-b")
        attacker.generate_keypair()
        forged = _forge(r, task_description="refund 5000")
        forged.signature = attacker.sign_receipt(forged.receipt_hash)
        forged.public_key = attacker.get_public_key()

        assert _status(verify_receipt(forged)) != "INTACT"
        v = verify_receipt(forged, trusted_public_key=signer.get_public_key())
        assert _status(v) == "UNTRUSTED_KEY"
        assert v["authenticated"] is False

    def test_dispatch_hash_is_bound(self, tmp_path):
        storage, e, signer = _issuer(tmp_path)
        r = issue_receipt(
            storage, "agent-b", e.id, "work", "refund 50",
            dispatch_hash="a" * 64, signing=signer,
        )
        r.dispatch_hash = "b" * 64  # swap causal binding, keep hash + signature
        v = verify_receipt(r, trusted_public_key=signer.get_public_key())
        assert _status(v) == "TAMPERED"

    def test_agent_receive_requires_trusted_issuer_key(self, tmp_path):
        from dsm.agent import DarylAgent

        b = DarylAgent("agent-b", data_dir=str(tmp_path / "b"), startup_verify=False)
        a = DarylAgent("agent-a", data_dir=str(tmp_path / "a"), startup_verify=False)
        b.start()
        intent = b.intend("refund", {"amount": 50})
        entry = b.confirm(intent, {"ok": True})
        receipt = b.issue_receipt(entry.id, entry.shard, "refund 50")

        # Unknown issuer key -> not stored.
        out = a.receive_receipt(json.dumps(receipt))
        assert out["stored"] is False

        a.import_agent_key("agent-b", b.public_key())
        assert a.receive_receipt(json.dumps(receipt))["stored"] is True

        forged = TaskReceipt.from_dict(receipt)
        forged = _forge(forged, task_description="refund 5000")
        out = a.receive_receipt(forged.to_json())
        assert out["stored"] is False
        assert out["integrity"] == "SIGNATURE_INVALID"


def test_reference_hash_helper_still_matches_core():
    """Guard: the forgery helpers above use the same canonical hash as the kernel."""
    e = make_entry("x")
    assert _compute_canonical_entry_hash(e, None)


# --------------------------------------------------------------------------
# Review round 2 — three further cases reproduced by the reviewer
# --------------------------------------------------------------------------


class TestR2SigningFailsClosed:
    def test_wrong_password_refuses_to_start(self, tmp_path):
        from dsm.agent import DarylAgent, SigningError

        DarylAgent("agent-a", data_dir=str(tmp_path), startup_verify=False,
                   signing_password="right")
        with pytest.raises(SigningError):
            DarylAgent("agent-a", data_dir=str(tmp_path), startup_verify=False,
                       signing_password="wrong")

    def test_signing_failure_fails_the_operation(self, tmp_path, monkeypatch):
        from dsm.agent import DarylAgent, SigningError

        agent = DarylAgent("agent-a", data_dir=str(tmp_path), startup_verify=False)
        agent.start()

        def boom(_):
            raise ValueError("Failed to load keypair")

        monkeypatch.setattr(agent._signing, "sign_entry", boom)
        with pytest.raises(SigningError):
            agent.intend("refund", {"amount": 50})


def _signed_agent(tmp_path):
    from dsm.agent import DarylAgent

    agent = DarylAgent("agent-a", data_dir=str(tmp_path), startup_verify=False)
    agent.start()
    for amount in (50, 60):
        i = agent.intend("refund", {"amount": amount})
        agent.confirm(i, {"ok": True})
    return agent


class TestR2SignatureCoverage:
    def test_all_signatures_deleted_is_not_all_valid(self, tmp_path):
        agent = _signed_agent(tmp_path)
        assert agent.verify_entry_signatures()["status"] == "ALL_VALID"

        _rewrite_log(agent._anchor_log, lambda r: None)  # normalise
        records = [r for r in agent._anchor_log.read_log() if r.get("type") != "entry_signature"]
        agent._anchor_log.log_path.write_text(
            "".join(json.dumps(r, sort_keys=True) + "\n" for r in records), encoding="utf-8"
        )
        result = agent.verify_entry_signatures()
        assert result["status"] == "UNSIGNED_ENTRIES"
        assert result["expected"] == 4 and len(result["unsigned"]) == 4

    def test_one_signature_deleted_is_detected(self, tmp_path):
        agent = _signed_agent(tmp_path)
        records = agent._anchor_log.read_log()
        drop = next(i for i, r in enumerate(records) if r.get("type") == "entry_signature")
        del records[drop]
        agent._anchor_log.log_path.write_text(
            "".join(json.dumps(r, sort_keys=True) + "\n" for r in records), encoding="utf-8"
        )
        result = agent.verify_entry_signatures()
        assert result["status"] == "UNSIGNED_ENTRIES" and len(result["unsigned"]) == 1


class TestR2RewriteThenGrow:
    def test_rewritten_and_longer_chain_with_old_pin_is_tampered(self, tmp_path):
        storage = Storage(data_dir=str(tmp_path))
        append_n(storage, 3)
        pin_file = storage.integrity_dir / "sessions_last_hash.json"
        old_pin = pin_file.read_text(encoding="utf-8")

        forged = _rewrite_whole_chain(storage, "sessions", [f"forged-{i}" for i in range(4)])
        pin_file.write_text(old_pin, encoding="utf-8")  # keep the old pin

        result = verify_shard(Storage(data_dir=str(forged.data_dir)), "sessions")
        assert _status(result) == "TAMPERED"
        assert result["mismatch_type"] == "PREFIX_REWRITTEN"

    def test_legit_growth_ahead_of_pin_still_ok(self, tmp_path):
        storage = Storage(data_dir=str(tmp_path))
        append_n(storage, 3)
        pin_file = storage.integrity_dir / "sessions_last_hash.json"
        old_pin = pin_file.read_text(encoding="utf-8")
        append_n(storage, 2)
        pin_file.write_text(old_pin, encoding="utf-8")  # pin lag (crash window)

        result = verify_shard(Storage(data_dir=str(tmp_path)), "sessions")
        assert _status(result) == "OK"
        assert result["pin_status"] == "AHEAD_OF_PIN"


# --------------------------------------------------------------------------
# Review round 3 — key files disappearing, production key protection
# --------------------------------------------------------------------------


class TestR3KeyFileLoss:
    @pytest.mark.parametrize("suffix", [".pub", ".seed"])
    def test_key_file_lost_after_start_refuses_operations(self, tmp_path, suffix):
        from dsm.agent import DarylAgent, SigningError

        agent = DarylAgent("agent-a", data_dir=str(tmp_path), startup_verify=False)
        agent.start()
        i = agent.intend("refund", {"amount": 50})
        (tmp_path / "keys" / f"agent-a{suffix}").unlink()
        with pytest.raises(SigningError):
            agent.confirm(i, {"ok": True})
        with pytest.raises(SigningError):
            agent.intend("refund", {"amount": 60})
        with pytest.raises(SigningError):
            agent.checkpoint()

    @pytest.mark.parametrize("suffix", [".pub", ".seed"])
    def test_incomplete_keypair_is_not_silently_replaced(self, tmp_path, suffix):
        from dsm.agent import DarylAgent, SigningError

        DarylAgent("agent-a", data_dir=str(tmp_path), startup_verify=False)
        keys = tmp_path / "keys"
        survivor = keys / ("agent-a.seed" if suffix == ".pub" else "agent-a.pub")
        before = survivor.read_bytes()
        (keys / f"agent-a{suffix}").unlink()

        with pytest.raises(SigningError):
            DarylAgent("agent-a", data_dir=str(tmp_path), startup_verify=False)
        assert survivor.read_bytes() == before
        assert not (keys / f"agent-a{suffix}").exists()

    def test_signing_layer_refuses_partial_overwrite(self, tmp_path):
        s = AgentSigning(str(tmp_path), "agent-a", password="pw")
        s.generate_keypair()
        (tmp_path / "agent-a.pub").unlink()
        fresh = AgentSigning(str(tmp_path), "agent-a", password="pw")
        with pytest.raises(ValueError):
            fresh.generate_keypair()
        fresh.generate_keypair(force=True)  # explicit replacement still possible


class TestR3ProductionKeyProtection:
    def test_production_requires_a_separate_secret(self, tmp_path, monkeypatch):
        from dsm.agent import DarylAgent, SigningError

        monkeypatch.delenv("DSM_SIGNING_PASSWORD", raising=False)
        monkeypatch.delenv("DSM_KEY_PROTECTION", raising=False)
        with pytest.raises(SigningError):
            DarylAgent("agent-a", data_dir=str(tmp_path), startup_verify=False)
        assert not (tmp_path / "keys" / "agent-a.seed").exists()

    def test_secret_from_environment(self, tmp_path, monkeypatch):
        from dsm.agent import DarylAgent

        monkeypatch.delenv("DSM_KEY_PROTECTION", raising=False)
        monkeypatch.setenv("DSM_SIGNING_PASSWORD", "s3cret")
        agent = DarylAgent("agent-a", data_dir=str(tmp_path), startup_verify=False)
        assert agent.public_key()
        # The seed is NOT decryptable with the agent_id fallback.
        assert not AgentSigning(str(tmp_path / "keys"), "agent-a").can_sign()

    def test_dev_mode_must_be_explicit(self, tmp_path, monkeypatch):
        from dsm.agent import DarylAgent

        monkeypatch.delenv("DSM_SIGNING_PASSWORD", raising=False)
        agent = DarylAgent("agent-a", data_dir=str(tmp_path), startup_verify=False,
                           key_protection="dev")
        assert agent.public_key()

    def test_unknown_mode_rejected(self, tmp_path):
        from dsm.agent import DarylAgent

        with pytest.raises(ValueError):
            DarylAgent("agent-a", data_dir=str(tmp_path), startup_verify=False,
                       key_protection="lax")

    def test_migrate_dev_key_to_secret(self, tmp_path, monkeypatch):
        from dsm.agent import DarylAgent

        monkeypatch.delenv("DSM_SIGNING_PASSWORD", raising=False)
        dev = DarylAgent("agent-a", data_dir=str(tmp_path), startup_verify=False,
                         key_protection="dev")
        pub = dev.public_key()
        dev.change_signing_password("s3cret")
        prod = DarylAgent("agent-a", data_dir=str(tmp_path), startup_verify=False,
                          signing_password="s3cret")
        assert prod.public_key() == pub  # same identity, now secret-protected

    def test_signing_disabled_needs_no_secret(self, tmp_path, monkeypatch):
        from dsm.agent import DarylAgent

        monkeypatch.delenv("DSM_SIGNING_PASSWORD", raising=False)
        monkeypatch.delenv("DSM_KEY_PROTECTION", raising=False)
        agent = DarylAgent("agent-a", data_dir=str(tmp_path), startup_verify=False,
                           signing_dir=False)
        assert agent.public_key() is None


# --------------------------------------------------------------------------
# Review round 4 — repair-before-verify laundering, signing unavailable
# --------------------------------------------------------------------------


def _rewritten_and_grown(tmp_path):
    """3 genuine entries, then the whole chain replaced by 4 forged ones while
    the old pin (count 3) is kept: a FORWARD divergence that a blind
    reconcile would 'repair' by advancing the pin to the forged tip."""
    storage = Storage(data_dir=str(tmp_path))
    append_n(storage, 3)
    pin_file = storage.integrity_dir / "sessions_last_hash.json"
    old_pin = pin_file.read_text(encoding="utf-8")
    _rewrite_whole_chain(storage, "sessions", [f"forged-{i}" for i in range(4)])
    pin_file.write_text(old_pin, encoding="utf-8")
    return pin_file, old_pin


class TestR4VerifyBeforeRepair:
    @pytest.mark.parametrize("mode", ["strict", "full", "reconcile"])
    def test_agent_startup_does_not_launder_rewrite(self, tmp_path, mode):
        from dsm.agent import DarylAgent

        pin_file, old_pin = _rewritten_and_grown(tmp_path)
        DarylAgent._startup_cache.clear()
        if mode == "strict":
            with pytest.raises(RuntimeError):
                DarylAgent("agent-a", data_dir=str(tmp_path), startup_verify=mode)
        else:
            agent = DarylAgent("agent-a", data_dir=str(tmp_path), startup_verify=mode)
            assert agent.startup_report["status"] == "INTEGRITY_ERROR"
        assert pin_file.read_text(encoding="utf-8") == old_pin  # pin untouched
        assert _status(verify_shard(Storage(data_dir=str(tmp_path)), "sessions")) == "TAMPERED"

    def test_legit_crash_window_still_reconciled(self, tmp_path):
        from dsm.agent import DarylAgent

        storage = Storage(data_dir=str(tmp_path))
        append_n(storage, 3)
        pin_file = storage.integrity_dir / "sessions_last_hash.json"
        old_pin = pin_file.read_text(encoding="utf-8")
        append_n(storage, 1)
        pin_file.write_text(old_pin, encoding="utf-8")  # pin lag

        DarylAgent._startup_cache.clear()
        agent = DarylAgent("agent-a", data_dir=str(tmp_path), startup_verify="strict")
        assert agent.startup_report["status"] in ("OK", "RECONCILED")
        assert json.loads(pin_file.read_text(encoding="utf-8"))["entry_count"] == 4

    def test_cli_agent_check_is_read_only_and_fails(self, tmp_path, capsys):
        import argparse
        from dsm import cli

        pin_file, old_pin = _rewritten_and_grown(tmp_path)
        DarylAgent_cache_clear()
        rc = cli._cmd_agent_check(argparse.Namespace(data_dir=str(tmp_path)))
        assert rc == 1
        assert pin_file.read_text(encoding="utf-8") == old_pin

    def test_cli_startup_check_does_not_launder(self, tmp_path):
        import argparse
        from dsm import cli

        pin_file, old_pin = _rewritten_and_grown(tmp_path)
        rc = cli._cmd_startup_check(argparse.Namespace(data_dir=str(tmp_path), full=False))
        assert rc == 1
        assert pin_file.read_text(encoding="utf-8") == old_pin

    def test_deleted_pin_is_not_recreated_at_startup(self, tmp_path):
        from dsm.agent import DarylAgent

        storage = Storage(data_dir=str(tmp_path))
        append_n(storage, 5)
        truncate_last_segment(storage, "sessions", 2)
        pin_file = storage.integrity_dir / "sessions_last_hash.json"
        pin_file.unlink()

        DarylAgent._startup_cache.clear()
        agent = DarylAgent("agent-a", data_dir=str(tmp_path), startup_verify="reconcile")
        assert agent.startup_report["status"] == "INTEGRITY_ERROR"
        assert not pin_file.exists()


def DarylAgent_cache_clear():
    from dsm.agent import DarylAgent

    DarylAgent._startup_cache.clear()


class TestR4SigningUnavailable:
    @pytest.mark.parametrize("mode", ["production", "dev"])
    def test_no_nacl_refuses_to_start(self, tmp_path, monkeypatch, mode):
        import dsm.signing
        from dsm.agent import DarylAgent, SigningError

        monkeypatch.setattr(dsm.signing, "NACL_AVAILABLE", False)
        with pytest.raises(SigningError):
            DarylAgent("agent-a", data_dir=str(tmp_path), startup_verify=False,
                       key_protection=mode)

    def test_no_nacl_with_existing_key_refuses_to_start(self, tmp_path, monkeypatch):
        import dsm.signing
        from dsm.agent import DarylAgent, SigningError

        DarylAgent("agent-a", data_dir=str(tmp_path), startup_verify=False)
        monkeypatch.setattr(dsm.signing, "NACL_AVAILABLE", False)
        with pytest.raises(SigningError):
            DarylAgent("agent-a", data_dir=str(tmp_path), startup_verify=False)

    def test_explicit_opt_out_still_works_without_nacl(self, tmp_path, monkeypatch):
        import dsm.signing
        from dsm.agent import DarylAgent

        monkeypatch.setattr(dsm.signing, "NACL_AVAILABLE", False)
        agent = DarylAgent("agent-a", data_dir=str(tmp_path), startup_verify=False,
                           signing_dir=False)
        agent.start()
        assert agent.intend("refund", {"amount": 50})


# --------------------------------------------------------------------------
# Review round 5 — the startup cache must not bypass strict/full checks
# --------------------------------------------------------------------------


class TestR5StartupCache:
    def test_cached_error_still_refuses_strict(self, tmp_path):
        """reconcile-mode agent caches INTEGRITY_ERROR; a strict agent in the
        same process must still refuse to start."""
        from dsm.agent import DarylAgent

        _rewritten_and_grown(tmp_path)
        DarylAgent._reset_startup_cache()
        first = DarylAgent("agent-a", data_dir=str(tmp_path), startup_verify="reconcile")
        assert first.startup_report["status"] == "INTEGRITY_ERROR"
        with pytest.raises(RuntimeError):
            DarylAgent("agent-a", data_dir=str(tmp_path), startup_verify="strict")

    @pytest.mark.parametrize("first_mode", ["reconcile", "strict"])
    def test_cached_ok_not_reused_after_tampering(self, tmp_path, first_mode):
        """A cached OK must not stand in for a fresh strict verification."""
        from dsm.agent import DarylAgent

        storage = Storage(data_dir=str(tmp_path))
        append_n(storage, 3)
        DarylAgent._reset_startup_cache()
        first = DarylAgent("agent-a", data_dir=str(tmp_path), startup_verify=first_mode)
        assert first.startup_report["status"] in ("OK", "RECONCILED")

        _rewritten_and_grown_existing(tmp_path)
        assert _status(verify_shard(Storage(data_dir=str(tmp_path)), "sessions")) == "TAMPERED"
        with pytest.raises(RuntimeError):
            DarylAgent("agent-a", data_dir=str(tmp_path), startup_verify="strict")
        second = DarylAgent("agent-a", data_dir=str(tmp_path), startup_verify="full")
        assert second.startup_report["status"] == "INTEGRITY_ERROR"

    def test_cached_error_warns_in_reconcile_mode(self, tmp_path, caplog):
        from dsm.agent import DarylAgent

        _rewritten_and_grown(tmp_path)
        DarylAgent._reset_startup_cache()
        DarylAgent("agent-a", data_dir=str(tmp_path), startup_verify="reconcile")
        caplog.clear()
        again = DarylAgent("agent-a", data_dir=str(tmp_path), startup_verify="reconcile")
        assert again.startup_report["status"] == "INTEGRITY_ERROR"
        assert "integrity" in caplog.text.lower()


def _rewritten_and_grown_existing(tmp_path):
    """Same forgery as _rewritten_and_grown, on an existing 3-entry shard."""
    storage = Storage(data_dir=str(tmp_path))
    pin_file = storage.integrity_dir / "sessions_last_hash.json"
    old_pin = pin_file.read_text(encoding="utf-8")
    _rewrite_whole_chain(storage, "sessions", [f"forged-{i}" for i in range(4)])
    pin_file.write_text(old_pin, encoding="utf-8")
