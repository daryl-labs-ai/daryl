"""Deterministic smoke corpus. Store target >= 100k Core estimator tokens."""

from __future__ import annotations

from pathlib import Path

from hexashard import HexType, Project, SourceStatus
from hexashard.tokens import estimate_tokens

from hexashard_adapter import AdapterConfig, HexaShardAdapter, MockChatProvider

FILLER_WORDS = (
    "cafeteria", "kettle", "badge", "lobby", "parking", "minutes", "facilities",
    "corridor", "lockbox", "clipboard", "shift", "roster", "canopy", "loading",
    "dock", "pallet", "radio", "headset", "walkway", "mezzanine",
)

PLANTS = {
    "beaconel": {
        "hex": "architecture",
        "title": "Site geometry note SG-01",
        "content": (
            "The primary dish at the north pad has a BEACONEL elevation of 41.2 degrees. "
            "This figure is the surveyed geometric constraint for the ORION-GATE feed."
        ),
        "claim_key": "beacon_elevation",
        "claim_value": "41.2",
    },
    "gatebudget_v1": {
        "hex": "sources",
        "title": "ORION-GATE budget brief rev 1",
        "content": "The GATEBUDGET daily cap is 4.0TB per site in rev 1.",
        "claim_key": "gate_budget",
        "claim_value": "4.0TB",
    },
    "gatebudget_v2": {
        "hex": "sources",
        "title": "ORION-GATE budget brief rev 2",
        "content": (
            "The GATEBUDGET daily cap is 6.1TB per site. Rev 2 supersedes rev 1. "
            "The previous 4.0TB figure is historical only."
        ),
        "claim_key": "gate_budget",
        "claim_value": "6.1TB",
    },
    "adr_v1": {
        "hex": "decisions",
        "title": "ADR-OG-01 queue-first",
        "content": "ADR-OG-01 decides the ingest path is QUEUEFIRST.",
        "claim_key": "adr_og_01",
        "claim_value": "QUEUEFIRST",
    },
    "adr_v2": {
        "hex": "decisions",
        "title": "ADR-OG-01 credit-backpressure",
        "content": "ADR-OG-01 is superseded. The current ingest path is CREDITBP.",
        "claim_key": "adr_og_01",
        "claim_value": "CREDITBP",
    },
    "bug4412": {
        "hex": "bugs",
        "title": "BUG-4412 heap starve",
        "content": (
            "BUG-4412: the ingest worker dies with HEAPSTARVE after six hours "
            "when the credit window is left at the default."
        ),
        "claim_key": "bug4412",
        "claim_value": "HEAPSTARVE",
    },
}


def _filler(n: int) -> str:
    words = [FILLER_WORDS[(n * 19 + i * 3) % len(FILLER_WORDS)] for i in range(900)]
    return f"Facilities minutes {n}. " + " ".join(words)


def store_tokens(project: Project) -> int:
    return sum(estimate_tokens(s.content) for s in project.sources.all())


def build_smoke_project(root: str | Path, *, min_store: int = 100_000) -> HexaShardAdapter:
    cfg = AdapterConfig(provider="mock", model_context_budget=8000, retrieval_budget=1500)
    adapter = HexaShardAdapter.create(
        root,
        name="ORION-GATE-SMOKE",
        mission="Deliver the ORION-GATE ground ingest path without HEXMESH routing.",
        config=cfg,
        provider=MockChatProvider(),
        active_context_budget_tokens=6000,
    )
    p = adapter.project
    hex_ids = {}
    with p.bulk():
        for key in ("architecture", "sources", "decisions", "bugs", "facilities"):
            hex_ids[key] = p.add_hex(key, HexType.SOURCE, tags=[key]).hex_id

        def plant(name: str):
            meta = PLANTS[name]
            return p.add_source(
                "spec", meta["title"], meta["content"],
                hex_id=hex_ids[meta["hex"]],
                status=SourceStatus.CURRENT,
                tags=[meta["hex"], name],
                claim_key=meta["claim_key"],
                claim_value=meta["claim_value"],
            )

        beacon = plant("beaconel")
        gb1 = plant("gatebudget_v1")
        adr1 = plant("adr_v1")
        bug = plant("bug4412")
        p.pin("BEACONEL", "41.2", beacon.source_id, critical=True, hex_id=hex_ids["architecture"])
        p.pin("GATEBUDGET", "4.0TB", gb1.source_id, critical=True, hex_id=hex_ids["sources"])
        p.pin("ADR-OG-01", "QUEUEFIRST", adr1.source_id, critical=True, hex_id=hex_ids["decisions"])

        n = 0
        while store_tokens(p) < min_store:
            n += 1
            body = _filler(n)
            hx = ("architecture", "sources", "decisions", "bugs", "facilities")[n % 5]
            p.add_source(
                "minutes", f"Facilities minutes {n}", body,
                hex_id=hex_ids[hx], tags=["facilities", hx],
            )

        gb2 = plant("gatebudget_v2")
        adr2 = plant("adr_v2")
        p.supersede(gb1.source_id, gb2.source_id)
        p.supersede(adr1.source_id, adr2.source_id)
        p.pin("GATEBUDGET", "6.1TB", gb2.source_id, critical=True, hex_id=hex_ids["sources"])
        p.pin("ADR-OG-01", "CREDITBP", adr2.source_id, critical=True, hex_id=hex_ids["decisions"])
        p.state.current_objective = "Ship CREDITBP ingest without HEXMESH."
        adapter._ids = {  # type: ignore[attr-defined]
            "beacon": beacon.source_id,
            "gb1": gb1.source_id,
            "gb2": gb2.source_id,
            "adr1": adr1.source_id,
            "adr2": adr2.source_id,
            "bug": bug.source_id,
            "hexes": hex_ids,
        }
    adapter.close()
    return HexaShardAdapter.open(root, config=cfg, provider=MockChatProvider())
