from __future__ import annotations

from fastapi import APIRouter, Request

from daysync_core.db import connect_database, database_path_for_project
from daysync_core.studio import get_studio_timeline_snapshot

router = APIRouter(prefix="/projects/{project_id}/studio", tags=["studio"])


@router.get("/timeline")
def studio_timeline_route(project_id: str, request: Request) -> dict[str, object]:
    root_path = request.app.state.runtime.resolve(project_id)
    with connect_database(database_path_for_project(root_path)) as connection:
        return get_studio_timeline_snapshot(connection, project_id)
