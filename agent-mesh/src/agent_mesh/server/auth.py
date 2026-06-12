"""API-key authentication for sensitive endpoints (P0 / C2).

The mesh API drives real, billable LLM calls and writes to an append-only log.
Before this guard every endpoint was reachable unauthenticated on 0.0.0.0.

Policy:
  * If ``config.api_key`` is set, sensitive endpoints require a matching key,
    supplied as ``X-API-Key: <key>`` or ``Authorization: Bearer <key>``.
    Comparison is constant-time.
  * If no key is configured, enforcement is DISABLED (development/tests only).
    Production refuses to start without a key — see app.create_app().
"""
from __future__ import annotations

import hmac

from fastapi import HTTPException, Request


def _provided_key(request: Request) -> str | None:
    key = request.headers.get("x-api-key")
    if key:
        return key.strip()
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


async def require_api_key(request: Request) -> None:
    """FastAPI dependency: enforce the API key when one is configured."""
    cfg = request.app.state.mesh.config
    expected = getattr(cfg, "api_key", None)
    if not expected:
        # No key configured → enforcement off (dev/test). Production is blocked
        # from reaching this state by create_app().
        return
    provided = _provided_key(request)
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="missing_or_invalid_api_key")
