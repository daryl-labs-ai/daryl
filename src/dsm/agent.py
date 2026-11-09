"""
DarylAgent SDK — plug-and-play facade for DSM.

Single entry point: Storage, SessionGraph, Witness, Audit, Coverage.
Agent developers need zero DSM knowledge; 5 lines to integrate.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional, Set, Tuple, Union
from uuid import uuid4

from .anchor import AnchorLog, pre_commit, post_commit, capture_environment, verify_all_commitments
from .audit import Policy, audit_all, audit_shard
from .policy_adapter import (
    AuditReport,
    generate_audit_report,
    list_adapters,
    load_and_audit,
    verify_report,
)
from .coverage import check_coverage
from .core.models import Entry
from .core.storage import Storage
from .receipts import make_receipt
from .session.session_graph import SessionGraph
from .session.session_limits_manager import SessionLimitsManager
from .rr.index import RRIndexBuilder
from .rr.navigator import RRNavigator
from .rr.query import RRQueryEngine
from .rr.helpers import get_populated_rr_builder, build_session_summary
from .exchange import (
    TaskReceipt,
    issue_receipt as issue_receipt_fn,
    list_received_receipts,
    store_external_receipt,
    verify_receipt as verify_receipt_fn,
)
from .seal import SealRegistry, list_sealed_shards, seal_shard as seal_shard_fn, verify_seal as verify_seal_fn
from .verify import guarded_startup_check, verify_all, verify_shard
from .witness import ShardWitness
from .signing import AgentSigning, import_public_key, load_public_key
from .checkpoint import make_checkpoint, ed25519_verify
from .artifacts import ArtifactStore
from .identity import IdentityGuard, IdentityManager, IdentityState, replay_identity
from .identity.identity_registry import AgentIdentity, IdentityRegistry
from .sovereignty import SovereigntyPolicy, PolicySnapshot, EnforcementResult
from .orchestrator import NeutralOrchestrator, RuleSet, AdmissionResult
from .collective import (
    CollectiveEntry,
    CollectiveShard,
    CollectiveMemoryDistiller,
    RollingDigester,
    ShardSyncEngine,
)
from .lifecycle import ShardLifecycle, ShardState, LifecycleResult, VerifyResult
from .lanes import LaneGroup, LaneTip, MergeEntry, LaneWriteResult
from .shard_families import ShardFamily, classify_shard, list_shards_by_family

logger = logging.getLogger("dsm.agent")

# Metadata event types that DarylAgent signs; verify_entry_signatures() expects
# a valid signature for every entry of these types.
SIGNED_EVENT_TYPES = ("action_intent", "action_result")
SIGNING_PASSWORD_ENV = "DSM_SIGNING_PASSWORD"
KEY_PROTECTION_ENV = "DSM_KEY_PROTECTION"
KEY_PROTECTION_MODES = ("production", "dev")


class SigningError(RuntimeError):
    """Signing is enabled for this agent but could not be performed.

    Raised instead of silently writing unsigned intents/results (fail closed).
    """


class DarylAgent:
    """
    Facade that wires Storage, SessionGraph, optional Witness/Audit.
    Use agent_id as session source; all methods map to existing DSM modules.
    """

    _startup_cache: dict = {}  # {abs_data_dir: report_dict} — S-5 deduplication

    @classmethod
    def _reset_startup_cache(cls) -> None:
        """Clear the startup check cache. Call in test fixtures to ensure isolation."""
        cls._startup_cache = {}

    def __init__(
        self,
        agent_id: str,
        data_dir: str = "data",
        shard: str = "sessions",
        witness_dir: Optional[str] = None,
        witness_key: str = "",
        signing_dir: Optional[Union[str, bool]] = None,
        signing_password: Optional[str] = None,
        artifact_dir: Optional[Union[str, bool]] = None,
        startup_verify: Union[bool, str] = "reconcile",
        auto_keygen: bool = True,
        key_protection: Optional[str] = None,
    ):
        """
        startup_verify: Integrity check at boot. Default "reconcile" fixes crash
            inconsistencies only (fast, O(1) per shard). Use "full" to also detect
            tampering (slower, O(n) per shard). Use "strict" for production: same
            as "full" but raises RuntimeError on integrity errors. Note: "reconcile"
            does NOT detect tampering. Use "full", "strict", or call agent.verify() for that.
        auto_keygen: P1 — when signing is enabled (signing_dir is not False) and no
            keypair exists yet, generate one so intents, results, receipts and
            checkpoints are signed by default. Pass False to keep the old opt-in
            behaviour. Publish public_key() out of band so verifiers can trust it.
        signing_password: protects the private key on disk. Defaults to the
            DSM_SIGNING_PASSWORD environment variable (keep it out of the data
            directory).
        key_protection: "production" (default) requires that secret whenever
            signing is enabled and raises SigningError without it. "dev" is the
            explicit compatibility mode: without a secret the seed is encrypted
            with the agent_id, so anyone who copies the keys directory can sign
            as this agent. Defaults to DSM_KEY_PROTECTION, else "production".
            Migrate a dev key with change_signing_password().

        Signing fails closed: if a keypair exists but cannot be unlocked (wrong
        password, corrupt seed), or only half of it is on disk, the constructor
        raises SigningError (it never regenerates over a surviving half). Once
        the agent has started with a key, signing stays mandatory for its whole
        life: if a key file disappears later, intend()/confirm()/
        issue_receipt()/checkpoint() raise SigningError instead of going on
        unsigned.
        """
        self.agent_id = agent_id
        self.data_dir = Path(data_dir)
        self.shard = shard
        self._storage = Storage(data_dir=str(self.data_dir))

        self._startup_report = None
        if startup_verify:
            abs_dir = str(self.data_dir.resolve())
            full = startup_verify in ("full", "strict")
            # S-5 cache: only the cheap "reconcile" mode may reuse a previous
            # report from this process. "full"/"strict" promise a verification
            # of the data as it is NOW, so they always re-run (a cached OK may
            # predate tampering), and their fresh result refreshes the cache.
            cached = None if full else DarylAgent._startup_cache.get(abs_dir)
            if cached is not None:
                self._startup_report = cached
            else:
                # Verify BEFORE any pin repair (never launder a rewrite).
                self._startup_report = guarded_startup_check(self._storage, full_verify=full)
                DarylAgent._startup_cache[abs_dir] = self._startup_report
            # Decision applied to every report, cached or fresh.
            if self._startup_report["status"] == "INTEGRITY_ERROR":
                if startup_verify == "strict":
                    raise RuntimeError(
                        f"DarylAgent({agent_id}): integrity check failed: "
                        f"{self._startup_report}"
                    )
                logger.warning(
                    "DarylAgent(%s): startup integrity check found errors%s: %s",
                    agent_id,
                    " (cached report)" if cached is not None else "",
                    self._startup_report,
                )

        limits = SessionLimitsManager.agent_defaults(str(self.data_dir))
        self._graph = SessionGraph(storage=self._storage, limits_manager=limits)
        self._witness = (
            ShardWitness(witness_dir, witness_key) if witness_dir else None
        )
        self._anchor_log = AnchorLog(str(self.data_dir / "anchors"))
        self._index_dir = str(self.data_dir / "index")

        # V4-C: in-process cache for RRIndexBuilder.
        # Invalidated by mtime check on .idx files (covers cross-process
        # writes that rebuild indexes). Transparent to callers.
        self._rr_builder_cache = None
        self._rr_idx_mtime: Optional[Tuple[int, ...]] = None

        self._pending_commitments = {}  # intent_id -> commitment_hash
        self._signing = None
        # Latched at startup: once True, signing is required for the agent's
        # lifetime, whatever happens to the key files afterwards.
        self._signing_enforced = False
        mode = key_protection or os.environ.get(KEY_PROTECTION_ENV) or "production"
        if mode not in KEY_PROTECTION_MODES:
            raise ValueError(f"key_protection must be one of {KEY_PROTECTION_MODES}, got {mode!r}")
        self._key_protection = mode
        if signing_dir is not False:
            path = signing_dir if isinstance(signing_dir, str) else str(self.data_dir / "keys")
            if signing_password is None:
                signing_password = os.environ.get(SIGNING_PASSWORD_ENV) or None
            if not signing_password and mode == "production":
                raise SigningError(
                    f"DarylAgent({agent_id}): no signing secret. Set signing_password "
                    f"or {SIGNING_PASSWORD_ENV} (kept outside the data directory), pass "
                    f"key_protection='dev' / {KEY_PROTECTION_ENV}=dev for development, "
                    "or signing_dir=False to disable signing"
                )
            self._signing = AgentSigning(path, self.agent_id, password=signing_password)
            if self._signing.has_partial_keypair():
                raise SigningError(
                    f"DarylAgent({agent_id}): incomplete keypair in {path} (seed or public "
                    "key missing); refusing to regenerate over it. Restore the missing "
                    "file, or replace the identity explicitly with "
                    "AgentSigning(...).generate_keypair(force=True)"
                )
            if auto_keygen and not self._signing.has_keypair():
                try:
                    self._signing.generate_keypair()
                except RuntimeError as e:  # PyNaCl missing
                    raise SigningError(
                        f"DarylAgent({agent_id}): signing is required but unavailable "
                        f"({e}); install PyNaCl, or pass signing_dir=False to run "
                        "without signatures"
                    ) from e
            if self._signing.has_keypair():
                if not self._signing.can_sign():
                    raise SigningError(
                        f"DarylAgent({agent_id}): signing key exists but cannot be "
                        "unlocked (wrong signing_password or corrupt seed); refusing "
                        "to run unsigned"
                    )
                self._signing_enforced = True
                if self._signing.uses_default_password:
                    logger.warning(
                        "DarylAgent(%s): key_protection=dev — signing key protected only "
                        "by agent_id; a copy of the data directory can sign as this agent",
                        agent_id,
                    )
        self._artifact_store = None
        if artifact_dir is not False:
            path = artifact_dir if isinstance(artifact_dir, str) else str(self.data_dir / "artifacts")
            self._artifact_store = ArtifactStore(path)

        _sid = self._graph.get_session_id() or "identity"
        self._identity_manager = IdentityManager(
            self._storage, self.agent_id, session_id=_sid
        )
        self._identity_guard = IdentityGuard(self._storage, self.agent_id)

        # --- A→E Pillars ---
        # A — Identity Registry
        self._registry = IdentityRegistry(self._storage)
        # B — Sovereignty Policy
        self._sovereignty = SovereigntyPolicy(self._storage)
        # C — Neutral Orchestrator
        self._orchestrator = NeutralOrchestrator(
            self._storage,
            rules=RuleSet.default(),
            identity=self._registry,
            policy=self._sovereignty,
        )
        # D — Collective (default collective shard)
        self._collective = CollectiveShard(self._storage, "collective_main")
        self._sync_engine = ShardSyncEngine(
            self._storage,
            collective=self._collective,
            identity=self._registry,
            policy=self._sovereignty,
            orchestrator=self._orchestrator,
        )
        self._distiller = CollectiveMemoryDistiller()
        self._digester = RollingDigester(self._collective, self._storage)
        # E — Lifecycle
        self._lifecycle = ShardLifecycle(self._storage, distiller=self._distiller)
        # Parallel Lanes
        self._lanes = LaneGroup(
            self._storage,
            identity=self._registry,
            policy=self._sovereignty,
            orchestrator=self._orchestrator,
        )

    # ------------------------------------------------------------------
    # Core properties (existing)
    # ------------------------------------------------------------------

    @property
    def storage(self):
        return self._storage

    @property
    def graph(self):
        return self._graph

    # ------------------------------------------------------------------
    # A→E module access (direct bypass of facade for advanced users)
    #
    # Usage:
    #   agent.registry.register(...)       # direct A
    #   agent.sovereignty.allows(...)      # direct B
    #   agent.orchestrator.admit(...)      # direct C
    #   agent.collective.recent(...)       # direct D read
    #   agent.sync_engine.push(...)        # direct D write
    #   agent.digester.read_with_digests(...)  # direct D context
    #   agent.lifecycle.drain(...)         # direct E
    # ------------------------------------------------------------------

    @property
    def registry(self) -> IdentityRegistry:
        """A — Identity Registry (direct access)."""
        return self._registry

    @property
    def sovereignty(self) -> SovereigntyPolicy:
        """B — Sovereignty Policy (direct access)."""
        return self._sovereignty

    @property
    def orchestrator(self) -> NeutralOrchestrator:
        """C — Neutral Orchestrator (direct access)."""
        return self._orchestrator

    @property
    def collective(self) -> CollectiveShard:
        """D — Collective Shard read-side (direct access)."""
        return self._collective

    @property
    def sync_engine(self) -> ShardSyncEngine:
        """D — Sync Engine write-side (direct access)."""
        return self._sync_engine

    @property
    def digester(self) -> RollingDigester:
        """D — Rolling Digester for context loading (direct access)."""
        return self._digester

    @property
    def lanes(self) -> LaneGroup:
        """Parallel shard lanes (direct access)."""
        return self._lanes

    @property
    def lifecycle(self) -> ShardLifecycle:
        """E — Shard Lifecycle (direct access)."""
        return self._lifecycle

    @property
    def startup_report(self) -> Optional[dict]:
        """
        Return the startup integrity check report, or None if check was skipped.

        Note: 'reconcile' mode only detects crash inconsistencies, not tampering.
        Use startup_verify='full' or call self.verify() for tamper detection.
        """
        return self._startup_report

    def start(self) -> Optional[Any]:
        try:
            return self._graph.start_session(source=self.agent_id)
        except OSError as e:
            logger.error("start failed: %s", e)
            return None

    def end(self, sync: bool = True) -> Optional[Any]:
        """End the current session.

        Args:
            sync: If True (default), triggers auto-sync and lifecycle checks
                  via the A→E hooks on session end.
        """
        try:
            return self._graph.end_session(
                sync_engine=self._sync_engine if sync else None,
                lifecycle=self._lifecycle if sync else None,
            )
        except OSError as e:
            logger.error("end failed: %s", e)
            return None

    def snapshot(self, data: dict) -> Optional[Any]:
        try:
            return self._graph.record_snapshot(data)
        except OSError as e:
            logger.error("snapshot failed: %s", e)
            return None

    def _signing_required(self) -> bool:
        # Latched flag, NOT has_keypair(): a key file vanishing must not turn
        # the signing obligation off.
        return self._signing_enforced

    def _require_signer(self) -> None:
        """Preflight: refuse to write work we will not be able to sign."""
        if self._signing_required() and not self._signing.can_sign():
            raise SigningError(f"DarylAgent({self.agent_id}): signing key unavailable")

    def _record_entry_signature(self, entry: Any) -> None:
        """Sign an entry hash and record it in the anchor log.

        Fails closed: when signing is enabled, any failure raises SigningError
        (the entry stays unsigned on disk and verify_entry_signatures() will
        report it).
        """
        if not (self._signing_required() and entry is not None and entry.hash):
            return
        try:
            signature = self._signing.sign_entry(entry.hash)
            self._anchor_log._append_record({
                "type": "entry_signature",
                "entry_id": entry.id,
                "entry_hash": entry.hash,
                "shard_id": getattr(entry, "shard", None),
                "signature": signature,
                "public_key": self._signing.get_public_key(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as e:
            raise SigningError(
                f"DarylAgent({self.agent_id}): failed to sign entry {entry.id}: {e}"
            ) from e

    def intend(self, action_name: str, params: Optional[dict] = None) -> Optional[str]:
        self._require_signer()
        try:
            entry = self._graph.execute_action(action_name, params or {})
            if entry is None:
                return None
            intent_id = entry.metadata.get("intent_id") or entry.id
            # P4: pre-commit anchoring
            try:
                anchor = pre_commit(self._anchor_log, intent_id, action_name, params or {})
                self._pending_commitments[intent_id] = anchor["commitment_hash"]
            except OSError as e:
                logger.debug("anchor pre-commit skipped: %s", e)
            # P9: sign entry if signing enabled
            self._record_entry_signature(entry)
            return intent_id
        except OSError as e:
            logger.error("intend failed: %s", e)
            return None

    def confirm(
        self,
        intent_id: str,
        result: Any = None,
        success: bool = True,
        raw_input: Any = None,
    ) -> Optional[Any]:
        self._require_signer()
        receipt = {}
        if raw_input is not None:
            receipt = make_receipt(raw_input)
        result_data = result if isinstance(result, dict) else {"value": result}
        artifact_hash = None
        if self._artifact_store is not None and raw_input is not None:
            try:
                art = self._artifact_store.store(
                    raw_input, source=f"confirm:{intent_id}", artifact_type="raw_input"
                )
                artifact_hash = art["artifact_hash"]
            except Exception as e:
                logger.debug("artifact store skipped: %s", e)
        # P4: post-commit anchoring
        try:
            commitment_hash = self._pending_commitments.pop(intent_id, None)
            if commitment_hash is None:
                # Intent opened by another process/instance: bind to the logged
                # pre_commit so the pair stays verifiable.
                pre = self._anchor_log.find_by_intent(intent_id).get("pre_commit")
                commitment_hash = pre.get("commitment_hash") if pre else None
            post_commit(
                self._anchor_log, intent_id, result_data,
                raw_input=raw_input, commitment_hash=commitment_hash,
            )
        except OSError as e:
            logger.debug("anchor post-commit skipped: %s", e)
        try:
            result_entry = self._graph.confirm_action(
                intent_id,
                result_data=result_data,
                success=success,
                input_hash=receipt.get("input_hash"),
                input_preview=receipt.get("input_preview"),
            )
            self._record_entry_signature(result_entry)
            if result_entry is not None and artifact_hash is not None and self._artifact_store is not None:
                try:
                    self._artifact_store.link_to_entry(artifact_hash, result_entry.id)
                except Exception as e:
                    logger.debug("confirm signing skipped: %s", e)
            return result_entry
        except OSError as e:
            logger.error("confirm failed: %s", e)
            return None

    def orphaned_intents(self) -> List[Any]:
        try:
            return self._graph.find_orphaned_intents(self._storage)
        except OSError as e:
            logger.error("orphaned_intents failed: %s", e)
            return []

    def verify(
        self,
        shard_id: Optional[str] = None,
        checkpoint: Optional[dict] = None,
        trusted_public_key: Optional[str] = None,
    ) -> Any:
        """Verify one shard (or all). Pass a client-held `checkpoint` (from
        checkpoint()) and the agent's `trusted_public_key` to detect truncation
        or a full rewrite even if the on-disk pin was removed or recomputed."""
        if shard_id:
            return verify_shard(
                self._storage, shard_id,
                checkpoint=checkpoint, trusted_public_key=trusted_public_key,
            )
        if checkpoint is not None or trusted_public_key is not None:
            raise ValueError("checkpoint verification requires a shard_id")
        return verify_all(self._storage)

    def checkpoint(self, shard_id: Optional[str] = None) -> List[dict]:
        """Export checkpoints (signed when a keypair exists) of one or all shards.

        Hand these to the client/auditor and keep them OUTSIDE this agent's data
        directory: they are the completeness proof the local pin cannot be.
        """
        self._require_signer()
        signing = self._signing if self._signing_required() else None
        if shard_id:
            shard_ids = [shard_id]
        else:
            shard_ids = [s.shard_id for s in self._storage.list_shards()]
        return [make_checkpoint(self._storage, sid, signing=signing) for sid in shard_ids]

    def verify_entry_signatures(
        self,
        trusted_public_key: Optional[str] = None,
        shard_id: str = "sessions",
        since: Optional[str] = None,
    ) -> dict:
        """Check that every entry this agent signs is signed, and validly.

        Coverage: every entry of `shard_id` whose event_type is in
        SIGNED_EVENT_TYPES (intents and results) must have an entry_signature
        record in the anchor log that verifies under `trusted_public_key`
        (default: this agent's own public key). Entries timestamped before
        `since` (ISO 8601) are exempt — use it for history written before
        signing was enabled.

        Also reported: signatures that do not verify, and validly signed
        entries that no longer exist in storage.

        Status: ALL_VALID | INVALID_SIGNATURES | UNSIGNED_ENTRIES |
                MISSING_ENTRIES | NOTHING_TO_VERIFY | NO_KEY
        Precedence: INVALID_SIGNATURES > UNSIGNED_ENTRIES > MISSING_ENTRIES.
        """
        key = trusted_public_key or self.public_key()
        empty = {"checked": 0, "expected": 0, "invalid": [], "unsigned": [], "missing": []}
        if not key:
            return {"status": "NO_KEY", **empty}

        since_dt = None
        if since is not None:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))

        records = [r for r in self._anchor_log.read_log() if r.get("type") == "entry_signature"]
        valid_hashes: Set[str] = set()
        invalid: List[str] = []
        for r in records:
            entry_hash = r.get("entry_hash") or ""
            if ed25519_verify(key, r.get("signature") or "", entry_hash):
                valid_hashes.add(entry_hash)
            else:
                invalid.append(r.get("entry_id"))

        entries = self._storage.read(shard_id, limit=10**6)
        stored_hashes = {e.hash for e in entries if e.hash}
        expected = []
        for e in entries:
            if (e.metadata or {}).get("event_type") not in SIGNED_EVENT_TYPES:
                continue
            if since_dt is not None:
                ts = e.timestamp
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts < since_dt:
                    continue
            expected.append(e)
        unsigned = [e.id for e in expected if e.hash not in valid_hashes]
        missing = [
            r.get("entry_id") for r in records
            if r.get("shard_id") in (None, shard_id)
            and (r.get("entry_hash") or "") in valid_hashes
            and r.get("entry_hash") not in stored_hashes
        ]

        if invalid:
            status = "INVALID_SIGNATURES"
        elif unsigned:
            status = "UNSIGNED_ENTRIES"
        elif missing:
            status = "MISSING_ENTRIES"
        elif not expected:
            status = "NOTHING_TO_VERIFY"
        else:
            status = "ALL_VALID"
        return {
            "status": status,
            "checked": len(records),
            "expected": len(expected),
            "invalid": invalid,
            "unsigned": unsigned,
            "missing": missing,
        }
    def check_coverage(
        self,
        indexed_ids: Optional[Set[str]] = None,
        indexed_hashes: Optional[Set[str]] = None,
    ) -> dict:
        ids = set(indexed_ids) if indexed_ids else None
        hashes = set(indexed_hashes) if indexed_hashes else None
        return check_coverage(self._storage, indexed_ids=ids, indexed_hashes=hashes)

    def witness_capture(self) -> List[dict]:
        if self._witness is None:
            raise ValueError("witness_dir was not set; cannot capture witness")
        return self._witness.capture_all(self._storage)

    def witness_verify(self, shard_id: Optional[str] = None) -> List[dict]:
        if self._witness is None:
            raise ValueError("witness_dir was not set; cannot verify witness")
        if shard_id:
            return [self._witness.verify_shard_against_witness(self._storage, shard_id)]
        log = self._witness.read_log()
        shard_ids = list({r["shard_id"] for r in log})
        return [
            self._witness.verify_shard_against_witness(self._storage, sid)
            for sid in shard_ids
        ]

    def audit(
        self, policy_path: str, shard_id: Optional[str] = None
    ) -> List[dict]:
        policy = Policy.from_file(policy_path)
        if shard_id:
            return [audit_shard(self._storage, shard_id, policy)]
        return audit_all(self._storage, policy)

    def seal_shard(self, shard_id: str, archive_path: Optional[str] = None) -> dict:
        registry = SealRegistry(str(self.data_dir / "seals"))
        record = seal_shard_fn(self._storage, shard_id, registry, archive_path)
        return record.to_dict()

    def sealed_shards(self) -> List[dict]:
        registry = SealRegistry(str(self.data_dir / "seals"))
        return list_sealed_shards(registry)

    def verify_seal(self, shard_id: str) -> dict:
        registry = SealRegistry(str(self.data_dir / "seals"))
        return verify_seal_fn(registry, shard_id)

    def _add_entry(self, action: str, data: dict) -> Entry:
        """Append an entry to the agent's shard (e.g. for dispatch). Returns the written entry with hash."""
        session_id = getattr(self._graph, "current_session_id", None) or "none"
        entry = Entry(
            id=str(uuid4()),
            timestamp=datetime.now(timezone.utc),
            session_id=session_id,
            source=self.agent_id,
            content=json.dumps(data, ensure_ascii=False),
            shard=self.shard,
            hash="",
            prev_hash=None,
            metadata={"event_type": "tool_call", "action_name": action},
            version="v2.0",
        )
        return self._storage.append(entry)

    def dispatch_task(self, target_agent_id: str, task_params: dict) -> dict:
        """Dispatch work to another agent. Returns dispatch record.

        Creates a DSM entry recording the dispatch, then computes
        dispatch_hash from the entry hash + task_params.
        """
        from .causal import create_dispatch_hash, DispatchRecord

        entry = self._add_entry(
            action="dispatch",
            data={"target": target_agent_id, "task_params": task_params},
        )
        timestamp = datetime.now(timezone.utc).isoformat()
        dispatch_hash = create_dispatch_hash(entry.hash or "", task_params, timestamp)
        return DispatchRecord(
            dispatch_hash=dispatch_hash,
            dispatcher_agent_id=self.agent_id,
            dispatcher_entry_hash=entry.hash or "",
            target_agent_id=target_agent_id,
            task_params=task_params,
            timestamp=timestamp,
        ).to_dict()

    def issue_receipt(
        self,
        entry_id: str,
        shard_id: str,
        task_description: str = "",
        dispatch_hash: Optional[str] = None,
        routing_hash: Optional[str] = None,
    ) -> dict:
        """Issue a receipt for completed work, optionally with causal binding."""
        self._require_signer()
        signing = self._signing if self._signing_required() else None
        receipt = issue_receipt_fn(
            self._storage,
            self.agent_id,
            entry_id,
            shard_id,
            task_description,
            dispatch_hash=dispatch_hash,
            routing_hash=routing_hash,
            signing=signing,
        )
        return receipt.to_dict()

    def _trusted_key_for(self, agent_id: str) -> Optional[str]:
        """Public key this agent trusts for `agent_id` (imported via import_agent_key)."""
        return load_public_key(str(self.data_dir / "keys"), agent_id)

    def receive_receipt(self, receipt_json: str, trusted_public_key: Optional[str] = None) -> dict:
        """Verify and store a receipt from another agent.

        Stored only if INTACT, i.e. signed by the issuer key this agent trusts
        (passed explicitly, or previously imported with import_agent_key()).
        """
        receipt = TaskReceipt.from_json(receipt_json)
        key = trusted_public_key or self._trusted_key_for(receipt.issuer_agent_id)
        vr = verify_receipt_fn(receipt, trusted_public_key=key)
        stored = False
        if vr["status"] == "INTACT":
            store_external_receipt(self._storage, receipt, self.agent_id, shard_id="receipts")
            stored = True
        status = vr["status"]
        return {
            "stored": stored,
            "receipt_id": receipt.receipt_id,
            "integrity": getattr(status, "value", status),
        }

    def verify_external_receipt(self, receipt_json: str, trusted_public_key: Optional[str] = None) -> dict:
        receipt = TaskReceipt.from_json(receipt_json)
        key = trusted_public_key or self._trusted_key_for(receipt.issuer_agent_id)
        return verify_receipt_fn(receipt, trusted_public_key=key)

    def list_receipts(self) -> List[dict]:
        return [r.to_dict() for r in list_received_receipts(self._storage, shard_id="receipts")]

    def attest_compute(
        self,
        raw_input: Any,
        raw_output: Any,
        model_id: str,
        dispatch_hash: Optional[str] = None,
    ) -> dict:
        """Create a signed compute attestation for input→output binding.

        Returns attestation dict with hashes and optional signature.
        """
        from .attestation import create_attestation, sign_attestation

        att = create_attestation(
            agent_id=self.agent_id,
            raw_input=raw_input,
            raw_output=raw_output,
            model_id=model_id,
            dispatch_hash=dispatch_hash,
        )
        if self._signing is not None and self._signing.has_keypair():
            try:
                att = sign_attestation(att, self._signing)
            except Exception as e:
                logger.debug("attestation signing skipped: %s", e)
        return att.to_dict()

    def generate_keys(self, force: bool = False) -> dict:
        """Generate ed25519 keypair for this agent. Idempotent. From then on
        signing is mandatory for this agent instance."""
        if self._signing is None:
            raise ValueError("Signing is disabled")
        result = self._signing.generate_keypair(force=force)
        self._signing_enforced = True
        return result

    def change_signing_password(self, new_password: str) -> None:
        """Re-encrypt this agent's seed under a new secret (e.g. to migrate a
        key created with key_protection='dev' to production)."""
        if self._signing is None:
            raise ValueError("Signing is disabled")
        self._signing.change_password(new_password)

    def public_key(self) -> Optional[str]:
        """Return this agent's public key (hex), or None."""
        if self._signing is None:
            return None
        return self._signing.get_public_key()

    def import_agent_key(self, agent_id: str, public_key_hex: str) -> str:
        """Import another agent's public key for receipt verification."""
        if self._signing is None:
            raise ValueError("Signing is disabled")
        return import_public_key(str(self.data_dir / "keys"), agent_id, public_key_hex)

    def rotate_key(self, reason: str = "routine rotation") -> dict:
        """Rotate this agent's Ed25519 keypair. Old key is retired, new key generated."""
        if self._signing is None:
            raise ValueError("Signing is disabled")
        return self._signing.rotate_key(reason=reason)

    def revoke_key(self, public_key: str, reason: str = "compromised") -> bool:
        """Revoke a public key (own or imported). Returns True if found."""
        if self._signing is None:
            raise ValueError("Signing is disabled")
        return self._signing.revoke_key(public_key, reason=reason)

    def key_history(self) -> list:
        """Return the key rotation history for this agent."""
        if self._signing is None:
            return []
        return self._signing.key_history

    def identity_genesis(
        self,
        purpose: str,
        capabilities: Optional[List[str]] = None,
        constraints: Optional[List[str]] = None,
        created_by: str = "",
        **extra: Any,
    ) -> Entry:
        """Create the genesis identity event for this agent."""
        return self._identity_manager.create_genesis(
            purpose=purpose,
            capabilities=capabilities or [],
            constraints=constraints or [],
            created_by=created_by,
            **extra,
        )

    def identity_event(
        self, event_type: str, payload: dict, reason: Optional[str] = None
    ) -> Entry:
        """Append an identity evolution event."""
        return self._identity_manager.append_event(
            event_type, payload, reason=reason
        )

    def identity_replay(self, up_to: Optional[datetime] = None) -> IdentityState:
        """Reconstruct this agent's identity from replay."""
        return replay_identity(self.storage, self.agent_id, up_to=up_to)

    def identity_check(self) -> dict:
        """Run identity guard heuristic check."""
        return self._identity_guard.check_continuity()

    def store_artifact(
        self,
        raw_data: Union[str, bytes, dict],
        source: str,
        artifact_type: str = "response",
        metadata: Optional[dict] = None,
    ) -> dict:
        """Store raw I/O data in content-addressable artifact store."""
        if self._artifact_store is None:
            raise ValueError("Artifact store is disabled")
        return self._artifact_store.store(raw_data, source, artifact_type, metadata)

    def retrieve_artifact(self, artifact_hash: str) -> Optional[bytes]:
        """Retrieve raw bytes for an artifact by hash."""
        if self._artifact_store is None:
            raise ValueError("Artifact store is disabled")
        return self._artifact_store.retrieve(artifact_hash)

    def verify_artifact(self, artifact_hash: str) -> dict:
        """Verify artifact integrity."""
        if self._artifact_store is None:
            raise ValueError("Artifact store is disabled")
        return self._artifact_store.verify_artifact(artifact_hash)

    def index_sessions(self) -> dict:
        """Build or rebuild session index for this agent's shard, via RR (ADR-0001)."""
        builder = RRIndexBuilder(storage=self._storage, index_dir=str(self._index_dir))
        return builder.build()

    def _compute_idx_mtime(self) -> Optional[Tuple[int, ...]]:
        """Compute a cache key from .idx file mtimes.

        Returns a tuple of st_mtime_ns for all 5 RR index files,
        or None if any file is missing (forces a rebuild path).
        Used to detect when indexes have been modified by any process
        (intra or inter) so the cached builder can be invalidated.
        """
        from pathlib import Path
        idx_files = (
            "sessions.idx",
            "agents.idx",
            "timeline.idx",
            "shards.idx",
            "actions.idx",
        )
        mtimes = []
        index_path = Path(self._index_dir)
        for name in idx_files:
            f = index_path / name
            if not f.exists():
                return None
            mtimes.append(f.stat().st_mtime_ns)
        return tuple(mtimes)

    def _get_cached_rr_builder(self):
        """Return a cached RRIndexBuilder, invalidating on mtime change.

        First call (or after invalidation) loads/builds via
        get_populated_rr_builder. Subsequent calls return the cached
        instance unless any .idx file mtime has changed.

        Per V4-C: gain is `(N-1) × load_cost` for an agent session
        making N index queries. Invalidation is a 5-stat() syscall
        (sub-ms) at each access.
        """
        current_mtime = self._compute_idx_mtime()
        if (
            self._rr_builder_cache is None
            or current_mtime is None
            or self._rr_idx_mtime != current_mtime
        ):
            self._rr_builder_cache = get_populated_rr_builder(
                self._storage, self._index_dir
            )
            # Re-read mtime AFTER build to capture any rebuild-induced
            # mtime change (build() writes .idx files atomically).
            self._rr_idx_mtime = self._compute_idx_mtime()
        return self._rr_builder_cache

    def find_session(self, session_id: str) -> Optional[dict]:
        """Look up a session summary by session_id, via RR index (ADR-0001 Phase 7b).

        Returns a session summary dict (session_id, source, start_time, end_time,
        entry_count, entry_ids, actions), or None if the session has no entries
        in the current index.

        Complexity: O(1) dict lookup once the index is loaded. First call may
        trigger an index build (O(N) in the number of entries) if no persisted
        index is present.
        """
        builder = self._get_cached_rr_builder()
        records = builder.session_index.get(session_id)
        if not records:
            return None
        return build_session_summary(records, session_id)

    def query_actions(
        self,
        action_name: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
    ) -> list:
        """Query actions across sessions via RR (ADR-0001 Phase 7b)."""
        builder = self._get_cached_rr_builder()
        navigator = RRNavigator(index_builder=builder, storage=self._storage)
        engine = RRQueryEngine(navigator=navigator)
        return engine.query_actions(
            action_name=action_name,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )

    def audit_report(self, policy_source: str, adapter_name: Optional[str] = None) -> dict:
        """Generate audit report using external policy via adapter. Returns report dict."""
        report = load_and_audit(
            self._storage,
            agent_id=self.agent_id,
            policy_source=policy_source,
            adapter_name=adapter_name,
            shard_ids=[self.shard],
        )
        return report.to_dict()

    def export_audit(
        self, policy_source: str, output_path: str, adapter_name: Optional[str] = None
    ) -> str:
        """Generate and export audit report to JSON file. Returns output path."""
        report = load_and_audit(
            self._storage,
            agent_id=self.agent_id,
            policy_source=policy_source,
            adapter_name=adapter_name,
            shard_ids=[self.shard],
        )
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report.to_json())
        return output_path

    def verify_audit_report(self, report_path: str) -> dict:
        """Verify an audit report's integrity. Returns {report_id, status}."""
        with open(report_path, "r", encoding="utf-8") as f:
            report = AuditReport.from_json(f.read())
        return verify_report(report)

    def capture_env(self, source: str, raw_data, headers: Optional[dict] = None) -> dict:
        """Capture environment fingerprint for external data."""
        return capture_environment(self._anchor_log, source, raw_data, headers)

    def verify_commitments(self) -> dict:
        """Verify all pre/post commitment pairs."""
        return verify_all_commitments(self._anchor_log)

    # ==================================================================
    # Signing helper
    # ==================================================================

    def _sign(self, data: str = "") -> str:
        """Sign data with Ed25519 if keypair available, else 'unsigned'.

        Used by A→E facade methods to provide real cryptographic proof
        when AgentSigning is configured, graceful fallback otherwise.
        """
        if self._signing and self._signing.has_keypair():
            return self._signing.sign_entry(data or self.agent_id)
        return "unsigned"

    def _public_key(self) -> Optional[str]:
        """Get agent's public key if available."""
        if self._signing and self._signing.has_keypair():
            return self._signing.get_public_key()
        return None

    # ==================================================================
    # A→E Pillar facade methods
    # ==================================================================

    # --- A: Identity Registry ---

    def register_agent(
        self,
        agent_id: str,
        public_key: str,
        model: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Entry:
        """Register an agent in the identity registry. Returns the DSM entry."""
        return self._registry.register(
            agent_id=agent_id,
            public_key=public_key,
            owner_id=self.agent_id,
            owner_signature=self._sign(),
            model=model,
            metadata=metadata,
        )

    def resolve_agent(self, agent_id: str) -> Optional[AgentIdentity]:
        """Resolve an agent identity. O(1) via cached index."""
        return self._registry.resolve(agent_id)

    def revoke_agent(self, agent_id: str, reason: str = "revoked") -> Entry:
        """Revoke an agent from the registry. Returns the DSM entry."""
        return self._registry.revoke(
            agent_id, self.agent_id, owner_signature=self._sign(), reason=reason,
        )

    def agent_trust(self, agent_id: str, deep: bool = False) -> float:
        """Get trust score for an agent. O(1) fast, O(N) deep."""
        if deep:
            return self._registry.deep_trust_score(agent_id)
        return self._registry.trust_score(agent_id)

    def list_registered_agents(self) -> List[AgentIdentity]:
        """List all registered agents."""
        return self._registry.list_agents()

    # --- B: Sovereignty Policy ---

    def set_policy(
        self,
        agents: List[str],
        min_trust_score: float = 0.5,
        allowed_types: Optional[List[str]] = None,
        approval_required: Optional[List[str]] = None,
        cross_ai: bool = False,
    ) -> Entry:
        """Set sovereignty policy for this agent's collective. Returns DSM entry."""
        return self._sovereignty.set(
            owner_id=self.agent_id,
            owner_signature=self._sign(),
            policy={
                "agents": agents,
                "min_trust_score": min_trust_score,
                "allowed_types": allowed_types or ["observation", "analysis", "decision"],
                "approval_required": approval_required or [],
                "cross_ai": cross_ai,
            },
        )

    def get_policy(self) -> Optional[PolicySnapshot]:
        """Get current sovereignty policy."""
        return self._sovereignty.get(self.agent_id)

    def check_sovereignty(
        self, agent_id: str, action_type: str
    ) -> EnforcementResult:
        """Check if an agent is allowed to perform an action."""
        return self._sovereignty.allows(
            self.agent_id, agent_id, action_type, self._registry,
        )

    # --- C: Orchestrator ---

    def admit_entry(
        self, entry: Entry, agent_id: str
    ) -> AdmissionResult:
        """Run admission control on an entry for the collective."""
        return self._orchestrator.admit(entry, agent_id, owner_id=self.agent_id)

    # --- D: Collective Memory ---

    def push_to_collective(
        self,
        entry: Entry,
        summary: str,
        detail: str = "",
        key_findings: Optional[List[str]] = None,
    ) -> Any:
        """Push a projection of an entry to the collective shard.

        Goes through orchestrator admission → sync engine write.
        Returns PushResult with admitted/rejected hashes.
        """
        return self._sync_engine.push(
            agent_id=self.agent_id,
            owner_id=self.agent_id,
            entries=[entry],
            summary_fn=lambda e: summary,
            detail_fn=lambda e: (detail, key_findings or []),
        )

    def pull_collective(self, since_hash: Optional[str] = None) -> Any:
        """Pull new entries from the collective since a hash.

        Returns PullResult with synced count and last_hash.
        """
        return self._sync_engine.pull(self.agent_id, since_hash=since_hash)

    def collective_summary(self) -> dict:
        """Get summary of the collective shard."""
        return self._collective.summary()

    def collective_recent(self, limit: int = 50) -> List[CollectiveEntry]:
        """Get recent entries from collective."""
        return self._collective.recent(limit=limit)

    def collective_at_tier(
        self, tier: int = 2, limit: int = 50,
        max_tokens: Optional[int] = None,
    ) -> List[dict]:
        """Get recent collective entries at a specific resolution tier.

        Tier 0 (~30 tokens/entry): hash, agent_id, timestamp
        Tier 1 (~80 tokens/entry): + summary, action_type
        Tier 2 (~300 tokens/entry): + detail, key_findings
        Tier 3 (~500 tokens/entry): all fields

        Auto-downgrades tier if max_tokens budget would be exceeded.
        """
        return self._collective.recent_at_tier(
            tier=tier, limit=limit, max_tokens=max_tokens,
        )

    def read_with_digests(self, since: datetime, max_tokens: int = 8000) -> Any:
        """Budget-aware context loading with rolling digests."""
        return self._digester.read_with_digests(since=since, max_tokens=max_tokens)

    def roll_digests(self, levels: Optional[List[int]] = None) -> List[Any]:
        """Produce rolling temporal digests for all pending time windows.

        Automatically identifies hourly/daily/weekly/monthly windows
        that contain entries but have no digest yet, then creates them.

        Args:
            levels: Optional filter — [1]=hourly, [2]=daily, [3]=weekly, [4]=monthly.
                    Default: all levels.

        Returns:
            List of DigestEntry objects created.
        """
        return self._digester.roll(levels=levels)

    # --- Parallel Lanes ---

    def register_lane(self, agent_id: str) -> str:
        """Register a parallel lane for an agent. Returns lane shard name."""
        return self._lanes.register_lane(agent_id)

    def push_to_lane(
        self,
        agent_id: str,
        entries: List[Entry],
        summary_fn=None,
        detail_fn=None,
    ) -> LaneWriteResult:
        """Push entries to an agent's lane (zero contention with other agents)."""
        return self._lanes.push(
            agent_id=agent_id,
            owner_id=self.agent_id,
            entries=entries,
            summary_fn=summary_fn,
            detail_fn=detail_fn,
        )

    def lane_recent(
        self,
        limit: int = 50,
        agent_id: Optional[str] = None,
    ) -> list:
        """Read recent entries across all lanes, merged by time."""
        return self._lanes.recent(limit=limit, agent_id=agent_id)

    def lane_recent_at_tier(
        self,
        tier: int = 2,
        limit: int = 50,
        max_tokens: Optional[int] = None,
        agent_id: Optional[str] = None,
    ) -> List[dict]:
        """Read across lanes at a specific resolution tier with budget control."""
        return self._lanes.recent_at_tier(
            tier=tier, limit=limit, max_tokens=max_tokens, agent_id=agent_id,
        )

    def create_lane_merge(self) -> MergeEntry:
        """Create a merge entry referencing all current lane tips."""
        return self._lanes.create_merge()

    def lane_stats(self) -> dict:
        """Get statistics across all parallel lanes."""
        return self._lanes.stats()

    # --- E: Lifecycle ---

    def lifecycle_state(self, shard_id: str) -> str:
        """Get lifecycle state of a shard (active/draining/sealed/archived)."""
        return self._lifecycle.state(shard_id)

    def drain(self, shard_id: str) -> LifecycleResult:
        """Drain a shard (trigger distillation, block further writes)."""
        return self._lifecycle.drain(
            shard_id, self.agent_id, self._sign(),
            collective=self._collective,
        )

    def lifecycle_seal(self, shard_id: str, reason: Optional[str] = None) -> LifecycleResult:
        """Seal a shard permanently. Auto-drains if active."""
        return self._lifecycle.seal(
            shard_id, self.agent_id, self._sign(),
            reason=reason, collective=self._collective,
        )

    def archive(self, shard_id: str) -> LifecycleResult:
        """Archive a sealed shard. Terminal state."""
        return self._lifecycle.archive(shard_id, self.agent_id, self._sign())

    def lifecycle_verify(self, shard_id: str, deep: bool = False) -> VerifyResult:
        """Verify shard integrity. O(1) spot-check or full replay."""
        return self._lifecycle.verify(shard_id, deep=deep)

    def lifecycle_triggers(self, shard_id: str) -> Any:
        """Check automatic lifecycle triggers for a shard."""
        return self._lifecycle.check_triggers(shard_id, self.agent_id, self._sign())

    # --- Cross-cutting: Shard Families ---

    def shard_family(self, shard_id: str) -> str:
        """Classify a shard by family (agent/registry/audit/collective/infra)."""
        return classify_shard(shard_id)

    def shards_by_family(self, family: str) -> List[str]:
        """List all known shards for a family."""
        return list_shards_by_family(self._storage, family)
