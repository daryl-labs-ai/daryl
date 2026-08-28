"""Deterministic, human-readable addresses.

Every addressable thing in a HexaShard project gets a stable, sortable,
greppable string address.  Addresses carry project identity, epoch (for
hexes) and a zero-padded sequence -- nothing else.  In particular they encode
no geometry and no neighbour relationships.

    hex       P1.E1.H001
    source    P1.S0001
    pin       P1.K001
    fragment  P1.S0001#c003

An immutable machine UUID is derived from the address with UUID5 over a fixed
namespace, so it is stable across runs and machines without a random source.
"""

from __future__ import annotations

import re
import uuid

#: Fixed namespace so machine UUIDs are reproducible.
ADDRESS_NAMESPACE = uuid.UUID("0f3a6c52-1d47-5c8b-9a10-b7e2f4c60d31")

_HEX_RE = re.compile(r"^(?P<project>[A-Za-z0-9]+)\.E(?P<epoch>\d+)\.H(?P<seq>\d+)$")
_SOURCE_RE = re.compile(r"^(?P<project>[A-Za-z0-9]+)\.S(?P<seq>\d+)$")
_PROJECT_RE = re.compile(r"^[A-Za-z0-9]+$")


def validate_project_prefix(prefix: str) -> str:
    if not _PROJECT_RE.match(prefix):
        raise ValueError(f"project prefix must be alphanumeric, got {prefix!r}")
    return prefix


def hex_address(project_prefix: str, epoch: int, seq: int) -> str:
    return f"{project_prefix}.E{epoch}.H{seq:03d}"


def source_address(project_prefix: str, seq: int) -> str:
    return f"{project_prefix}.S{seq:04d}"


def pin_address(project_prefix: str, seq: int) -> str:
    return f"{project_prefix}.K{seq:03d}"


def fragment_address(source_id: str, index: int) -> str:
    return f"{source_id}#c{index:03d}"


def source_of_fragment(fragment_id: str) -> str:
    return fragment_id.split("#", 1)[0]


def machine_uuid(address: str) -> str:
    """Immutable machine identifier derived from the human address."""
    return str(uuid.uuid5(ADDRESS_NAMESPACE, address))


def parse_hex_address(address: str) -> tuple[str, int, int]:
    m = _HEX_RE.match(address)
    if not m:
        raise ValueError(f"not a hex address: {address!r}")
    return m["project"], int(m["epoch"]), int(m["seq"])


def parse_source_address(address: str) -> tuple[str, int]:
    m = _SOURCE_RE.match(address)
    if not m:
        raise ValueError(f"not a source address: {address!r}")
    return m["project"], int(m["seq"])
