"""
DarylAgent SDK — plug-and-play facade for DSM.

Single entry point: Storage, SessionGraph, Witness, Audit, Coverage.
Agent developers need zero DSM knowledge; 5 lines to integrate.
"""

import logging
from pathlib import Path
from typing import Any, List, Optional, Set

from .audit import Policy, audit_all, audit_shard
from .coverage import check_coverage
from .core.storage import Storage
from .receipts import make_receipt
from .session.session_graph import SessionGraph
from .session.session_limits_manager import SessionLimitsManager
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
            return entry.metadata.get("intent_id") or entry.id
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
