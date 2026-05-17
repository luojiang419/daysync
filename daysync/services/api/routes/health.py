from __future__ import annotations

from fastapi import APIRouter, Request

from daysync_core.media import get_ffmpeg_runtime_status

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request) -> dict[str, object]:
    ffmpeg_status = request.app.state.runtime.ffmpeg_status
    if ffmpeg_status is None:
        ffmpeg_status = get_ffmpeg_runtime_status(auto_download=False).to_dict()
    return {
        "status": "ok",
        "registered_projects": len(request.app.state.runtime.project_roots),
        "ffmpeg": ffmpeg_status,
    }
