from __future__ import annotations

from fastapi import APIRouter, Request

from daysync_core.db import connect_database, database_path_for_project
from daysync_core.export import export_sync_report_csv

from ..schemas.models import ExportCsvRequest

router = APIRouter(prefix="/projects/{project_id}/exports", tags=["export"])


@router.post("/csv")
def export_csv_route(project_id: str, payload: ExportCsvRequest, request: Request) -> dict[str, object]:
    root_path = request.app.state.runtime.resolve(project_id)
    with connect_database(database_path_for_project(root_path)) as connection:
        return export_sync_report_csv(connection, project_id, payload.output_path)
