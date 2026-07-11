"""M1 · D2b tests — official ChatGPT export normalizer (`.zip`/tree → D2a shape).

A synthetic official conversation exercises every ratified policy branch (P1–P5):
linearization to current_node, an off-path regeneration, a system node, a tool node,
a multimodal image placeholder, a hidden node, an empty node. Validated against the
documented OpenAI export structure and synthetic fixtures — NOT yet against a real export.
"""

from __future__ import annotations

import json
import zipfile

import pytest

from prl.config import PRLConfig
from prl.daryl_cli import main
from prl.exceptions import PRLError
from prl.ingest import import_chatgpt
from prl.chatgpt_normalize import (
    _is_official,
    _render_content,
    normalize_official,
    resolve_conversations,
)


def _node(nid, role, content, parent, children, *, t=0.0, hidden=False):
    meta = {"is_visually_hidden_from_conversation": True} if hidden else {}
    return {"id": nid, "parent": parent, "children": children,
            "message": {"author": {"role": role}, "create_time": t,
                        "content": content, "metadata": meta}}


def _text(*parts):
    return {"content_type": "text", "parts": list(parts)}


def _official_conv():
    """root→n7 kept path; n3b is an off-path regeneration."""
    mapping = {
        "n0": {"id": "n0", "parent": None, "children": ["n1"], "message": None},  # root anchor
        "n1": _node("n1", "system", _text("you are helpful"), "n0", ["n2"], t=1),
        "n2": _node("n2", "user", _text("hello"), "n1", ["n3", "n3b"], t=2),
        "n3": _node("n3", "assistant", _text("hi there"), "n2", ["n4"], t=3),
        "n3b": _node("n3b", "assistant", _text("regenerated alt"), "n2", [], t=3),  # off path
        "n4": _node("n4", "tool", _text("tool ran ok"), "n3", ["n5"], t=4),
        "n5": _node("n5", "assistant",
                    {"content_type": "multimodal_text",
                     "parts": ["look:", {"content_type": "image_asset_pointer",
                                         "asset_pointer": "file-xyz"}]},
                    "n4", ["n6"], t=5),
        "n6": _node("n6", "assistant", _text("secret"), "n5", ["n7"], t=6, hidden=True),
        "n7": _node("n7", "assistant", _text(""), "n6", [], t=7),  # empty
    }
    return {"conversation_id": "abc123de-0000", "title": "Kernel Design",
            "create_time": 100.0, "update_time": 200.0,
            "current_node": "n7", "mapping": mapping}


# --- content rendering (P4) -------------------------------------------------


def test_render_text_and_multimodal_placeholder():
    assert _render_content(_text("a", "b")) == ("a\nb", 0)
    text, ph = _render_content({"content_type": "multimodal_text",
                                "parts": ["look:", {"asset_pointer": "x"}]})
    assert text == "look:\n[image]" and ph == 1


def test_render_flat_text_and_typed_placeholder_and_empty():
    # a flat "text" content (tether_quote/code/…) is kept verbatim
    assert _render_content({"content_type": "tether_quote", "text": "quoted"}) == ("quoted", 0)
    # opaque content with no renderable text → typed, counted placeholder
    assert _render_content({"content_type": "execution_output"}) == ("[execution_output]", 1)
    assert _render_content(_text("")) == ("", 0)


# --- normalization (P1/P2/P3/P5) --------------------------------------------


def test_normalize_official_linearizes_and_reports():
    out, report = normalize_official([_official_conv()])
    assert set(out) == {"abc123de-0000"}
    msgs = out["abc123de-0000"]["messages"]
    assert [(m["role"], m["text"]) for m in msgs] == [
        ("user", "hello"),
        ("assistant", "hi there"),
        ("tool", "tool ran ok"),          # tool kept (P3)
        ("assistant", "look:\n[image]"),  # placeholder (P4)
    ]
    # P5 — every drop counted by reason
    assert report.dropped_system == 1     # n1
    assert report.dropped_branches == 1   # n3b off-path regeneration
    assert report.dropped_hidden == 1     # n6
    assert report.dropped_empty == 1      # n7
    assert report.placeholder_nontext == 1
    assert report.any()


def test_linearization_fallback_without_current_node():
    conv = _official_conv()
    conv["current_node"] = None  # broken pointer → create_time-ordered fallback
    out, _ = normalize_official([conv])
    # still recovers the message-bearing nodes in order (incl. the off-path sibling now)
    roles = [m["role"] for m in out["abc123de-0000"]["messages"]]
    assert roles[0] == "user" and "assistant" in roles and "tool" in roles


# --- format detection / resolution ------------------------------------------


def test_is_official_detection():
    assert _is_official([_official_conv()]) is True
    assert _is_official({"conversations": {"c1": {"title": "T", "messages": []}}}) is False
    assert _is_official({"c1": {"title": "T", "messages": []}}) is False


def test_resolve_passthrough_normalized(tmp_path):
    p = tmp_path / "norm.json"
    p.write_text(json.dumps({"conversations": {"c1": {"title": "T",
                            "messages": [{"role": "user", "text": "hi", "t": 1}]}}}))
    convs, report = resolve_conversations(p)
    assert "c1" in convs and not report.any()  # untouched, no drops


def _write_zip(tmp_path, payload, name="conversations.json"):
    z = tmp_path / "export.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr(name, json.dumps(payload))
    return z


def test_resolve_official_zip(tmp_path):
    z = _write_zip(tmp_path, [_official_conv()])
    convs, report = resolve_conversations(z)
    assert convs["abc123de-0000"]["title"] == "Kernel Design"
    assert report.dropped_branches == 1 and report.placeholder_nontext == 1


def test_resolve_zip_without_conversations_json(tmp_path):
    z = _write_zip(tmp_path, [_official_conv()], name="other.json")
    with pytest.raises(PRLError, match="no conversations.json"):
        resolve_conversations(z)


# --- end to end (reuses the D2a seeding path unchanged) ---------------------


def test_import_official_zip_end_to_end(tmp_path):
    z = _write_zip(tmp_path, [_official_conv()])
    config = PRLConfig(declared_projects=[tmp_path], storage_dir=tmp_path / "store")
    report = import_chatgpt(config, z)
    assert report.conversations == 1
    assert report.subjects == 1                     # kernel-design.abc123 (id6 from conversation_id)
    assert report.acts == 4                          # the 4 kept turns
    assert report.normalization.dropped_branches == 1
    assert report.normalization.placeholder_nontext == 1


def test_cli_import_official_zip_reports_normalization(tmp_path, capsys):
    z = _write_zip(tmp_path, [_official_conv()])
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"declared_projects": [str(tmp_path)],
                               "storage_dir": str(tmp_path / "store")}))
    rc = main(["import", "chatgpt", str(z), "--config", str(cfg)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "✓ imported 4 acts from 1 conversations" in out
    assert "normalization (official export):" in out
    assert "branches=1" in out and "non-text-placeholders=1" in out
