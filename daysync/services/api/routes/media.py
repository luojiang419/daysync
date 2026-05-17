from __future__ import annotations

from fastapi import APIRouter, Request

from daysync_core.db import connect_database, database_path_for_project
from daysync_core.media import ensure_ffmpeg_runtime, import_media
from daysync_core.timeline import generate_flat_timeline_for_project_media

from ..schemas.models import MediaImportRequest

router = APIRouter(prefix="/projects/{project_id}/media", tags=["media"])


@router.post("/import")
def import_media_route(project_id: str, payload: MediaImportRequest, request: Request) -> dict[str, object]:
    request.app.state.runtime.ffmpeg_status = ensure_ffmpeg_runtime().to_dict()
    root_path = request.app.state.runtime.resolve(project_id)
    with connect_database(database_path_for_project(root_path)) as connection:
        result = import_media(connection, project_id, payload.paths, payload.session_id)
        generated_timelines = []
        for media_type in ("video", "audio"):
            timeline = generate_flat_timeline_for_project_media(connection, project_id, media_type)
            if timeline is not None:
                generated_timelines.append(
                    {
                        "media_type": media_type,
                        "flat_timeline_id": timeline["flat_timeline_id"],
                        "items": timeline["items"],
                    }
                )
        return {
            **result,
            "generated_timelines": generated_timelines,
        }
