from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from daysync_core.errors import DaySyncError
from daysync_core.media import ensure_ffmpeg_runtime, ffmpeg_status_from_exception

from .app_state import AppState
from .routes.admin import router as admin_router
from .routes.export import router as export_router
from .routes.health import router as health_router
from .routes.media import router as media_router
from .routes.projects import router as projects_router
from .routes.subtitles import router as subtitles_router
from .routes.sync import router as sync_router
from .routes.timeline import router as timeline_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not hasattr(app.state, "runtime"):
        app.state.runtime = AppState()
    try:
        app.state.runtime.ffmpeg_status = ensure_ffmpeg_runtime().to_dict()
    except Exception as exc:
        app.state.runtime.ffmpeg_status = ffmpeg_status_from_exception(exc).to_dict()
    yield


app = FastAPI(title="DaySync API", version="0.1.0", lifespan=lifespan)
app.state.runtime = AppState()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:1420",
        "http://localhost:1420",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
        "http://tauri.localhost",
        "https://tauri.localhost",
        "tauri://localhost",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(DaySyncError)
def handle_daysync_error(_: Request, exc: DaySyncError) -> JSONResponse:
    return JSONResponse(status_code=exc.http_status, content=exc.to_dict())


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "DaySync API", "version": "0.1.0"}


app.include_router(health_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(projects_router, prefix="/api")
app.include_router(media_router, prefix="/api")
app.include_router(timeline_router, prefix="/api")
app.include_router(subtitles_router, prefix="/api")
app.include_router(sync_router, prefix="/api")
app.include_router(export_router, prefix="/api")
