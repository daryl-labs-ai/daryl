# agent-mesh V0

FastAPI-based coordination server for a mesh of agents. Exposes HTTP endpoints to
register agents, create missions and tasks, and submit signed task results. All
state-changing actions go through an append-only DSM writer (`events.jsonl`) and
are indexed in SQLite.

## Layout

```
agent-mesh/
  src/agent_mesh/
    config.py            # env loader (python-dotenv)
    models/              # Pydantic domain models (Agent, Task, Contribution)
    dsm/                 # envelope builder, ULID helpers, event factories, DSMWriter
    index/db.py          # aiosqlite WAL-mode index
    registry/            # in-memory AgentRegistry
    scheduler/           # round-robin TaskScheduler
    adapters/daryl_adapter/
      signing.py         # Ed25519 (PyNaCl), SigningAdapter
      attestation.py     # local attestation stub
      causal.py          # CausalAdapter — never raises
      exchange.py        # ExchangeAdapter — receipts
    server/              # FastAPI app, routes, schemas, AppState
  tests/                 # pytest + pytest-asyncio + httpx
```

## Invariants

- `DSMWriter.write()` is the only event writer.
- `event_id` is a server-generated ULID.
- `causal_refs`: max 8, unique, all valid ULIDs; else ValueError.
- Rule A: receipts are only issued after a successful DSM write.
- Rule B: `CausalAdapter.maybe_apply_causal_link` returns None on any failure, never raises.
- `server_recovered` is written at boot if the previous lifecycle event is `server_started` with no matching `server_stopped`.
- HTTP codes: 201 on create, 404 not found, 409 duplicate, 422 validation/signature, 503 no agent, 500 internal. Never 400.

## Run

```
cd agent-mesh
pip install -e ".[dev]"
python -m pytest tests/ -v
uvicorn agent_mesh.server.app:create_app --factory --host 127.0.0.1 --port 8000
```
