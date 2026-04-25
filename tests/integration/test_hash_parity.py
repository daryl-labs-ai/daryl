"""Cross-package parity test (ADR-0002).

Asserts that all sources of canonical hashing — daryl-dsm, agent-mesh,
and dsm-primitives directly — produce byte-identical hashes for shared
fixtures.

This is the test that catches Unicode divergence, schema drift, or any
silent re-implementation of canonical logic in either consumer.

If this test fails, one of three things has happened:
1. dsm-primitives spec changed without coordinating consumers
2. daryl-dsm or agent-mesh re-introduced custom canonical logic
3. The fixture was modified (which is itself a breaking schema change)
"""

import sys
from pathlib import Path

# CANONICAL_ENTRY_V1 lives in dsm-primitives tests/fixtures/. Add the
# package's tests dir to sys.path so we can import the fixture from
# outside the installed package surface.
_PKG_TESTS = Path(__file__).resolve().parents[2] / \
    "packages" / "dsm-primitives" / "tests"
if str(_PKG_TESTS) not in sys.path:
    sys.path.insert(0, str(_PKG_TESTS))

from fixtures.canonical_entry import CANONICAL_ENTRY_V1  # noqa: E402

from dsm_primitives import hash_canonical                # noqa: E402
from agent_mesh.adapters.daryl_adapter.signing import \
    compute_content_hash                                  # noqa: E402


def test_dsm_primitives_hash_well_formed():
    """dsm_primitives is the spec source — sanity check on output shape."""
    h = hash_canonical(CANONICAL_ENTRY_V1)
    assert h.startswith("v1:")
    assert len(h) == 67


def test_agent_mesh_hash_matches_primitives():
    """agent-mesh's compute_content_hash must produce the same hash
    as dsm_primitives.hash_canonical for the shared fixture."""
    mesh_hash = compute_content_hash(CANONICAL_ENTRY_V1)
    primitives_hash = hash_canonical(CANONICAL_ENTRY_V1)
    assert mesh_hash == primitives_hash, \
        f"divergence: mesh={mesh_hash}, primitives={primitives_hash}"


def test_unicode_convergence_audit_v4_section_6_3():
    """The bug that motivated ADR-0002 (audit V4 §6.3): 'café' must
    produce the same hash on both sides post-migration."""
    fixture = {"name": "café"}

    h_primitives = hash_canonical(fixture)
    h_mesh = compute_content_hash(fixture)

    assert h_primitives == h_mesh, \
        f"Unicode divergence resurfaced: primitives={h_primitives}, mesh={h_mesh}"


def test_emoji_convergence():
    """Sanity: emoji input also converges."""
    fixture = {"reaction": "🎉"}
    h_primitives = hash_canonical(fixture)
    h_mesh = compute_content_hash(fixture)
    assert h_primitives == h_mesh


def test_nested_dict_convergence():
    """Nested structures with sort_keys behavior."""
    fixture = {
        "outer": {"z": 1, "a": 2},
        "items": [1, "two", 3.0, None],
    }
    h_primitives = hash_canonical(fixture)
    h_mesh = compute_content_hash(fixture)
    assert h_primitives == h_mesh


def test_worker_server_path_convergence():
    """Critical: the path 'worker signs canonical bytes, server recomputes
    hash from same payload' produces matching hashes byte-for-byte.

    This is the path that broke before V4-A.3 (worker = ensure_ascii=False,
    server = ensure_ascii=True). Locking it down with a test prevents
    regression."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent-mesh"))
    from workers.protocol import _canonical, _sha256

    payload = {"task_id": "t-001", "result": "café au lait", "score": 0.95}

    # Worker side: canonical bytes → "v1:" + sha256 hex
    worker_hash = _sha256(_canonical(payload))

    # Server side: compute_content_hash → hash_canonical
    server_hash = compute_content_hash(payload)

    assert worker_hash == server_hash, \
        f"worker/server divergence: worker={worker_hash}, server={server_hash}"
