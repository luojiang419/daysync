from __future__ import annotations

from fastapi import APIRouter, Request

from daysync_core.db import connect_database, database_path_for_project
from daysync_core.timeline import generate_flat_timeline

from ..schemas.models import FlatTimelineCreateRequest

router = APIRouter(prefix="/projects/{project_id}/flat-timelines", tags=["timeline"])


@router.post("")
def create_flat_timeline_route(
    project_id: str, payload: FlatTimelineCreateRequest, request: Request
) -> dict[str, object]:
    root_path = request.app.state.runtime.resolve(project_id)
    with connect_database(database_path_for_project(root_path)) as connection:
        return generate_flat_timeline(
            connection,
            project_id,
            payload.media_type,
            payload.media_file_ids,
            payload.sort_mode,
            payload.gap_ms,
        )
