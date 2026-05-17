from __future__ import annotations

from fastapi import APIRouter, Query, Request

from daysync_core.db import (
    connect_database,
    create_project,
    database_path_for_project,
    open_project,
    project_snapshot,
    save_project_settings,
)

from ..schemas.models import ProjectCreateRequest, ProjectOpenResponse, ProjectSettingsUpdateRequest

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectOpenResponse)
def create_project_route(payload: ProjectCreateRequest, request: Request) -> dict[str, object]:
    project = create_project(payload.root_path, payload.name, payload.shooting_date)
    request.app.state.runtime.register(project["id"], project["root_path"])
    return project_snapshot(project["root_path"])


@router.get("/open", response_model=ProjectOpenResponse)
def open_project_route(request: Request, root_path: str = Query(...)) -> dict[str, object]:
    project = open_project(root_path)
    request.app.state.runtime.register(project["id"], project["root_path"])
    return project_snapshot(project["root_path"])


@router.put("/{project_id}/settings")
def update_project_settings_route(
    project_id: str, payload: ProjectSettingsUpdateRequest, request: Request
) -> dict[str, object]:
    root_path = request.app.state.runtime.resolve(project_id)
    with connect_database(database_path_for_project(root_path)) as connection:
        settings = save_project_settings(connection, project_id, payload.model_dump())
    return {"project_settings": settings}
