"""P0 tests — PRL foundation: models, Entry mapping, config.

Scope guard: these tests touch only ``prl`` + the repository canonical
primitive (via ``prl._canonical``). No DSM kernel, no Storage, no RR, no
filesystem scan.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from prl._canonical import canonical_bytes
from prl.config import PRLConfig
from prl.exceptions import (
    PRLConfigError,
    PRLEntryMappingError,
    PRLError,
    PRLValidationError,
)
from prl.types import (
    PRL_ACTION,
    CommitNode,
    Edge,
    EntryDraft,
    FileNode,
    ProjectNode,
    SessionNode,
    from_entry,
    to_entry,
)

SHARD = "prl_test"
RUN = "run-0001"


def _sample_nodes():
    return [
        ProjectNode(project_id="sha256:" + "a" * 64, root_path="/p/x", name="x"),
        FileNode(
            path="src/a.py",
            content_hash="sha256:" + "b" * 64,
            size=10,
            mtime_ms=1_700_000_000_000,
            project_id="sha256:" + "a" * 64,
        ),
        CommitNode(
            sha="abc123",
            author="me",
            ts_ms=1_700_000_001_000,
            message="feat: x",
            files=("src/a.py", "src/b.py"),
            project_id="sha256:" + "a" * 64,
        ),
        SessionNode(
            session_id="s1",
            tool="cursor",
            title=None,
            started_ms=1_700_000_002_000,
            ended_ms=None,
            text_preview="we decided X",
            project_id=None,
        ),
        Edge(
            edge_type="modified",
            src_id="abc123",
            dst_id="sha256:" + "b" * 64,
            confidence=0.8,
            evidence={"method": "commit_window"},
        ),
    ]


# --- Pydantic round-trip ---------------------------------------------------


@pytest.mark.parametrize("node", _sample_nodes(), ids=lambda n: type(n).__name__)
def test_pydantic_round_trip(node):
    cls = type(node)
    again = cls(**node.model_dump())
    assert again == node


# --- to_entry / from_entry round-trip --------------------------------------


@pytest.mark.parametrize("node", _sample_nodes(), ids=lambda n: type(n).__name__)
def test_to_from_entry_round_trip(node):
    draft = to_entry(node, shard=SHARD, session_id=RUN)
    assert isinstance(draft, EntryDraft)
    recovered = from_entry(draft)
    assert recovered == node
    # canonical byte-identity (the property hashes/signatures rely on)
    assert canonical_bytes(recovered.model_dump(mode="json", exclude_none=True)) == \
        canonical_bytes(node.model_dump(mode="json", exclude_none=True))


@pytest.mark.parametrize("node", _sample_nodes(), ids=lambda n: type(n).__name__)
def test_from_entry_accepts_plain_dict(node):
    draft = to_entry(node, shard=SHARD, session_id=RUN)
    as_dict = draft.model_dump()
    assert from_entry(as_dict) == node


# --- action_name correctness ----------------------------------------------


def test_action_name_per_kind():
    nodes = _sample_nodes()
    expected = ["prl.project", "prl.file", "prl.commit", "prl.session", "prl.edge"]
    for node, exp in zip(nodes, expected):
        draft = to_entry(node, shard=SHARD, session_id=RUN)
        assert draft.metadata["action_name"] == exp
    assert set(PRL_ACTION.values()) == set(expected) | {"prl.consultation"}


def test_entry_draft_has_shard_and_session():
    draft = to_entry(_sample_nodes()[1], shard=SHARD, session_id=RUN)
    assert draft.shard == SHARD
    assert draft.session_id == RUN
    assert draft.source == "prl"
    # content is canonical JSON and decodes to the file payload
    payload = json.loads(draft.content)
    assert payload["content_hash"] == "sha256:" + "b" * 64


# --- Edge confidence bounds ------------------------------------------------


@pytest.mark.parametrize("bad", [-0.1, 1.1, 2.0])
def test_edge_confidence_rejected_out_of_bounds(bad):
    with pytest.raises(ValidationError):
        Edge(edge_type="modified", src_id="a", dst_id="b", confidence=bad)


@pytest.mark.parametrize("ok", [0.0, 0.5, 1.0])
def test_edge_confidence_accepted_in_bounds(ok):
    e = Edge(edge_type="modified", src_id="a", dst_id="b", confidence=ok)
    assert e.confidence == ok


# --- invalid tool rejected -------------------------------------------------


def test_invalid_tool_rejected():
    with pytest.raises(ValidationError):
        SessionNode(session_id="s", tool="notatool", started_ms=1)


# --- from_entry error boundaries -------------------------------------------


def test_from_entry_unknown_action_name():
    with pytest.raises(PRLEntryMappingError):
        from_entry({"metadata": {"action_name": "prl.bogus"}, "content": "{}"})


def test_from_entry_missing_action_name():
    with pytest.raises(PRLEntryMappingError):
        from_entry({"metadata": {}, "content": "{}"})


def test_from_entry_bad_content():
    with pytest.raises(PRLEntryMappingError):
        from_entry({"metadata": {"action_name": "prl.file"}, "content": "not json{"})


def test_from_entry_payload_fails_model():
    # valid JSON, wrong shape for a FileNode → PRLValidationError
    with pytest.raises(PRLValidationError):
        from_entry({"metadata": {"action_name": "prl.file"}, "content": "{\"path\": 1}"})


def test_prl_errors_share_base():
    for exc in (PRLConfigError, PRLValidationError, PRLEntryMappingError):
        assert issubclass(exc, PRLError)


# --- project_id determinism ------------------------------------------------


def test_project_id_deterministic_from_path():
    a = ProjectNode.from_root("/home/me/proj")
    b = ProjectNode.from_root("/home/me/proj")
    c = ProjectNode.from_root("/home/me/other")
    assert a.project_id == b.project_id
    assert a.project_id != c.project_id
    assert a.name == "proj"
    assert a.project_id.startswith("sha256:")


# --- config ----------------------------------------------------------------


def test_config_load_minimal(tmp_path):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"declared_projects": ["/home/me/proj"]}))
    cfg = PRLConfig.load(cfg_file)
    assert len(cfg.declared_projects) == 1
    assert cfg.embedding_model == "local"  # D5 default
    assert ".py" in cfg.index_extensions


def test_config_declared_projects_cannot_be_empty(tmp_path):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"declared_projects": []}))
    with pytest.raises(PRLConfigError):
        PRLConfig.load(cfg_file)


def test_config_missing_file_raises(tmp_path):
    with pytest.raises(PRLConfigError):
        PRLConfig.load(tmp_path / "nope.json")


def test_config_bad_json_raises(tmp_path):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text("{not valid json")
    with pytest.raises(PRLConfigError):
        PRLConfig.load(cfg_file)
