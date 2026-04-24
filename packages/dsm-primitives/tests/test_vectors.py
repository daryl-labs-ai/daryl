"""Reference vector tests.

Loads packages/dsm-primitives/tests/hash_vectors_v1.json and verifies
that each input dict produces the expected v1 hash.

Per ADR-0002, these vectors are IMMUTABLE. If this test fails after a
code change, the code is wrong — do NOT update the vectors file.
"""

import json
from pathlib import Path

import pytest

from dsm_primitives import hash_canonical

VECTORS_PATH = Path(__file__).parent / "hash_vectors_v1.json"


def _load_vectors():
    with open(VECTORS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("vector", _load_vectors())
def test_reference_vector(vector):
    name = vector["name"]
    input_data = vector["input"]
    expected = vector["expected_hash"]
    actual = hash_canonical(input_data)
    assert actual == expected, (
        f"Vector '{name}' hash mismatch.\n"
        f"  input:    {input_data!r}\n"
        f"  expected: {expected}\n"
        f"  actual:   {actual}"
    )
