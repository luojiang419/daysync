from __future__ import annotations

from fastapi import APIRouter, Query, Request

from daysync_core.db import connect_database, database_path_for_project
from daysync_core.search import search_subtitles
from daysync_core.subtitles import import_srt

from ..schemas.models import SearchQueryResponse, SubtitleImportRequest

router = APIRouter(prefix="/projects/{project_id}/subtitles", tags=["subtitles"])


@router.post("/import")
def import_subtitles_route(
    project_id: str, payload: SubtitleImportRequest, request: Request
) -> dict[str, object]:
    root_path = request.app.state.runtime.resolve(project_id)
    with connect_database(database_path_for_project(root_path)) as connection:
        return import_srt(
            connection,
            project_id,
            payload.flat_timeline_id,
            payload.track_type,
            payload.source_type,
            payload.path,
            payload.language,
        )


@router.get("/search", response_model=SearchQueryResponse)
def search_subtitles_route(
    project_id: str,
    request: Request,
    q: str = Query(...),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, object]:
    root_path = request.app.state.runtime.resolve(project_id)
    with connect_database(database_path_for_project(root_path)) as connection:
        return search_subtitles(connection, project_id, q, limit)
