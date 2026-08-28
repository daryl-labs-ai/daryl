"""Product Seam v0.1.1 — the CLI must be enough to maintain a project.

Two independent dogfoods found the same thing: the runtime worked, but every
project update meant leaving the CLI and writing Python. These tests hold the
CLI to being sufficient on its own, and hold the boundary that neither a model
answer nor a chat transcript becomes project truth.

The CLI is exercised as a subprocess wherever the point is the user-facing
behaviour, because that is what a person actually runs.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def hx(*args: str, expect: int = 0) -> subprocess.CompletedProcess:
    """Run the shipped CLI in a separate process, as a user would."""
    proc = subprocess.run(
        [sys.executable, "-m", "hexashard_adapter", *args],
        capture_output=True, text=True, cwd=str(REPO),
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO / "src"),
             "HOME": str(Path.home())},
    )
    assert proc.returncode == expect, (
        f"expected rc={expect}, got {proc.returncode}\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
    return proc


@pytest.fixture
def project(tmp_path) -> Path:
    root = tmp_path / "proj"
    hx("create", str(root), "--name", "seam", "--mission", "Open the depot.")
    hx("source", "add", str(root), "--type", "legal", "--title", "Berth licence",
       "--text", "Only berths 3 and 4 are licensed for the depot.")
    return root


# -- C1/C2: existing behaviour and discoverability ------------------------

def test_c1_chat_still_works(project):
    out = hx("chat", str(project), "--provider", "mock")
    assert "project seam" in out.stdout


def test_c2_help_exposes_every_authoring_operation():
    out = hx("--help")
    for verb in ("create", "status", "source", "pin", "supersede", "decision", "question", "chat"):
        assert verb in out.stdout, f"{verb} is not discoverable from --help"


def test_c2_help_explains_project_is_not_the_chat():
    out = hx("--help")
    assert "persists" in out.stdout.lower()


# -- C3-C5: project and sources ------------------------------------------

def test_c3_create_then_open(tmp_path):
    root = tmp_path / "p"
    hx("create", str(root), "--name", "alpha")
    assert (root / "project.json").is_file()
    assert "alpha" in hx("status", str(root)).stdout


def test_c3_create_refuses_to_clobber(project):
    err = hx("create", str(project), "--name", "again", expect=2).stderr
    assert "already exists" in err


def test_c4_add_source_from_cli(project):
    out = hx("source", "add", str(project), "--type", "note", "--title", "Survey",
             "--text", "The quay survey found no subsidence.")
    assert "P1.S0002" in out.stdout


def test_c4_add_source_from_file(project, tmp_path):
    f = tmp_path / "note.txt"
    f.write_text("Crane certification expires in March.")
    hx("source", "add", str(project), "--type", "ops", "--title", "Crane", "--file", str(f))
    assert "March" in hx("source", "show", str(project), "Crane").stdout


def test_c5_source_persists_across_process_reopen(project):
    hx("source", "add", str(project), "--type", "note", "--title", "Survey",
       "--text", "The quay survey found no subsidence.")
    # a genuinely separate process, reading only from disk
    assert "Survey" in hx("source", "list", str(project)).stdout
    assert "subsidence" in hx("source", "show", str(project), "Survey").stdout


# -- C6-C7: pins ----------------------------------------------------------

def test_c6_pin_by_source_title(project):
    out = hx("pin", str(project), "--key", "berths", "--value", "3 and 4",
             "--source", "Berth licence", "--critical")
    assert "grounded in P1.S0001" in out.stdout
    assert "CRITICAL" in out.stdout


def test_c7_pin_persists(project):
    hx("pin", str(project), "--key", "berths", "--value", "3 and 4", "--source", "Berth licence")
    assert "pins      1" in hx("status", str(project)).stdout


def test_c6_pin_without_grounding_is_refused_by_default(project):
    err = hx("pin", str(project), "--key", "berths", "--value", "3 and 4", expect=2).stderr
    assert "point at the source" in err


def test_c6_ungrounded_pin_requires_saying_so(project):
    out = hx("pin", str(project), "--key", "hunch", "--value", "maybe", "--ungrounded")
    assert "UNGROUNDED" in out.stdout


# -- C8-C9: supersession --------------------------------------------------

def test_c8_supersede_from_cli(project):
    hx("source", "add", str(project), "--type", "legal", "--title", "Licence amendment",
       "--text", "Berth 5 is licensed from December.")
    out = hx("supersede", str(project), "--old", "Berth licence", "--new", "Licence amendment")
    assert "supersedes" in out.stdout


def test_c9_statuses_are_correct_after_supersession(project):
    hx("source", "add", str(project), "--type", "legal", "--title", "Licence amendment",
       "--text", "Berth 5 is licensed from December.")
    hx("supersede", str(project), "--old", "Berth licence", "--new", "Licence amendment")
    listing = hx("source", "list", str(project)).stdout
    assert "SUPERSEDED" in listing and "CURRENT" in listing
    # history stays reachable
    assert "Only berths 3 and 4" in hx("source", "show", str(project), "P1.S0001").stdout


def test_c9_ordinary_supersession_surfaces_the_stale_pin(project):
    """The known claim_key limitation must be reported, never concealed."""
    hx("pin", str(project), "--key", "berths", "--value", "3 and 4", "--source", "Berth licence")
    hx("source", "add", str(project), "--type", "legal", "--title", "Licence amendment",
       "--text", "Berth 5 is licensed from December.")
    out = hx("supersede", str(project), "--old", "Berth licence", "--new", "Licence amendment")
    assert "NEEDS_REVIEW" in out.stdout
    assert "still reads" in out.stdout


def test_c9_declared_claim_carries_the_value_forward(project):
    hx("source", "add", str(project), "--type", "finance", "--title", "Budget",
       "--text", "The budget is 480k.", "--claim-key", "budget", "--claim-value", "480k")
    hx("pin", str(project), "--key", "budget", "--value", "480k", "--source", "Budget")
    hx("source", "add", str(project), "--type", "finance", "--title", "Budget revision",
       "--text", "The budget is 390k.", "--claim-key", "budget", "--claim-value", "390k")
    hx("supersede", str(project), "--old", "Budget", "--new", "Budget revision")
    from hexashard import Project
    pins = {p.key: p.value for p in Project.open(project).pins.all()}
    assert pins["budget"] == "390k"


def test_c8_source_cannot_supersede_itself(project):
    err = hx("supersede", str(project), "--old", "Berth licence",
             "--new", "Berth licence", expect=2).stderr
    assert "itself" in err


# -- C10-C11: decisions ---------------------------------------------------

def test_c10_explicit_decision_persists(project):
    hx("decision", str(project), "Winter opening confirmed for 3 November.")
    from hexashard import Project
    decisions = Project.open(project).state.recent_decisions
    assert any("3 November" in json.dumps(d) for d in decisions)


def test_c11_model_recommendation_does_not_become_a_decision(project):
    """A model answer is not authority. Only the user's decision verb is."""
    from hexashard import Project
    from hexashard_adapter import AdapterConfig, HexaShardAdapter, MockChatProvider

    adapter = HexaShardAdapter.open(project, config=AdapterConfig(provider="mock"))
    adapter.provider = MockChatProvider(
        reply="I recommend delaying the second carrier until June."
    )
    before = list(adapter.project.state.recent_decisions)
    adapter.chat("Should we delay the second carrier?")
    adapter.close()

    reopened = Project.open(project)
    assert reopened.state.recent_decisions == before
    blob = json.dumps(reopened.state.recent_decisions) + " ".join(
        s.content for s in reopened.sources.all())
    assert "I recommend delaying" not in blob


# -- C12: questions -------------------------------------------------------

def test_c12_question_can_be_opened_listed_and_resolved(project):
    hx("question", "add", str(project), "--text", "Who signs the staffing plan?")
    assert "Q1" in hx("question", "list", str(project)).stdout
    assert "1 question" in hx("status", str(project)).stdout
    hx("question", "resolve", str(project), "--id", "Q1")
    assert "resolved" in hx("question", "list", str(project)).stdout
    assert "0 question" in hx("status", str(project)).stdout


def test_c12_resolving_an_unknown_question_is_an_error(project):
    err = hx("question", "resolve", str(project), "--id", "Q9", expect=2).stderr
    assert "no question Q9" in err


# -- C13-C14: references --------------------------------------------------

def test_c13_ambiguous_title_is_not_guessed(project):
    hx("source", "add", str(project), "--type", "note", "--title", "Berth licence",
       "--text", "A second, differently sourced note with the same title.")
    err = hx("pin", str(project), "--key", "berths", "--value", "3 and 4",
             "--source", "Berth licence", expect=2).stderr
    assert "matches 2 sources" in err
    assert "P1.S0001" in err and "P1.S0002" in err


def test_c13_unknown_reference_lists_what_exists(project):
    err = hx("pin", str(project), "--key", "x", "--value", "y",
             "--source", "Nonexistent", expect=2).stderr
    assert "no source matches" in err and "Berth licence" in err


def test_c14_user_never_invents_an_internal_id(project):
    """IDs may be shown for auditability; they must not be required input."""
    hx("source", "add", str(project), "--type", "finance", "--title", "Budget",
       "--text", "The budget is 480k.")
    hx("pin", str(project), "--key", "budget", "--value", "480k", "--source", "Budget")
    hx("source", "add", str(project), "--type", "finance", "--title", "Budget revision",
       "--text", "The budget is 390k.")
    hx("supersede", str(project), "--old", "Budget", "--new", "Budget revision")
    hx("question", "add", str(project), "--text", "auto id?")
    assert "Q1" in hx("question", "list", str(project)).stdout


def test_c14_ids_are_still_shown(project):
    assert "P1.S0001" in hx("source", "list", str(project)).stdout


# -- C15-C18 --------------------------------------------------------------

def test_c15_malformed_command_is_useful(tmp_path):
    assert "no project at" in hx("status", str(tmp_path / "nope"), expect=2).stderr
    assert "create one with" in hx("status", str(tmp_path / "nope"), expect=2).stderr


def test_c15_missing_content_is_explained(project):
    err = hx("source", "add", str(project), "--type", "note",
             "--title", "Empty", expect=2).stderr
    assert "--text" in err and "--file" in err


def test_c16_read_only_still_blocks_writes(project):
    from hexashard_adapter import AdapterConfig, HexaShardAdapter
    adapter = HexaShardAdapter.open(project, config=AdapterConfig(provider="mock", mode="READ_ONLY"))
    with pytest.raises(PermissionError):
        adapter.add_source("note", "x", "y")
    turn, epoch = adapter.project.state.turn, adapter.project.state.epoch
    adapter.chat("what are the berths?")
    assert (adapter.project.state.turn, adapter.project.state.epoch) == (turn, epoch)
    adapter.close()


def test_c16_chat_announces_read_only(project):
    out = hx("chat", str(project), "--provider", "mock", "--mode", "READ_ONLY")
    assert "READ_ONLY" in out.stdout


def test_c17_c18_transcript_never_becomes_a_source(project):
    from hexashard import Project
    from hexashard_adapter import AdapterConfig, HexaShardAdapter, MockChatProvider

    adapter = HexaShardAdapter.open(project, config=AdapterConfig(provider="mock"))
    adapter.provider = MockChatProvider(reply="The depot should use berth 9 immediately.")
    before = {s.source_id for s in adapter.project.sources.all()}
    adapter.chat("Which berth should we use?")
    adapter.chat("Are you sure?")
    adapter.close()

    reopened = Project.open(project)
    assert {s.source_id for s in reopened.sources.all()} == before
    assert all("berth 9" not in (s.content or "") for s in reopened.sources.all())
