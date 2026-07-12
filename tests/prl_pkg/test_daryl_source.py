"""M1 · D2c tests — boundary act, import manifest, and the `daryl source` source map.

Boundary = one certified SessionNode per conversation; manifest = one per import run
(deterministic counts + identity in text_preview); source map = a derived RR projection
keyed by subject_id, showing the boundary receipt + authoritative ordered turn receipts.
"""

from __future__ import annotations

import json

from prl.config import PRLConfig
from prl.daryl_cli import main
from prl.ingest import _MANIFEST_PREFIX, import_chatgpt
from prl.query.source_map_read import SourceMapQuery
from prl.store import open_storage
from prl.types import SessionNode, from_entry

from dsm.rr.index import RRIndexBuilder
from dsm.rr.navigator import RRNavigator


def _export(tmp_path):
    export = {"conversations": {
        "conv-aaa-111111": {"title": "Kernel Design", "create_time": 100, "update_time": 150,
                            "messages": [{"role": "user", "text": "how does the chain work?", "t": 1},
                                         {"role": "assistant", "text": "hash + prev_hash", "t": 2}]},
        "conv-bbb-222222": {"title": "Onboarding UX", "create_time": 200, "update_time": 260,
                            "messages": [{"role": "user", "text": "z" * 9000, "t": 1}]},  # truncated
    }}
    p = tmp_path / "export.json"
    p.write_text(json.dumps(export))
    return p


def _config(tmp_path):
    return PRLConfig(declared_projects=[tmp_path], storage_dir=tmp_path / "store")


def _nav(tmp_path):
    storage = open_storage(_config(tmp_path))
    builder = RRIndexBuilder(storage=storage, index_dir=str(tmp_path / "store" / "_rr_index"))
    builder.build()
    return RRNavigator(builder, storage)


# --- boundary act + manifest (write side) -----------------------------------


def test_import_reports_identity_and_boundaries(tmp_path):
    rep = import_chatgpt(_config(tmp_path), _export(tmp_path))
    assert rep.boundary_acts == 2                       # one per imported conversation
    assert rep.run_id and rep.source_sha256 and rep.imported_at
    assert len(rep.source_sha256) == 64                  # sha-256 hex


def test_boundary_sessionnode_written_per_conversation(tmp_path):
    import_chatgpt(_config(tmp_path), _export(tmp_path))
    nav = _nav(tmp_path)
    sessions = [from_entry(e) for e in nav.resolve_entries(nav.navigate_action("prl.session"))]
    boundaries = [s for s in sessions
                  if isinstance(s, SessionNode) and not s.session_id.startswith(_MANIFEST_PREFIX)]
    assert {s.session_id for s in boundaries} == {"conv-aaa-111111", "conv-bbb-222222"}
    kernel = next(s for s in boundaries if s.session_id == "conv-aaa-111111")
    assert kernel.tool == "chatgpt" and kernel.title == "Kernel Design"
    assert kernel.started_ms == 100_000 and kernel.ended_ms == 150_000  # conversation span


def test_manifest_records_deterministic_counts_and_identity(tmp_path):
    rep = import_chatgpt(_config(tmp_path), _export(tmp_path))
    nav = _nav(tmp_path)
    sessions = [from_entry(e) for e in nav.resolve_entries(nav.navigate_action("prl.session"))]
    manifests = [s for s in sessions
                 if isinstance(s, SessionNode) and s.session_id.startswith(_MANIFEST_PREFIX)]
    assert len(manifests) == 1                           # one manifest per import run
    payload = json.loads(manifests[0].text_preview)
    assert payload["run_id"] == rep.run_id
    assert payload["source_sha256"] == rep.source_sha256
    c = payload["counts"]
    assert c["conversations_received"] == 2 and c["subjects"] == 2
    assert c["turn_acts"] == 3 and c["boundary_acts"] == 2 and c["truncations"] == 1
    assert "storage_dir" not in payload and "storage_dir" not in json.dumps(payload)  # never persisted


# --- source map (read side) -------------------------------------------------


def test_source_map_projects_boundary_and_ordered_turns(tmp_path):
    import_chatgpt(_config(tmp_path), _export(tmp_path))
    q = SourceMapQuery(open_storage(_config(tmp_path)), tmp_path / "store" / "_rr_index")
    # id6 = first 6 hex chars of "conv-aaa-111111" (non-hex stripped) → "caaa11"
    sm = q.project("kernel-design.caaa11")
    assert sm.found()
    assert sm.conversation_id == "conv-aaa-111111"       # raw provenance
    assert sm.boundary_receipt and sm.boundary_receipt.startswith("v1:")
    assert [t.role for t in sm.turns] == ["user", "assistant"]   # authoritative order
    assert [t.ordinal for t in sm.turns] == [1, 2]
    assert all(t.receipt.startswith("v1:") for t in sm.turns)


def test_source_map_flags_truncation(tmp_path):
    import_chatgpt(_config(tmp_path), _export(tmp_path))
    q = SourceMapQuery(open_storage(_config(tmp_path)), tmp_path / "store" / "_rr_index")
    sm = q.project("onboarding-ux.cbbb22")
    assert sm.found() and sm.turns[0].truncated is True


def test_source_map_not_found_is_honest(tmp_path):
    import_chatgpt(_config(tmp_path), _export(tmp_path))
    q = SourceMapQuery(open_storage(_config(tmp_path)), tmp_path / "store" / "_rr_index")
    sm = q.project("does-not-exist.zzzzzz")
    assert not sm.found()


# --- CLI --------------------------------------------------------------------


def test_cli_source_end_to_end(tmp_path, capsys):
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"declared_projects": [str(tmp_path)],
                               "storage_dir": str(tmp_path / "store")}))
    main(["import", "chatgpt", str(_export(tmp_path)), "--config", str(cfg)])
    capsys.readouterr()
    rc = main(["source", "--subject", "kernel-design.caaa11", "--config", str(cfg)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Source Map — kernel-design.caaa11" in out
    assert "conversation_id: conv-aaa-111111" in out
    assert "boundary receipt: v1:" in out
    # ordinal-1 user precedes ordinal-2 assistant (authoritative order)
    assert "#1" in out and "#2" in out
    assert out.index("user") < out.index("assistant")
    assert "exact per-turn time not recorded in M1" in out
