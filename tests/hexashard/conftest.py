import sys
from pathlib import Path

# Migrated: the Core package is installed; this directory only has to be
# importable so the suite can reach `fixtures.synthetic_project`.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest

from hexashard import HexType, Project


@pytest.fixture
def proj(tmp_path) -> Project:
    return Project.create(tmp_path / "p", name="test", mission="Test mission.")


@pytest.fixture
def loaded(tmp_path):
    """A small project with a hex, two sources, and one critical pin."""
    p = Project.create(tmp_path / "p", name="test", mission="Test mission.")
    spec = p.add_hex("Specification", HexType.SOURCE, tags=["spec"])
    s1 = p.add_source(
        "spec", "Mission brief rev 1",
        "The capex ceiling for the programme is 4.2 million euro.\n\n"
        "The ceiling is contractually non-negotiable.",
        hex_id=spec.hex_id, claim_key="capex_ceiling", claim_value="4.2M EUR",
    )
    s2 = p.add_source(
        "note", "Throughput note",
        "Peak throughput observed during the morning window is 16 requests per second.",
        hex_id=spec.hex_id,
    )
    p.pin("capex_ceiling", "4.2M EUR", s1.source_id, critical=True, hex_id=spec.hex_id)
    return p, spec, s1, s2

