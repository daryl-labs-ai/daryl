"""
Tests for DarylAgent startup_verify parameter (S-5).
"""

import json
import uuid
from datetime import datetime, timezone

import pytest

from dsm.core.models import Entry
from dsm.core.storage import Storage

try:
    from dsm.agent import DarylAgent
    AGENT_AVAILABLE = True
except ImportError:
    AGENT_AVAILABLE = False


def _make_entry(content: str, shard: str = "sessions") -> Entry:
    return Entry(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        session_id="agent_startup_test",
        source="test",
        content=content,
        shard=shard,
        hash="",
        prev_hash=None,
        metadata={},
        version="v2.0",
    )


@pytest.fixture(autouse=True)
def _reset_agent_cache():
    """Reset DarylAgent startup cache between tests for isolation."""
    if AGENT_AVAILABLE:
        DarylAgent._reset_startup_cache()
    yield
    if AGENT_AVAILABLE:
        DarylAgent._reset_startup_cache()


@pytest.mark.skipif(not AGENT_AVAILABLE, reason="DarylAgent not importable")
class TestAgentStartup:
    def test_agent_startup_reconcile_default(self, tmp_path):
        """Default startup_verify='reconcile' runs reconciliation."""
        storage = Storage(data_dir=str(tmp_path))
        for i in range(3):
            storage.append(_make_entry(f"pre_{i}"))

        agent = DarylAgent(
            agent_id="test_agent",
            data_dir=str(tmp_path),
            startup_verify="reconcile",
            signing_dir=False,
            artifact_dir=False,
        )
        assert agent.startup_report is not None
        assert agent.startup_report["status"] in ("OK", "RECONCILED")

    def test_agent_startup_disabled(self, tmp_path):
        """startup_verify=False skips all checks."""
        agent = DarylAgent(
            agent_id="test_agent",
            data_dir=str(tmp_path),
            startup_verify=False,
            signing_dir=False,
            artifact_dir=False,
        )
        assert agent.startup_report is None

    def test_agent_startup_full_verify(self, tmp_path):
        """startup_verify='full' runs reconcile + full chain verification."""
        storage = Storage(data_dir=str(tmp_path))
        for i in range(5):
            storage.append(_make_entry(f"full_{i}"))

        agent = DarylAgent(
            agent_id="test_agent",
            data_dir=str(tmp_path),
            startup_verify="full",
            signing_dir=False,
            artifact_dir=False,
        )
        report = agent.startup_report
        assert report is not None
        assert report["status"] == "OK"
        assert len(report["verified"]) >= 1

    def test_agent_startup_strict_raises_on_tampering(self, tmp_path):
        """startup_verify='strict' raises RuntimeError if integrity check fails."""
        storage = Storage(data_dir=str(tmp_path))
        for i in range(5):
            storage.append(_make_entry(f"strict_{i}"))

        seg_dir = tmp_path / "shards" / "sessions"
        seg_files = list(seg_dir.glob("*.jsonl"))
        assert len(seg_files) >= 1
        with open(seg_files[0], "r", encoding="utf-8") as f:
            lines = f.readlines()
        modified = []
        for i, line in enumerate(lines):
            if not line.strip():
                modified.append(line)
                continue
            data = json.loads(line.strip())
            if i == 1:
                data["content"] = "TAMPERED"
            modified.append(
                json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
            )
        with open(seg_files[0], "w", encoding="utf-8") as f:
            f.writelines(modified)

        with pytest.raises(RuntimeError, match="integrity check failed"):
            DarylAgent(
                agent_id="strict_agent",
                data_dir=str(tmp_path),
                startup_verify="strict",
                signing_dir=False,
                artifact_dir=False,
            )

    def test_agent_startup_cache_deduplication(self, tmp_path):
        """Multiple agents on same data_dir only trigger one startup check."""
        storage = Storage(data_dir=str(tmp_path))
        storage.append(_make_entry("dedup"))

        a1 = DarylAgent(
            agent_id="agent_1",
            data_dir=str(tmp_path),
            startup_verify="reconcile",
            signing_dir=False,
            artifact_dir=False,
        )
        a2 = DarylAgent(
            agent_id="agent_2",
            data_dir=str(tmp_path),
            startup_verify="reconcile",
            signing_dir=False,
            artifact_dir=False,
        )
        assert a1.startup_report is not None
        assert a2.startup_report is not None
        assert a1.startup_report is a2.startup_report
