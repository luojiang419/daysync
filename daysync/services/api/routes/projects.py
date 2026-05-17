from __future__ import annotations

from fastapi import APIRouter, Query, Request

from daysync_core.db import create_project, open_project, project_snapshot

from ..schemas.models import ProjectCreateRequest, ProjectOpenResponse

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
