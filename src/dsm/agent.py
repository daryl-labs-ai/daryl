"""
DarylAgent SDK — plug-and-play facade for DSM.

Single entry point: Storage, SessionGraph, Witness, Audit, Coverage.
Agent developers need zero DSM knowledge; 5 lines to integrate.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional, Set, Union

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
from .core.storage import Storage
from .receipts import make_receipt
from .session.session_graph import SessionGraph
from .session.session_index import SessionIndex
from .session.session_limits_manager import SessionLimitsManager
from .exchange import (
    TaskReceipt,
    issue_receipt as issue_receipt_fn,
    list_received_receipts,
    store_external_receipt,
    verify_receipt as verify_receipt_fn,
)
from .seal import SealRegistry, list_sealed_shards, seal_shard as seal_shard_fn, verify_seal as verify_seal_fn
from .verify import verify_all, verify_shard
from .witness import ShardWitness
from .signing import AgentSigning, import_public_key
from .artifacts import ArtifactStore

logger = logging.getLogger("dsm.agent")


class DarylAgent:
    """
    Facade that wires Storage, SessionGraph, optional Witness/Audit.
    Use agent_id as session source; all methods map to existing DSM modules.
    """

    def __init__(
        self,
        agent_id: str,
        data_dir: str = "data",
        shard: str = "sessions",
        witness_dir: Optional[str] = None,
        witness_key: str = "",
        signing_dir: Optional[Union[str, bool]] = None,
        artifact_dir: Optional[Union[str, bool]] = None,
    ):
        self.agent_id = agent_id
        self.data_dir = Path(data_dir)
        self.shard = shard
        self._storage = Storage(data_dir=str(self.data_dir))
        limits = SessionLimitsManager.agent_defaults(str(self.data_dir))
        self._graph = SessionGraph(storage=self._storage, limits_manager=limits)
        self._witness = (
            ShardWitness(witness_dir, witness_key) if witness_dir else None
        )
        self._anchor_log = AnchorLog(str(self.data_dir / "anchors"))
        self._index_dir = str(self.data_dir / "index")
        self._pending_commitments = {}  # intent_id -> commitment_hash
        self._signing = None
        if signing_dir is not False:
            path = signing_dir if isinstance(signing_dir, str) else str(self.data_dir / "keys")
            self._signing = AgentSigning(path, self.agent_id)
        self._artifact_store = None
        if artifact_dir is not False:
            path = artifact_dir if isinstance(artifact_dir, str) else str(self.data_dir / "artifacts")
            self._artifact_store = ArtifactStore(path)

    @property
    def storage(self):
        return self._storage

    @property
    def graph(self):
        return self._graph

    def start(self) -> Optional[Any]:
        try:
            return self._graph.start_session(source=self.agent_id)
        except OSError as e:
            logger.error("start failed: %s", e)
            return None

    def end(self) -> Optional[Any]:
        try:
            return self._graph.end_session()
        except OSError as e:
            logger.error("end failed: %s", e)
            return None

    def snapshot(self, data: dict) -> Optional[Any]:
        try:
            return self._graph.record_snapshot(data)
        except OSError as e:
            logger.error("snapshot failed: %s", e)
            return None

    def intend(self, action_name: str, params: Optional[dict] = None) -> Optional[str]:
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
            if self._signing and self._signing.has_keypair() and entry and entry.hash:
                try:
                    signature = self._signing.sign_entry(entry.hash)
                    self._anchor_log._append_record({
                        "type": "entry_signature",
                        "entry_id": entry.id,
                        "entry_hash": entry.hash,
                        "signature": signature,
                        "public_key": self._signing.get_public_key(),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                except Exception as e:
                    logger.debug("entry signing skipped: %s", e)
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

    def verify(self, shard_id: Optional[str] = None) -> Any:
        if shard_id:
            return verify_shard(self._storage, shard_id)
        return verify_all(self._storage)

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

    def issue_receipt(self, entry_id: str, shard_id: str, task_description: str) -> dict:
        receipt = issue_receipt_fn(self._storage, self.agent_id, entry_id, shard_id, task_description)
        result = receipt.to_dict()
        if self._signing is not None and self._signing.has_keypair():
            try:
                result["signature"] = self._signing.sign_receipt(receipt.receipt_hash)
                result["public_key"] = self._signing.get_public_key()
            except Exception as e:
                logger.debug("receipt signing skipped: %s", e)
        return result

    def receive_receipt(self, receipt_json: str) -> dict:
        receipt = TaskReceipt.from_json(receipt_json)
        vr = verify_receipt_fn(receipt)
        stored = False
        if vr["status"] == "INTACT":
            store_external_receipt(self._storage, receipt, self.agent_id, shard_id="receipts")
            stored = True
        return {"stored": stored, "receipt_id": receipt.receipt_id, "integrity": vr["status"]}

    def verify_external_receipt(self, receipt_json: str) -> dict:
        receipt = TaskReceipt.from_json(receipt_json)
        return verify_receipt_fn(receipt)

    def list_receipts(self) -> List[dict]:
        return [r.to_dict() for r in list_received_receipts(self._storage, shard_id="receipts")]

    def generate_keys(self, force: bool = False) -> dict:
        """Generate ed25519 keypair for this agent. Idempotent."""
        if self._signing is None:
            raise ValueError("Signing is disabled")
        return self._signing.generate_keypair(force=force)

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
        """Build or rebuild session index for this agent's shard."""
        index = SessionIndex(self._index_dir, shard_id=self.shard)
        return index.build_from_storage(self._storage)

    def find_session(self, session_id: str) -> Optional[dict]:
        """Quick O(1) lookup for session metadata via index."""
        index = SessionIndex(self._index_dir, shard_id=self.shard)
        return index.find_session(session_id)

    def query_actions(
        self,
        action_name: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
    ) -> list:
        """Query actions across sessions using index."""
        index = SessionIndex(self._index_dir, shard_id=self.shard)
        return index.get_actions(
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
