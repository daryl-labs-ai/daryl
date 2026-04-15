"""FastAPI dashboard app — read-only view of agent-mesh state.

Serves a single HTML page with vanilla JS + 4 JSON endpoints.
No database writes, no websocket, no framework beyond FastAPI.

Run:
    cd agent-mesh
    python -m dashboard.app
    # or
    uvicorn --factory dashboard.app:create_app --port 8001
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from .readers import DashboardReader


def _resolve_data_dir(data_dir: Path | str | None = None) -> Path:
    if data_dir is not None:
        return Path(data_dir).resolve()
    env = os.environ.get("AGENT_MESH_DATA_DIR")
    if env:
        return Path(env).resolve()
    return (Path(__file__).resolve().parent.parent / "data").resolve()


def _load_template() -> str:
    tpl = Path(__file__).resolve().parent / "templates" / "index.html"
    return tpl.read_text(encoding="utf-8")


def create_app(data_dir: Path | str | None = None) -> FastAPI:
    data_path = _resolve_data_dir(data_dir)
    reader = DashboardReader(data_path)
    html = _load_template()

    app = FastAPI(title="agent-mesh dashboard", version="0.1.0")
    app.state.reader = reader
    app.state.html = html
    app.state.data_dir = str(data_path)

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        return HTMLResponse(app.state.html)

    @app.get("/api/missions")
    async def api_missions() -> JSONResponse:
        return JSONResponse(app.state.reader.list_missions())

    @app.get("/api/missions/{mission_id}/compare")
    async def api_mission_compare(mission_id: str) -> JSONResponse:
        data = app.state.reader.compare_mission_results(mission_id)
        if data is None:
            raise HTTPException(status_code=404, detail="mission not found")
        return JSONResponse(data)

    @app.get("/api/missions/{mission_id}")
    async def api_mission_detail(mission_id: str) -> JSONResponse:
        detail = app.state.reader.get_mission_detail(mission_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="mission not found")
        return JSONResponse(detail)

    @app.get("/api/tasks")
    async def api_tasks() -> JSONResponse:
        return JSONResponse(app.state.reader.list_tasks())

    @app.get("/api/tasks/{task_id}")
    async def api_task_detail(task_id: str) -> JSONResponse:
        detail = app.state.reader.get_task_detail(task_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="task not found")
        return JSONResponse(detail)

    @app.get("/api/agents")
    async def api_agents() -> JSONResponse:
        return JSONResponse(app.state.reader.list_agents())

    @app.get("/api/events")
    async def api_events(limit: int = 50) -> JSONResponse:
        clamped = max(1, min(500, int(limit)))
        return JSONResponse(app.state.reader.recent_events(limit=clamped))

    @app.get("/api/events/{event_id}")
    async def api_event_detail(event_id: str) -> JSONResponse:
        ev = app.state.reader.get_event(event_id)
        if ev is None:
            raise HTTPException(status_code=404, detail="event not found")
        return JSONResponse(ev)

    return app


# Module-level app so `uvicorn dashboard.app:app` works without --factory.
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "dashboard.app:app",
        host=os.environ.get("DASHBOARD_HOST", "127.0.0.1"),
        port=int(os.environ.get("DASHBOARD_PORT", "8001")),
        reload=False,
    )
