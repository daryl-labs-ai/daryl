"""FastAPI app factory."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ..adapters.daryl_adapter import CausalAdapter, ExchangeAdapter, SigningAdapter
from ..config import Config
from ..dsm import factory as ev_factory
from ..dsm.writer import DSMWriter
from ..index.db import IndexDB
from ..registry.agent_registry import AgentRegistry
from ..scheduler.task_scheduler import TaskScheduler
from .state import AppState


def _detect_recovery(writer: DSMWriter) -> bool:
    """Return True if we crashed before last shutdown."""
    events = writer.read_all()
    last_lifecycle = None
    for e in events:
        if e.get("scope_id") == "system.server.lifecycle":
            last_lifecycle = e.get("event_type")
    return last_lifecycle == "server_started"


def create_app(config: Config | None = None) -> FastAPI:
    cfg = config or Config.load()
    logging.basicConfig(level=getattr(logging, cfg.log_level.upper(), logging.INFO))
    log = logging.getLogger("agent_mesh")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        writer = DSMWriter(cfg.data_dir)
        index_db = IndexDB(cfg.data_dir)
        await index_db.init()
        state = AppState(
            config=cfg,
            index_db=index_db,
            registry=AgentRegistry(),
            signing_adapter=SigningAdapter(),
            causal_adapter=CausalAdapter(),
            exchange_adapter=ExchangeAdapter(),
            dsm_writer=writer,
            scheduler=TaskScheduler(),
        )
        app.state.mesh = state

        recovered = _detect_recovery(writer)
        if recovered:
            ev = ev_factory.server_recovered(cfg.server_id, {"server_id": cfg.server_id})
            log.info("server_recovered detected")
        else:
            ev = ev_factory.server_started(cfg.server_id, {"server_id": cfg.server_id})
            log.info("server_started")
        written = writer.write(ev)
        if written is not None:
            await index_db.index_event(ev, written.entry_hash)

        try:
            yield
        finally:
            stop_ev = ev_factory.server_stopped(cfg.server_id, {"server_id": cfg.server_id})
            written = writer.write(stop_ev)
            if written is not None:
                await index_db.index_event(stop_ev, written.entry_hash)
            await index_db.close()
            log.info("server_stopped")

    app = FastAPI(title="agent-mesh", version="0.1.0", lifespan=lifespan)

    from .routes import router  # avoid circular

    app.include_router(router)
    return app
