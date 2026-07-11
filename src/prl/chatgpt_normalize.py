"""Official ChatGPT export normalizer (M1 · D2b) — official `.zip` → the D2a shape.

The "stranger with a ChatGPT export" (M1 promise) has OpenAI's *Export Data* `.zip`,
whose ``conversations.json`` is a **message tree** (``mapping`` + ``current_node``), not the
flat ``{title, messages:[{role,text,t}]}`` D2a ingests. This module is the *only* new work
in D2b: it turns the official tree into that exact D2a shape and hands off — the seeding
path (subject key, attribution, truncation, receipts) is D2a's, reused unchanged.

Ratified normalization policy (MOHAMED, 2026-07-08 — P1–P5):

- **P1 linearization:** keep the single path root → ``current_node`` (the surviving branch).
- **P2 regenerations:** message nodes off that path are dropped, counted ``dropped.branches``.
- **P3 system/tool:** drop ``system`` nodes and any ``is_visually_hidden_from_conversation``
  node (counted ``dropped.system`` / ``dropped.hidden``); keep ``tool`` nodes as ``role=tool``.
- **P4 non-text:** string parts kept verbatim; every non-string/opaque part becomes an
  explicit typed placeholder (``[image]`` / ``[file: …]`` / ``[browsing: …]``), never dropped
  silently (counted ``placeholder.nontext``).
- **P5 reporting:** nothing dropped silently — every drop is counted *by reason* and surfaced.

Validated against the documented OpenAI export structure and synthetic fixtures; **not yet
verified against a real official OpenAI export** (follow-up validation gate if one appears).
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from .exceptions import PRLError


@dataclass
class NormalizationReport:
    """Per-import drop accounting (P5). Zero across the board on the already-normalized
    (D2a) passthrough — only the official-tree path produces drops."""

    dropped_system: int = 0
    dropped_hidden: int = 0
    dropped_branches: int = 0
    dropped_empty: int = 0
    placeholder_nontext: int = 0

    def any(self) -> bool:
        return bool(self.dropped_system or self.dropped_hidden or self.dropped_branches
                    or self.dropped_empty or self.placeholder_nontext)


# --- content rendering (P4) -------------------------------------------------


def _placeholder_for(part: dict) -> str:
    ct = str(part.get("content_type") or "")
    if "image" in ct or "asset_pointer" in part:
        return "[image]"
    if "audio" in ct:
        return "[audio]"
    if part.get("name"):
        return f"[file: {part['name']}]"
    return "[attachment]"


def _render_content(content: dict) -> tuple[str, int]:
    """Render a message ``content`` to text + a count of non-text placeholders.
    String content is kept verbatim; opaque parts become typed placeholders (never
    silently dropped)."""
    parts = content.get("parts")
    if isinstance(parts, list):
        placeholders = 0
        chunks: list[str] = []
        for p in parts:
            if isinstance(p, str):
                if p.strip():
                    chunks.append(p)
            elif isinstance(p, dict):
                chunks.append(_placeholder_for(p))
                placeholders += 1
            else:
                chunks.append("[attachment]")
                placeholders += 1
        return "\n".join(chunks), placeholders

    # No parts list: many content types (code, tether_quote, execution_output) carry a
    # flat "text" — keep it verbatim. Otherwise substitute a typed, counted placeholder.
    text = content.get("text")
    if isinstance(text, str) and text.strip():
        return text, 0

    ct = str(content.get("content_type") or "")
    if ct:
        return f"[{ct}]", 1
    return "", 0


# --- tree linearization (P1) ------------------------------------------------


def _linear_path(mapping: dict, current_node: Any) -> list[dict]:
    """The root → ``current_node`` node chain (the kept branch). Falls back to all
    message-bearing nodes in create_time order if ``current_node`` is missing/broken."""
    if isinstance(current_node, str) and current_node in mapping:
        chain: list[dict] = []
        seen: set[str] = set()
        nid: Any = current_node
        while isinstance(nid, str) and nid in mapping and nid not in seen:
            seen.add(nid)
            node = mapping[nid]
            chain.append(node)
            nid = node.get("parent")
        chain.reverse()
        return chain
    nodes = [n for n in mapping.values() if isinstance(n, dict) and n.get("message")]
    nodes.sort(key=lambda n: (n["message"].get("create_time") is None,
                              n["message"].get("create_time") or 0))
    return nodes


# --- conversation normalization ---------------------------------------------


def _normalize_conversation(conv: dict, report: NormalizationReport) -> dict:
    mapping = conv.get("mapping") or {}
    path = _linear_path(mapping, conv.get("current_node"))
    path_ids = {n.get("id") for n in path if isinstance(n, dict)}

    # P2: message-bearing nodes off the kept path are abandoned regenerations/edits.
    for nid, node in mapping.items():
        if nid not in path_ids and isinstance(node, dict) and node.get("message"):
            report.dropped_branches += 1

    messages: list[dict] = []
    for node in path:
        m = node.get("message") if isinstance(node, dict) else None
        if not m:
            continue  # the root anchor carries no message
        role = str((m.get("author") or {}).get("role") or "unknown")
        meta = m.get("metadata") or {}
        if meta.get("is_visually_hidden_from_conversation"):
            report.dropped_hidden += 1
            continue
        if role == "system":
            report.dropped_system += 1
            continue
        text, placeholders = _render_content(m.get("content") or {})
        report.placeholder_nontext += placeholders
        if not text.strip():
            report.dropped_empty += 1
            continue
        messages.append({"role": role, "text": text, "t": m.get("create_time")})

    return {
        "title": conv.get("title") or "",
        "gizmo_id": conv.get("gizmo_id"),
        "create_time": conv.get("create_time"),
        "update_time": conv.get("update_time"),
        "messages": messages,
    }


def _iter_official(data: Any) -> Iterator[tuple[str, dict]]:
    """Yield ``(conv_id, conv)`` from the official structure — a list of conversations,
    or a dict keyed by id. The id feeds the D2a ``.<id6>`` subject suffix."""
    if isinstance(data, list):
        for i, conv in enumerate(data):
            if isinstance(conv, dict):
                yield str(conv.get("conversation_id") or conv.get("id") or i), conv
    elif isinstance(data, dict):
        for cid, conv in data.items():
            if isinstance(conv, dict):
                yield str(conv.get("conversation_id") or conv.get("id") or cid), conv


def normalize_official(data: Any) -> tuple[dict, NormalizationReport]:
    """Official tree structure → ``{conv_id: {title, messages:[{role,text,t}], …}}`` (the
    D2a shape) plus the drop report."""
    report = NormalizationReport()
    out: dict[str, dict] = {}
    for conv_id, conv in _iter_official(data):
        out[conv_id] = _normalize_conversation(conv, report)
    return out, report


# --- source resolution (zip / format detection) -----------------------------


def _read_zip_json(path: Path) -> Any:
    try:
        with zipfile.ZipFile(path) as zf:
            names = [n for n in zf.namelist() if n.rsplit("/", 1)[-1] == "conversations.json"]
            if not names:
                raise PRLError(f"no conversations.json inside {path.name}")
            with zf.open(sorted(names, key=len)[0]) as fh:  # top-most conversations.json
                return json.load(fh)
    except zipfile.BadZipFile as exc:
        raise PRLError(f"{path.name} is not a valid zip: {exc}") from exc
    except ValueError as exc:
        raise PRLError(f"conversations.json in {path.name} is not valid JSON: {exc}") from exc


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PRLError(f"cannot read export at {path}: {exc}") from exc
    except ValueError as exc:
        raise PRLError(f"export is not valid JSON: {exc}") from exc


def _first_value(data: dict) -> Any:
    inner = data.get("conversations") or data.get("loose_conversations") or data
    if isinstance(inner, dict):
        return next(iter(inner.values()), None)
    if isinstance(inner, list):
        return inner[0] if inner else None
    return None


def _is_official(data: Any) -> bool:
    """Official = a conversation carries a ``mapping`` tree. Normalized (D2a) carries
    ``messages``. A list is always the official shape."""
    if isinstance(data, list):
        return any(isinstance(c, dict) and "mapping" in c for c in data[:3])
    if isinstance(data, dict):
        sample = _first_value(data)
        return isinstance(sample, dict) and "mapping" in sample
    return False


def _extract_normalized(data: Any) -> dict:
    """Tolerant extraction of the already-normalized map (same shapes D2a accepts)."""
    if isinstance(data, dict) and isinstance(data.get("conversations"), dict):
        return data["conversations"]
    if isinstance(data, dict) and isinstance(data.get("loose_conversations"), dict):
        return data["loose_conversations"]
    if isinstance(data, dict):
        return data
    raise PRLError("export must be a JSON object of conversations")


def resolve_conversations(path: str | Path) -> tuple[dict, NormalizationReport]:
    """Resolve any accepted source to the D2a shape + a drop report:
    an official ``.zip`` (or ``conversations.json``) is normalized; an already-normalized
    JSON passes through with an empty report. The seeding path stays D2a's, untouched."""
    path = Path(path)
    data = _read_zip_json(path) if path.suffix.lower() == ".zip" else _read_json(path)
    if _is_official(data):
        return normalize_official(data)
    return _extract_normalized(data), NormalizationReport()
