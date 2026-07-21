"""Swarm v0.1 — schema concordance and focused examples.

* Every stored JSON schema in ``src/prl/swarm/schemas/`` must be byte-identical
  to the one generated from the FINAL pydantic model (no drift between schema
  files and code).
* Every ``docs/swarm/examples/valid`` example must decode through the real
  model + envelope and pass the bounded writer against a real kernel store.
* Every ``docs/swarm/examples/invalid`` example must be rejected at its
  declared layer (``model`` or ``writer``) — and never reach the shard.
* Every ``docs/swarm/examples/scenarios`` file must produce its expected
  replay diagnostics (observed, never auto-resolved, never written back).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dsm.core.storage import Storage

from prl.exceptions import PRLError
from prl.store import PRLStore
from prl.swarm import project_run, to_swarm_entry
from prl.swarm.types import ACTION_TO_MODEL, SCHEMA_VERSION

REPO = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO / "src" / "prl" / "swarm" / "schemas"
EXAMPLES = REPO / "docs" / "swarm" / "examples"


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


# --- schema concordance ------------------------------------------------------


def test_schema_files_match_models_exactly():
    index = _load(SCHEMA_DIR / "INDEX.json")
    assert index["schema_version"] == SCHEMA_VERSION
    assert set(index["records"]) == set(ACTION_TO_MODEL)
    for action, fname in index["records"].items():
        stored = _load(SCHEMA_DIR / fname)
        generated = ACTION_TO_MODEL[action].model_json_schema()
        assert stored == generated, f"schema drift for {action} ({fname})"


def test_no_orphan_schema_files():
    index = _load(SCHEMA_DIR / "INDEX.json")
    on_disk = {p.name for p in SCHEMA_DIR.glob("*.schema.json")}
    assert on_disk == set(index["records"].values())


# --- valid examples ----------------------------------------------------------


@pytest.mark.parametrize(
    "path", sorted((EXAMPLES / "valid").glob("*.json")), ids=lambda p: p.name
)
def test_valid_examples_decode_and_commit(path, tmp_path):
    ex = _load(path)
    model = ACTION_TO_MODEL[ex["action_name"]]
    record = model(**ex["payload"])  # model accepts it
    store = PRLStore(Storage(data_dir=str(tmp_path)))
    result = store.commit_swarm_entry(to_swarm_entry(record))  # writer accepts it
    assert result.action_name == ex["action_name"]
    assert result.tip_hash


# --- invalid examples --------------------------------------------------------


@pytest.mark.parametrize(
    "path", sorted((EXAMPLES / "invalid").glob("*.json")), ids=lambda p: p.name
)
def test_invalid_examples_rejected_at_declared_layer(path, tmp_path):
    ex = _load(path)
    model = ACTION_TO_MODEL[ex["action_name"]]

    if ex["reject_at"] == "model":
        with pytest.raises(Exception):
            model(**ex["payload"])
        return

    assert ex["reject_at"] == "writer"
    # the payload itself is model-valid; the ENVELOPE is what must be refused
    payload_model = ACTION_TO_MODEL["swarm." + ex["payload"]["kind"]]
    record = payload_model(**ex["payload"])
    draft = to_swarm_entry(record)
    overrides = dict(ex.get("envelope_overrides", {}))
    if ex["action_name"] != "swarm." + ex["payload"]["kind"]:
        overrides["metadata"] = {**draft.metadata, "action_name": ex["action_name"]}
    bad = draft.model_copy(update=overrides)
    store = PRLStore(Storage(data_dir=str(tmp_path)))
    with pytest.raises(PRLError):
        store.commit_swarm_entry(bad)
    assert not store._storage.read(draft.shard, limit=5)  # nothing appended


# --- diagnostic scenarios ----------------------------------------------------


@pytest.mark.parametrize(
    "path", sorted((EXAMPLES / "scenarios").glob("*.json")), ids=lambda p: p.name
)
def test_scenarios_produce_expected_diagnostics(path):
    scenario = _load(path)
    records = [
        ACTION_TO_MODEL[r["action_name"]](**r["payload"])
        for r in scenario["records"]
    ]
    proj = project_run(records)
    kinds = {d.kind for d in proj.diagnostics}
    for expected in scenario["expected_diagnostics"]:
        assert expected in kinds, f"{path.name}: expected diagnostic {expected!r}, got {kinds}"
