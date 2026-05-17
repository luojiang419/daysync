from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from daysync_core.errors import DaySyncError

from .app_state import AppState
from .routes.export import router as export_router
from .routes.health import router as health_router
from .routes.media import router as media_router
from .routes.projects import router as projects_router
from .routes.subtitles import router as subtitles_router
from .routes.sync import router as sync_router
from .routes.timeline import router as timeline_router

app = FastAPI(title="DaySync API", version="0.1.0")
app.state.runtime = AppState()


@app.exception_handler(DaySyncError)
def handle_daysync_error(_: Request, exc: DaySyncError) -> JSONResponse:
    return JSONResponse(status_code=exc.http_status, content=exc.to_dict())


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "DaySync API", "version": "0.1.0"}


app.include_router(health_router, prefix="/api")
app.include_router(projects_router, prefix="/api")
app.include_router(media_router, prefix="/api")
app.include_router(timeline_router, prefix="/api")
app.include_router(subtitles_router, prefix="/api")
app.include_router(sync_router, prefix="/api")
app.include_router(export_router, prefix="/api")
