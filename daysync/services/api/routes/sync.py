from __future__ import annotations

from fastapi import APIRouter, Request

from daysync_core.db import connect_database, database_path_for_project
from daysync_core.sync import create_manual_anchor_sync, list_sync_results

from ..schemas.models import ManualSyncRequest

router = APIRouter(prefix="/projects/{project_id}/sync", tags=["sync"])


@router.post("/manual-anchor")
def manual_anchor_sync_route(
    project_id: str, payload: ManualSyncRequest, request: Request
) -> dict[str, object]:
    root_path = request.app.state.runtime.resolve(project_id)
    with connect_database(database_path_for_project(root_path)) as connection:
        result = create_manual_anchor_sync(
            connection,
            project_id,
            payload.video_subtitle_id,
            payload.audio_subtitle_id,
        )
        return {"sync_result": result}


@router.get("/results")
def list_sync_results_route(project_id: str, request: Request) -> dict[str, object]:
    root_path = request.app.state.runtime.resolve(project_id)
    with connect_database(database_path_for_project(root_path)) as connection:
        return {"sync_results": list_sync_results(connection, project_id)}
