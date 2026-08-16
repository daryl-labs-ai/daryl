"""Regression guard for adversarially falsified claim wording.

An independent adversarial audit ran five experiments against DSM. All five
falsified a claim the documentation made; the hash chain itself held in every
one. The wording was then corrected. This guard keeps the specific falsified
formulations from creeping back.

Deliberately narrow. This is NOT a general lexical linter — words like "prove"
are perfectly correct in a sentence about what DSM does *not* prove, and the
threat model and disclaimers must stay exactly as blunt as they are. Only exact
phrases that were shown to be false are banned, each with the experiment that
falsified it.
"""

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]

# Surfaces that make claims to a reader or a calling agent.
CLAIM_SURFACES = [
    "README.md",
    "docs/CONSUMPTION_LAYER.md",
    "docs/DEMO_GUIDE.md",
    "demo/README.md",
    "demo/demo_end_to_end.py",
    "src/dsm/cli.py",
    "src/dsm/receipts.py",
    "src/dsm/attestation.py",
    "src/dsm/exchange.py",
    "src/dsm/memory/report.py",
]

# (banned phrase, why it is false) — matched case-insensitively as a substring.
BANNED_CLAIMS = [
    (
        "what the agent saw",
        "Experiment 4: receipts hash caller-supplied bytes, not what the agent "
        "observed. A substituted summary verifies INTACT.",
    ),
    (
        "but what it SAW",
        "Experiment 4: same capture boundary, receipts.py module docstring.",
    ),
    (
        "full deterministic replay",
        "Experiment 1: replay is deterministic over RECORDED events; it says "
        "nothing about activity never captured.",
    ),
    (
        "no silent data loss",
        "Experiment 1: DSM cannot detect acts that never crossed its boundary.",
    ),
    (
        "crash detection",
        "Experiment 1: an intent without a recorded result has an UNKNOWN "
        "cause — crash, abandonment, and in-flight are indistinguishable.",
    ),
    (
        "proof of work",
        "Experiment 4: a receipt binds an entry hash to a shard state; it is "
        "not evidence that work was performed.",
    ),
    (
        "proves authorship",
        "Signing is optional. An unsigned append carries no authorship binding.",
    ),
    (
        "compliance-ready",
        "Not assertable by a library; depends on jurisdiction and process.",
    ),
    (
        "every action, every decision",
        "Experiment 1: coverage is limited to what was recorded through DSM.",
    ),
]

# Phrases whose ABSENCE would mean an honest limitation was dropped.
# Each maps to the experiment it keeps on the record.
REQUIRED_DISCLOSURES = {
    "README.md": [
        # Experiment 1 — completeness of uncaptured activity
        "recorded through DSM",
        "Completeness of real activity",
        # Experiment 4 — proof of actually-observed input
        "what the model actually consumed",
        # Experiment 5 — declared provenance vs real investigation path
        "is the real investigation path",
        # Source-ref integrity v0 — existence is not relevance
        "RESOLVED",
    ],
}


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


@pytest.mark.parametrize("rel_path", CLAIM_SURFACES)
def test_claim_surface_has_no_falsified_wording(rel_path):
    haystack = _read(rel_path).lower()
    offenders = [
        f"{phrase!r} — {reason}"
        for phrase, reason in BANNED_CLAIMS
        if phrase.lower() in haystack
    ]
    assert not offenders, (
        f"{rel_path} reintroduces adversarially falsified wording:\n  "
        + "\n  ".join(offenders)
    )


@pytest.mark.parametrize("rel_path", sorted(REQUIRED_DISCLOSURES))
def test_claim_surface_keeps_its_honest_limitations(rel_path):
    haystack = _read(rel_path)
    missing = [
        phrase
        for phrase in REQUIRED_DISCLOSURES[rel_path]
        if phrase not in haystack
    ]
    assert not missing, (
        f"{rel_path} dropped disclosures that adversarial testing required: "
        f"{missing}"
    )


def test_list_shards_does_not_report_a_pin_as_verified():
    """`integrity_status='verified'` is emitted whenever a pin file exists.

    No chain verification runs to produce it, so the CLI must not present it
    as `verified`. The kernel field is unchanged; only the label is honest.
    """
    from dsm.cli import _shard_pin_label

    assert _shard_pin_label("verified") == "pin_present"
    assert _shard_pin_label("unknown") == "no_pin"
    # Unrecognised values pass through rather than being silently relabelled.
    assert _shard_pin_label("corrupted") == "corrupted"

    cli_source = _read("src/dsm/cli.py")
    assert "s.integrity_status}" not in cli_source, (
        "list-shards must print the pin label, not the raw kernel field"
    )
