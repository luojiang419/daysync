from __future__ import annotations

from fastapi import APIRouter, Request

from daysync_core.db import connect_database, database_path_for_project
from daysync_core.sync import create_manual_anchor_sync, list_sync_results, recommend_auto_candidates

from ..schemas.models import AutoCandidateRequest, ManualSyncRequest

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


@router.post("/auto-candidates")
def auto_candidates_route(
    project_id: str, payload: AutoCandidateRequest, request: Request
) -> dict[str, object]:
    root_path = request.app.state.runtime.resolve(project_id)
    with connect_database(database_path_for_project(root_path)) as connection:
        return recommend_auto_candidates(
            connection,
            project_id,
            payload.anchor_subtitle_id,
            payload.limit,
            payload.context_radius,
        )


@router.get("/results")
def list_sync_results_route(project_id: str, request: Request) -> dict[str, object]:
    root_path = request.app.state.runtime.resolve(project_id)
    with connect_database(database_path_for_project(root_path)) as connection:
        return {"sync_results": list_sync_results(connection, project_id)}
