"""M1 · D2a tests — `daryl import chatgpt <normalized.json>`.

Covers the ratified seeding rules as pure, store-free assertions (subject = slug(title),
agent_id = bare role, verbatim answer, 8000-char ceiling + explicit marker), the
end-to-end import against a real tmp store (counts + certified shard), and the CLI surface
(counts printed, corpus-derived pointers, honest .zip refusal).
"""

from __future__ import annotations

import json

import pytest

from dsm.core.storage import Storage
from dsm.verify import verify_shard

from prl.collectors import ConsultationAdapter
from prl.config import PRLConfig
from prl.daryl_cli import main
from prl.exceptions import PRLError
from prl.ingest import (
    MAX_ANSWER_CHARS,
    ImportReport,
    build_turn_act,
    import_chatgpt,
    load_conversations,
    slugify,
    _sorted_turns,
    _subject_id,
    _truncate,
)
from prl.store import CONSULTATION_SHARD


# --- pure rules -------------------------------------------------------------


def test_slugify():
    assert slugify("Deploying the DSM Kernel!") == "deploying-the-dsm-kernel"
    assert slugify("  Multi   space / punct.  ") == "multi-space-punct"
    assert slugify("") == ""


def test_subject_id_uniform_id6_suffix():
    """Canonical M1 rule (ratified 2026-07-08): slug(title).<id6>, ALWAYS suffixed —
    one subject per conversation, no title conflation."""
    assert _subject_id("New chat", "e3f9400c-6b90-8330") == "new-chat.e3f940"
    # same title, different conv id → DIFFERENT subjects (no conflation)
    a = _subject_id("Traduction en turc", "7698a12b-9258-8328")
    b = _subject_id("Traduction en turc", "0d8162f9-7890-832f")
    assert a != b and a == "traduction-en-turc.7698a1" and b == "traduction-en-turc.0d8162"
    # empty title → safe base, still suffixed
    assert _subject_id("", "abcdef12-0000") == "untitled.abcdef"


def test_sorted_turns_orders_and_drops_empty():
    conv = {"messages": [
        {"role": "assistant", "text": "second", "t": 2},
        {"role": "user", "text": "first", "t": 1},
        {"role": "user", "text": "   ", "t": 3},   # empty → dropped
        {"role": "tool", "text": "third", "t": 4},
    ]}
    assert _sorted_turns(conv) == [("user", "first"), ("assistant", "second"), ("tool", "third")]


def test_truncate_ceiling_and_marker():
    short = "x" * 10
    assert _truncate(short) == (short, False)

    long = "y" * (MAX_ANSWER_CHARS + 500)
    answer, truncated = _truncate(long)
    assert truncated is True
    assert answer.startswith("y" * MAX_ANSWER_CHARS)
    assert "truncated by daryl-import" in answer
    assert "500 chars omitted" in answer


def test_build_turn_act_applies_ratified_attribution():
    node, truncated = build_turn_act(
        ConsultationAdapter(), subject_id="my-subject", role="assistant", text="hello", org_id="org.x"
    )
    assert truncated is False
    assert node.subject_id == "my-subject"
    assert node.mode == "observation"          # standing derives PROPOSED, not stored
    assert node.answer == "hello"              # verbatim
    assert node.mef.agent_id == "assistant"    # bare role (ratified Q2)
    assert node.mef.carrier.provider == "chatgpt"   # provenance in the carrier, not agent_id
    assert node.mef.confidence == 1.0
    assert node.org_id == "org.x"


# --- loader -----------------------------------------------------------------


def test_load_conversations_tolerates_wrappers(tmp_path):
    p = tmp_path / "e.json"
    p.write_text(json.dumps({"conversations": {"c1": {"title": "T", "messages": []}}}))
    assert "c1" in load_conversations(p)

    p.write_text(json.dumps({"c2": {"title": "T", "messages": []}}))  # bare map
    assert "c2" in load_conversations(p)

    p.write_text("not json")
    with pytest.raises(PRLError):
        load_conversations(p)


# --- end to end -------------------------------------------------------------


def _export(tmp_path):
    export = {
        "conversations": {
            "c1": {"title": "Kernel Design", "create_time": 100, "messages": [
                {"role": "user", "text": "how does the chain work?", "t": 1},
                {"role": "assistant", "text": "hash + prev_hash", "t": 2},
            ]},
            "c2": {"title": "Onboarding UX", "create_time": 200, "messages": [
                {"role": "user", "text": "z" * (MAX_ANSWER_CHARS + 10), "t": 1},  # truncated
            ]},
            "c3": {"title": "Empty", "messages": []},  # no turns → counts as conv, no subject/acts
        }
    }
    p = tmp_path / "export.json"
    p.write_text(json.dumps(export))
    return p


def _config(tmp_path):
    return PRLConfig(declared_projects=[tmp_path], storage_dir=tmp_path / "store")


def test_import_seeds_and_reports_counts(tmp_path):
    report = import_chatgpt(_config(tmp_path), _export(tmp_path))
    assert isinstance(report, ImportReport)
    assert report.conversations == 3          # all three, incl. the empty one
    assert report.subjects == 2               # kernel-design, onboarding-ux (empty has no turns)
    assert report.acts == 3                   # 2 + 1
    assert report.truncations == 1
    assert report.suggestions                 # corpus-derived pointers offered


def test_import_writes_certified_acts(tmp_path):
    rep = import_chatgpt(_config(tmp_path), _export(tmp_path))
    storage = Storage(data_dir=str(tmp_path / "store"))
    report = verify_shard(storage, CONSULTATION_SHARD)
    assert str(report["status"]).endswith("OK")
    # turn acts (3) + one boundary SessionNode per imported conversation (2) + one manifest (1)
    assert report["total_entries"] == rep.acts + rep.boundary_acts + 1
    assert rep.boundary_acts == 2


def test_import_suggestions_are_recency_ordered_object_pointers(tmp_path):
    report = import_chatgpt(_config(tmp_path), _export(tmp_path))
    # c2 (create_time 200) is more recent than c1 (100) → onboarding-ux first, .id6 suffixed
    assert report.suggestions[0].startswith('daryl object --subject "onboarding-ux.c2"')


def test_import_malformed_zip_errors_honestly(tmp_path):
    # .zip is now accepted (D2b); a file that isn't a real zip fails with an honest error.
    zip_path = tmp_path / "export.zip"
    zip_path.write_bytes(b"PK\x03\x04not-a-zip")
    with pytest.raises(PRLError, match="not a valid zip"):
        import_chatgpt(_config(tmp_path), zip_path)


# --- CLI surface ------------------------------------------------------------


def test_cli_import_end_to_end(tmp_path, capsys):
    export = _export(tmp_path)
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"declared_projects": [str(tmp_path)],
                               "storage_dir": str(tmp_path / "store")}))
    rc = main(["import", "chatgpt", str(export), "--config", str(cfg)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "✓ imported 3 acts from 3 conversations" in out
    assert "subjects:    2" in out
    assert "truncations: 1" in out
    assert "Try these now:" in out


def test_cli_import_malformed_zip_errors(tmp_path, capsys):
    zip_path = tmp_path / "e.zip"
    zip_path.write_bytes(b"PKnope")
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"declared_projects": [str(tmp_path)],
                               "storage_dir": str(tmp_path / "store")}))
    rc = main(["import", "chatgpt", str(zip_path), "--config", str(cfg)])
    assert rc == 2
    assert "not a valid zip" in capsys.readouterr().err
