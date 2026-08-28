"""Canonical Core identity.

HexaShard Core v0.1 was frozen as an immutable archive before any of the
downstream experiments (cross-audit, paraphrase, Z-depth, spatial, LIVE 001,
LIVE 001-L, Adapter v0.1) were run.  Every one of those labs ran against a
byte-identical copy of that archive.

On migration into this repository the Core modules were copied *byte for byte*;
only their location changed.  The per-file digests below are the digests of the
frozen archive, so this module still answers the same question it answered in
the lab: is the Core running here the Core the evidence was produced against?

The Adapter never writes inside the Core package.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

#: SHA-256 of the frozen distribution archive `hexashard_core_v01_claude.tar.gz`.
#: Recorded before Adapter v0.1 was written and independently re-verified at the
#: pre-GitHub gate.
ARCHIVE_SHA256 = "268f0f08362982c2c6e85d5672d9f2e9efcc34f2e3306d40f5ee23e3763ca999"

#: Tree digest of the frozen Core *distribution* (27 files: package, tests,
#: fixtures, docs).  Retained for provenance only — the distribution layout does
#: not survive migration, the module bytes do.
FROZEN_DISTRIBUTION_TREE_SHA256 = (
    "2bbc2d4fc6afa4298b2528f40825f8e1a81271621766f213344396eb5063e5c3"
)

#: Per-module SHA-256 of the frozen Core package.  These are the bytes the
#: published evidence was produced against.
FROZEN_CORE_MODULES: dict[str, str] = {
    "__init__.py": "92a1a3582093b3d6c5612b2cb5d3cf4e43ebbe2f32ad93dd463d97089665ad43",
    "context.py": "af4f13280bad5af350c1d3b87be7ee325e76d3571362c155b1c85c37bd49fcae",
    "ids.py": "84fcbbd17b18f5bb0412b2c8a43c739c9ccdd1fd732b844c409c35fc505814c4",
    "metrics.py": "ff9867adb456b9ea24f53e631973dc83a49673385f41f2173a164ce4b119c57b",
    "models.py": "e695bc105aaed02a82bc0af1a2a2f68c562602f256dac53a6dd2bf0a68933c2a",
    "pins.py": "eae9fcd1dec550cff96821bf318b6ec2d2bbaccd372be643c9fdfef07966cc9f",
    "project.py": "ddccda801fdaab2bb1ccc349d22a12d393a0947c5515850672ca1d9584048acf",
    "providers.py": "70491fd864cf802dc5c2137e71ba78e2129a4cca183369346c83701b4d2c8599",
    "retrieval.py": "2961e1cb51d883bd8f05e6359f5fdfac116c7d84bd9fabc82ff539dfb62bc649",
    "store.py": "4922d905c54dbf59d595a25c305428262158efa32613ea860e3b4b77a472e8aa",
    "tokens.py": "2acbc54990ef7be7566e190af083159e2add58c9644722aa6e73d550df349589",
    "trust.py": "3595658a80b31c0e154922749c8150f5bec58fbecabaaac2afdc3fdb231ceb34",
}

#: Core suite result recorded before Adapter v0.1 was written.
CORE_TESTS_BEFORE = {"passed": 68, "command": "pytest tests/hexashard"}


def core_root() -> Path:
    """Directory of the installed Core package."""
    import hexashard

    return Path(hexashard.__file__).resolve().parent


def core_module_digests() -> dict[str, str]:
    root = core_root()
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.glob("*.py"))
    }


def assert_core_unmodified() -> dict[str, str]:
    """Raise unless the installed Core is byte-identical to the frozen v0.1."""
    got = core_module_digests()
    if got != FROZEN_CORE_MODULES:
        missing = sorted(set(FROZEN_CORE_MODULES) - set(got))
        added = sorted(set(got) - set(FROZEN_CORE_MODULES))
        changed = sorted(
            n for n in set(got) & set(FROZEN_CORE_MODULES)
            if got[n] != FROZEN_CORE_MODULES[n]
        )
        raise RuntimeError(
            "HexaShard Core is not the frozen v0.1 build: "
            f"changed={changed} missing={missing} added={added}"
        )
    return got
