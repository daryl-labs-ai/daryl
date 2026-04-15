"""Causal linking adapter — never raises."""
from __future__ import annotations

import copy

from ...dsm.ulid import is_valid_ulid


class CausalAdapter:
    def maybe_apply_causal_link(self, parent_event_id: str | None, event: dict) -> dict | None:
        try:
            if parent_event_id is None:
                return None
            if not is_valid_ulid(parent_event_id):
                return None
            new_event = copy.deepcopy(event)
            links = new_event.setdefault("links", {"parent_event_id": None, "causal_refs": []})
            refs = list(links.get("causal_refs") or [])
            if parent_event_id in refs:
                return None
            refs.append(parent_event_id)
            if len(refs) > 8:
                return None
            links["causal_refs"] = refs
            new_event["links"] = links
            return new_event
        except Exception:
            return None
