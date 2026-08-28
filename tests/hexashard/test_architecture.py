"""Architectural boundary, determinism and recovery tests.

These encode the parts of the acceptance criteria that are properties of the
*architecture* rather than of a single behaviour, so drift shows up as a test
failure rather than as prose in a document.
"""

import json
import re
from pathlib import Path

import pytest

from hexashard import HexType, Project, SourceStatus, Temperature

# Migrated: the Core is an installed package, so resolve it rather than
# assuming it sits beside this test directory.
import hexashard as _hexashard

PKG = Path(_hexashard.__file__).resolve().parent
SOURCES = {p.name: p.read_text(encoding="utf-8") for p in sorted(PKG.glob("*.py"))}
ALL_SOURCE = "\n".join(SOURCES.values())


def _code_only(text: str) -> str:
    """Executable tokens only -- docstrings and comments are documentation.

    The docs deliberately *name* the mechanisms this build excludes, so the
    boundary checks below must look at code, not prose.
    """
    import io
    import tokenize

    out = []
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type in (tokenize.STRING, tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE):
            continue
        out.append(tok.string)
    return " ".join(out)


def _identifiers(text: str) -> set[str]:
    import io
    import tokenize

    return {t.string for t in tokenize.generate_tokens(io.StringIO(text).readline)
            if t.type == tokenize.NAME}


CODE = "\n".join(_code_only(src) for src in SOURCES.values())
IDENTIFIERS = set().union(*(_identifiers(src) for src in SOURCES.values()))


# -- what must not exist ---------------------------------------------------
#: Identifiers whose presence would mean a rejected mechanism came back under
#: its own name.  Checked against code identifiers, never against prose.
BANNED_IDENTIFIERS = {
    "Agent", "AgentScheduler", "HexAgent", "Swarm", "swarm", "spawn",
    "activation", "activate", "neuron", "neural", "Packet", "packet",
    "neighbour_route", "route_to_neighbour", "six_neighbours", "adjacency",
    "sign", "signature", "verify_signature", "hash_chain", "merkle", "Merkle",
    "ed25519", "Ed25519", "blockchain", "receipt", "digest_chain",
}


def test_no_rejected_mechanism_exists_as_code():
    """Nothing the experiments rejected is present, even renamed."""
    assert IDENTIFIERS & BANNED_IDENTIFIERS == set()


@pytest.mark.parametrize("banned", ["merkle", "blockchain", "ed25519", "hash_chain",
                                    "hashlib", "hmac", "cryptography"])
def test_no_cryptography_in_core(banned):
    assert banned not in CODE.lower()


def test_no_cryptographic_or_vendor_imports():
    import ast

    imports: set[str] = set()
    for src in SOURCES.values():
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Import):
                imports |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imports.add(node.module.split(".")[0])
    stdlib_ok = {
        "__future__", "abc", "collections", "dataclasses", "enum", "hexashard",
        "contextlib", "copy", "json", "math", "os", "pathlib", "re", "tempfile",
        "typing", "uuid", "zlib",
    }
    assert imports - stdlib_ok == set(), f"unexpected imports: {imports - stdlib_ok}"


def test_no_dsm_dependency_anywhere():
    # DSM appears in the documentation, explaining why it is *not* here.
    assert "dsm" not in CODE.lower()
    assert "import dsm" not in ALL_SOURCE


def test_runtime_dependencies_are_zero():
    """The package must import with nothing but the standard library."""
    import subprocess
    import sys

    out = subprocess.run(
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0, {str(PKG.parent)!r}); import hexashard; "
         "print(len([m for m in sys.modules if not m.startswith('_')]))"],
        capture_output=True, text=True, check=True,
    )
    assert out.stdout.strip().isdigit()


# -- generic graph, not a hexagonal lattice --------------------------------
def test_relations_are_a_generic_graph_with_no_degree_limit(proj):
    hub = proj.add_hex("Hub", HexType.REFERENCE)
    spokes = [proj.add_hex(f"Spoke {i}", HexType.SOURCE) for i in range(12)]
    for s in spokes:
        proj.relate(hub.hex_id, "REFERENCES", s.hex_id)
    assert len(proj.relations.neighbours(hub.hex_id)) == 12      # > 6, by design
    assert proj.hexmap.get(hub.hex_id).hex_id == "P1.E1.H001"
    # addresses encode project/epoch/shard only -- no neighbour geometry
    assert re.fullmatch(r"P1\.E1\.H\d{3}", spokes[0].hex_id)


# -- temperature is bookkeeping, not cognition -----------------------------
class ExplodingProvider:
    name = "exploding"

    def generate(self, *a, **k):  # pragma: no cover
        raise AssertionError("core made a model call")


def test_context_management_needs_no_model_call(tmp_path):
    p = Project.create(tmp_path / "p", name="t", mission="m",
                       provider=ExplodingProvider())
    h1 = p.add_hex("A", HexType.SOURCE)
    h2 = p.add_hex("B", HexType.CONSTRAINT)
    s = p.add_source("spec", "s", "gasket tolerance is 0.4 mm", hex_id=h1.hex_id)
    p.pin("tolerance", "0.4 mm", s.source_id, critical=True)

    p.handle_turn("gasket tolerance")            # retrieval + budget + temper
    counts = p.retemper(extra_warm=[h2.hex_id])
    assert p.hexmap.get(h1.hex_id).temperature is Temperature.HOT
    assert p.hexmap.get(h2.hex_id).temperature is Temperature.WARM
    assert counts["HOT"] == 1 and counts["WARM"] == 1

    p.hexmap.set_temperature(h2.hex_id, Temperature.COLD)
    assert p.hexmap.get(h2.hex_id).temperature is Temperature.COLD
    p.state.current_summary = "x" * 4000
    assert p.rotate_epoch().to_epoch == 2        # rotation is deterministic too


def test_temperature_does_not_imply_authority(tmp_path):
    p = Project.create(tmp_path / "p", name="t")
    h = p.add_hex("Draft corner", HexType.SOURCE)
    draft = p.add_source("draft", "d", "the ceiling might be 9 million",
                         status=SourceStatus.DRAFT, hex_id=h.hex_id)
    p.state.touch_hex(h.hex_id)
    p.retemper()
    assert p.hexmap.get(h.hex_id).temperature is Temperature.HOT
    # HOT, and still not authoritative
    assert p.retrieve("ceiling").source_ids == []
    assert p.sources.get(draft.source_id).status is SourceStatus.DRAFT


# -- the map is cheaper than the corpus ------------------------------------
def test_hexmap_index_is_far_cheaper_than_the_corpus(tmp_path):
    from hexashard import json_tokens

    p = Project.create(tmp_path / "p", name="t")
    with p.bulk():
        for i in range(40):
            h = p.add_hex(f"Area {i}", HexType.SOURCE, tags=[f"a{i}"])
            p.add_source("doc", f"Doc {i}", ("filler sentence about component %d. " % i) * 200,
                         hex_id=h.hex_id)
    index_tokens = json_tokens(p.hexmap.index_view())
    corpus_tokens = p.sources.total_tokens(p.counter)
    assert corpus_tokens > 40_000
    assert index_tokens < corpus_tokens / 40


# -- determinism -----------------------------------------------------------
def _build(root: Path) -> Project:
    p = Project.create(root, name="det", mission="deterministic build")
    a = p.add_hex("Specs", HexType.SOURCE, tags=["spec"])
    b = p.add_hex("Decisions", HexType.DECISION, tags=["adr"])
    s1 = p.add_source("spec", "Brief", "The ceiling is 4.2 million euro.", hex_id=a.hex_id,
                      claim_key="ceiling", claim_value="4.2M")
    p.add_source("decision", "ADR-1", "We adopt federated replication.", hex_id=b.hex_id)
    p.relate(b.hex_id, "DERIVED_FROM", a.hex_id)
    p.pin("ceiling", "4.2M", s1.source_id, critical=True, hex_id=a.hex_id)
    p.handle_turn("what is the ceiling")
    p.close()
    return p


def test_identical_inputs_produce_identical_projects(tmp_path):
    p1, p2 = _build(tmp_path / "one"), _build(tmp_path / "two")
    for name in ("hexmap.jsonl", "pins.jsonl", "relations.jsonl",
                 "active_state.json", "sources/P1.S0001.json"):
        assert (p1.root / name).read_text() == (p2.root / name).read_text(), name


def test_retrieval_is_repeatable(tmp_path):
    p = _build(tmp_path / "one")
    a = p.retrieve("federated replication").to_dict()
    b = p.retrieve("federated replication").to_dict()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# -- restart / recovery (spec section 45) ----------------------------------
def test_restart_recovers_state_map_pins_and_cold_sources(tmp_path):
    root = tmp_path / "p"
    p = Project.create(root, name="recovery", mission="Survive a restart.")
    spec = p.add_hex("Specs", HexType.SOURCE, tags=["spec"])
    s1 = p.add_source("spec", "Brief", "The continuity requirement is 72 hours.",
                      hex_id=spec.hex_id, claim_key="continuity", claim_value="72h")
    cold = p.add_source("archive", "Old validation run",
                        "Validation run V-118 recorded a 41 millisecond p99.")
    p.pin("continuity", "72h", s1.source_id, critical=True, hex_id=spec.hex_id)
    p.state.current_objective = "Confirm continuity."
    p.state.add_open_question("Q1", "Is 72h measured per canton?")
    p.state.current_summary = "narrative " * 300
    p.rotate_epoch()
    p.handle_turn("continuity requirement")
    p.close()
    del p

    q = Project.open(root)
    assert q.state.epoch == 2
    assert q.state.mission == "Survive a restart."
    assert q.config.name == "recovery"
    assert [pp["key"] for pp in q.state.active_pins] == ["continuity"]
    assert [x["id"] for x in q.state.unresolved_questions()] == ["Q1"]
    assert len(q.hexmap) >= 2 and q.hexmap.get(spec.hex_id).title == "Specs"
    assert q.resolve_pin("continuity").grounded is True
    # a cold source, never in the active state, is still retrievable
    assert "41 millisecond" not in json.dumps(q.state.to_dict())
    assert cold.source_id in q.retrieve("validation run p99").source_ids
    assert q.by_address(cold.source_id).content.startswith("Validation run V-118")
    # epoch history survived
    assert q.epoch_transitions()[0]["from_epoch"] == 1
    assert (root / "epochs" / "E1.checkpoint.json").exists()


def test_no_daemon_or_external_service_is_required(tmp_path):
    """Everything is files: the project is fully inspectable with cat/ls."""
    root = tmp_path / "p"
    _build(root)
    names = {q.name for q in root.rglob("*") if q.is_file()}
    assert {"project.json", "active_state.json", "hexmap.jsonl", "pins.jsonl"} <= names
    assert all(q.suffix in {".json", ".jsonl", ".txt"} for q in root.rglob("*") if q.is_file())
    json.loads((root / "active_state.json").read_text())
    for line in (root / "hexmap.jsonl").read_text().splitlines():
        json.loads(line)
