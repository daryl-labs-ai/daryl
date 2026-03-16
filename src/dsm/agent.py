"""
DarylAgent SDK — plug-and-play facade for DSM.

Single entry point: Storage, SessionGraph, Witness, Audit, Coverage.
Agent developers need zero DSM knowledge; 5 lines to integrate.
"""

import logging
from pathlib import Path
from typing import Any, List, Optional, Set

from .anchor import AnchorLog, pre_commit, post_commit, capture_environment, verify_all_commitments
from .audit import Policy, audit_all, audit_shard
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
            except OSError:
                pass  # anchor failure should not block agent
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
        # P4: post-commit anchoring
        try:
            commitment_hash = self._pending_commitments.pop(intent_id, None)
            post_commit(
                self._anchor_log, intent_id, result_data,
                raw_input=raw_input, commitment_hash=commitment_hash,
            )
        except OSError:
            pass  # anchor failure should not block agent
        try:
            return self._graph.confirm_action(
                intent_id,
                result_data=result_data,
                success=success,
                input_hash=receipt.get("input_hash"),
                input_preview=receipt.get("input_preview"),
            )
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
        return receipt.to_dict()

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

    def capture_env(self, source: str, raw_data, headers: Optional[dict] = None) -> dict:
        """Capture environment fingerprint for external data."""
        return capture_environment(self._anchor_log, source, raw_data, headers)

    def verify_commitments(self) -> dict:
        """Verify all pre/post commitment pairs."""
        return verify_all_commitments(self._anchor_log)
