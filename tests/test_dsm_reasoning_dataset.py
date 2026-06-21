from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = REPO_ROOT / "datasets" / "dsm_reasoning_v0" / "validate_dataset.py"


def _load_validator():
    spec = importlib.util.spec_from_file_location(
        "dsm_reasoning_dataset_validator",
        VALIDATOR_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dsm_reasoning_dataset_v0_validates():
    validator = _load_validator()

    assert validator.main() == 0


def test_dsm_reasoning_dataset_validator_is_static_and_kernel_free():
    source = VALIDATOR_PATH.read_text(encoding="utf-8")

    forbidden_fragments = (
        "from dsm." + "core",
        "import dsm." + "core",
        "Stor" + "age",
        "core." + "storage",
    )
    for fragment in forbidden_fragments:
        assert fragment not in source
