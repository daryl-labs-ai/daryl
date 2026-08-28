"""Deterministic synthetic long-project fixture: MERIDIAN-9.

A fictional ground-segment programme, generated from a fixed seed so the
corpus is byte-identical on every run.  It exists to exercise the
architecture, not to be realistic prose.

Structure the integration test needs (spec section 33):

    old fact ................. KELL-9 elevation, never revised
    current fact ............. downlink budget, planted in epoch 1
    superseded fact .......... handover window 90s -> 45s
    critical pins ............ downlink budget, thermal cycling limit
    decision ................. ADR-002 store-and-forward
    decision update .......... ADR-007 supersedes it with backpressure
    cold historical material . validation run V-118
    irrelevant large corpus .. ~320 facilities-management minutes

The filler vocabulary is disjoint from every signal term, and
:func:`assert_no_leakage` enforces that, so a retrieval hit on a signal
source is never an accident of the filler.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path

SEED = 20260827
FILLER_SOURCES = 320
FILLER_PARAGRAPHS = 6

# --------------------------------------------------------------------------
# Signal material
# --------------------------------------------------------------------------

#: Terms that must never appear in filler.
SIGNAL_TERMS = [
    "downlink", "gigabit", "handover", "kell-9", "elevation", "thermal",
    "cycling", "v-118", "p99", "backpressure", "store-and-forward",
    "telemetry", "apogee", "adr-002", "adr-007", "sidereal", "raster",
]


@dataclass(frozen=True)
class Planted:
    key: str
    source_type: str
    title: str
    content: str
    claim_key: str | None = None
    claim_value: str | None = None
    status: str = "CURRENT"
    tags: tuple[str, ...] = ()


PLANTED: tuple[Planted, ...] = (
    Planted(
        key="downlink_budget",
        source_type="spec",
        title="MERIDIAN-9 telemetry brief rev 1.0",
        claim_key="downlink_budget",
        claim_value="4.7 Gb/pass",
        tags=("brief", "binding"),
        content=(
            "The MERIDIAN-9 telemetry downlink budget is 4.7 gigabits per pass.\n\n"
            "This figure is binding on every ground station in the network and may "
            "not be exceeded without a formal waiver from the programme board.\n\n"
            "The budget was derived from the apogee dwell time and the sidereal "
            "tracking rate of the primary dish."
        ),
    ),
    Planted(
        key="thermal_limit",
        source_type="constraint",
        title="Thermal cycling constraint TC-11",
        claim_key="thermal_cycling_limit",
        claim_value="180 cycles per annum",
        tags=("constraint", "binding"),
        content=(
            "The thermal cycling limit for the dish drive assembly is 180 cycles "
            "per annum.\n\nExceeding the thermal cycling limit voids the drive "
            "assembly warranty and requires a full bearing inspection."
        ),
    ),
    Planted(
        key="handover_v1",
        source_type="spec",
        title="Ground station handover procedure rev 1",
        claim_key="handover_window",
        claim_value="90 seconds",
        tags=("procedure",),
        content=(
            "The ground station handover window is 90 seconds.\n\n"
            "During the handover window both the outgoing and incoming station "
            "hold a lock on the spacecraft telemetry stream."
        ),
    ),
    Planted(
        key="handover_v2",
        source_type="spec",
        title="Ground station handover procedure rev 2",
        claim_key="handover_window",
        claim_value="45 seconds",
        tags=("procedure",),
        content=(
            "The ground station handover window is 45 seconds following the "
            "2033 antenna refit.\n\nThe shortened handover window was validated "
            "against the sidereal tracking rate of the refitted dishes."
        ),
    ),
    Planted(
        key="kell9_elevation",
        source_type="reference",
        title="Site register: KELL-9",
        tags=("site",),
        content=(
            "Site KELL-9 sits at an elevation of 2410 metres above sea level.\n\n"
            "KELL-9 is the only site in the network above the 2000 metre line and "
            "carries a separate lightning protection schedule."
        ),
    ),
    Planted(
        key="adr002",
        source_type="decision",
        title="ADR-002 telemetry buffering",
        tags=("adr", "decision"),
        content=(
            "ADR-002. Decision: adopt store-and-forward buffering at each ground "
            "station for the telemetry stream.\n\n"
            "Rationale: store-and-forward tolerates a lossy backhaul without "
            "dropping frames. Rejected alternative: direct streaming, on the "
            "grounds of backhaul reliability."
        ),
    ),
    Planted(
        key="adr007",
        source_type="decision",
        title="ADR-007 telemetry buffering, revised",
        tags=("adr", "decision"),
        content=(
            "ADR-007. Decision: replace store-and-forward buffering with streaming "
            "under backpressure.\n\nThe backhaul upgrade completed in 2033 removed "
            "the reliability argument that justified ADR-002. Streaming with "
            "backpressure reduces end-to-end latency by roughly two thirds."
        ),
    ),
    Planted(
        key="validation_v118",
        source_type="test",
        title="Validation run V-118",
        tags=("test", "archive"),
        content=(
            "Validation run V-118 recorded a p99 frame latency of 41 milliseconds "
            "across the whole network.\n\nV-118 ran before the antenna refit and is "
            "retained for historical comparison only."
        ),
    ),
    Planted(
        key="draft_downlink",
        source_type="draft",
        title="Draft downlink revision (unapproved)",
        status="DRAFT",
        tags=("draft",),
        content=(
            "Working draft. The telemetry downlink budget downlink budget may be "
            "raised to 6.1 gigabits per pass. Downlink budget downlink telemetry "
            "gigabits per pass downlink budget. This draft has not been reviewed."
        ),
    ),
    Planted(
        key="unverified_thermal",
        source_type="note",
        title="Unverified thermal note from the vendor call",
        status="UNVERIFIED",
        tags=("note",),
        content=(
            "Unverified. Someone on the vendor call said the thermal cycling limit "
            "thermal cycling limit is 240 cycles per annum. Thermal cycling limit "
            "cycles per annum thermal cycling. Nobody has confirmed this."
        ),
    ),
    Planted(
        key="raster_note",
        source_type="reference",
        title="Raster scan calibration note",
        tags=("calibration",),
        content=(
            "The raster scan calibration is repeated every 400 sidereal hours.\n\n"
            "Raster calibration drift beyond 0.02 degrees requires a manual "
            "re-point of the dish."
        ),
    ),
    Planted(
        key="apogee_note",
        source_type="reference",
        title="Apogee dwell reference",
        tags=("orbit",),
        content=(
            "Apogee dwell time for the MERIDIAN-9 orbit is 11.4 minutes.\n\n"
            "Apogee dwell is the limiting factor on per-pass downlink volume."
        ),
    ),
)

# --------------------------------------------------------------------------
# Filler material -- a large, boring, irrelevant corpus
# --------------------------------------------------------------------------

_SUBJECTS = ["the catering contract", "the visitor badge printer", "the car park barrier",
             "the stationery order", "the courier account", "the carpet replacement",
             "the water cooler service", "the lighting refit", "the window cleaning rota",
             "the vending machine", "the bike shelter", "the waste collection"]
_VERBS = ["was reviewed", "was renewed", "was deferred", "was escalated",
          "was noted without objection", "was returned to the supplier",
          "was reconciled against the ledger", "was queried by finance"]
_WHO = ["facilities", "the office manager", "the finance clerk", "the reception desk",
        "the building owner", "the cleaning supervisor", "the procurement assistant"]
_TAIL = ["No further action was recorded.", "A follow-up was placed on the standing agenda.",
         "The item was closed at the same meeting.", "Costs were within the annual allowance.",
         "The supplier acknowledged receipt.", "The matter was minuted for completeness."]


def _filler_paragraph(rng: random.Random, ref: str, n: int) -> str:
    return (
        f"Item {ref}-{n:02d}. {rng.choice(_SUBJECTS).capitalize()} "
        f"{rng.choice(_VERBS)} by {rng.choice(_WHO)}. {rng.choice(_TAIL)} "
        f"{rng.choice(_SUBJECTS).capitalize()} {rng.choice(_VERBS)} and "
        f"{rng.choice(_WHO)} confirmed the position. {rng.choice(_TAIL)} "
        f"A revised figure of {rng.randrange(200, 9000)} was entered against "
        f"cost code FM-{rng.randrange(1000, 9999)}. {rng.choice(_TAIL)}"
    )


def filler_sources(count: int = FILLER_SOURCES) -> list[tuple[str, str]]:
    """``(title, content)`` pairs.  Deterministic for a fixed seed."""
    rng = random.Random(SEED)
    out = []
    for i in range(count):
        ref = f"FM{i:04d}"
        body = "\n\n".join(_filler_paragraph(rng, ref, n) for n in range(FILLER_PARAGRAPHS))
        out.append((f"Facilities minutes {ref}", body))
    return out


def assert_no_leakage(sources: list[tuple[str, str]]) -> None:
    """Guarantee the irrelevant corpus is genuinely irrelevant."""
    for title, body in sources:
        blob = f"{title}\n{body}".lower()
        for term in SIGNAL_TERMS:
            if term in blob:
                raise AssertionError(f"filler leaked signal term {term!r} in {title}")


# --------------------------------------------------------------------------
# Query bank
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Query:
    text: str
    expect_key: str
    kind: str = "retrieval"          # retrieval | authority | historical
    forbid_keys: tuple[str, ...] = ()


QUERIES: tuple[Query, ...] = (
    Query("what is the telemetry downlink budget per pass", "downlink_budget",
          "authority", forbid_keys=("draft_downlink",)),
    Query("what is the thermal cycling limit for the dish drive", "thermal_limit",
          "authority", forbid_keys=("unverified_thermal",)),
    Query("how long is the ground station handover window", "handover_v2",
          "authority", forbid_keys=("handover_v1",)),
    Query("what elevation is site KELL-9", "kell9_elevation"),
    Query("which buffering approach did we adopt for telemetry", "adr007",
          "authority", forbid_keys=("adr002",)),
    Query("what p99 frame latency did validation run V-118 record", "validation_v118"),
    Query("how often is the raster scan calibration repeated", "raster_note"),
    Query("what is the apogee dwell time", "apogee_note"),
    Query("what was the original handover window before the refit", "handover_v1",
          "historical"),
    Query("what did ADR-002 originally decide about buffering", "adr002", "historical"),
)


# --------------------------------------------------------------------------
# Freezing
# --------------------------------------------------------------------------

LOCK_PATH = Path(__file__).with_name("FIXTURE_LOCK.json")


def fingerprint() -> dict:
    h = hashlib.sha256()
    for p in PLANTED:
        h.update(f"{p.key}|{p.title}|{p.content}|{p.status}".encode())
    for title, body in filler_sources():
        h.update(f"{title}|{body}".encode())
    for q in QUERIES:
        h.update(f"{q.text}|{q.expect_key}|{q.kind}".encode())
    return {
        "seed": SEED,
        "planted": len(PLANTED),
        "filler": FILLER_SOURCES,
        "queries": len(QUERIES),
        "sha256": h.hexdigest(),
    }


def freeze() -> dict:
    fp = fingerprint()
    LOCK_PATH.write_text(json.dumps(fp, indent=2, sort_keys=True) + "\n")
    return fp


def check_frozen() -> dict:
    if not LOCK_PATH.exists():
        return freeze()
    locked = json.loads(LOCK_PATH.read_text())
    current = fingerprint()
    if locked != current:
        raise AssertionError(
            "the fixture changed after it was frozen; results are not comparable\n"
            f"locked : {locked}\ncurrent: {current}"
        )
    return locked


if __name__ == "__main__":
    print(json.dumps(freeze(), indent=2))
