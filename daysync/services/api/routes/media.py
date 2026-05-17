from __future__ import annotations

from fastapi import APIRouter, Request

from daysync_core.db import connect_database, database_path_for_project
from daysync_core.media import import_media

from ..schemas.models import MediaImportRequest

router = APIRouter(prefix="/projects/{project_id}/media", tags=["media"])


@router.post("/import")
def import_media_route(project_id: str, payload: MediaImportRequest, request: Request) -> dict[str, object]:
    root_path = request.app.state.runtime.resolve(project_id)
    with connect_database(database_path_for_project(root_path)) as connection:
        return import_media(connection, project_id, payload.paths, payload.session_id)
