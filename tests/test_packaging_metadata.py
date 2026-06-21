from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_toml(path: Path) -> dict:
    try:
        import tomllib
    except ModuleNotFoundError:
        try:
            import tomli as tomllib
        except ModuleNotFoundError:
            from pip._vendor import tomli as tomllib

    return tomllib.loads(path.read_text(encoding="utf-8"))


def test_root_package_declares_dsm_primitives_runtime_dependency():
    pyproject = _load_toml(REPO_ROOT / "pyproject.toml")
    dependencies = pyproject["project"]["dependencies"]

    normalized_names = {
        dependency.split(";", 1)[0]
        .split("[", 1)[0]
        .split("<", 1)[0]
        .split(">", 1)[0]
        .split("=", 1)[0]
        .split("~", 1)[0]
        .strip()
        .lower()
        .replace("_", "-")
        for dependency in dependencies
    }

    assert "dsm-primitives" in normalized_names


def test_pypi_publish_workflow_is_manual_and_checks_dependency_resolution():
    workflow = (REPO_ROOT / ".github/workflows/publish-pypi.yml").read_text(
        encoding="utf-8"
    )

    assert "workflow_dispatch:" in workflow
    assert "release:" not in workflow
    assert "Check daryl-dsm runtime dependencies resolve from PyPI" in workflow
    assert "pip install dist/daryl_dsm-*.whl" in workflow
    assert "import dsm; import dsm_primitives" in workflow
