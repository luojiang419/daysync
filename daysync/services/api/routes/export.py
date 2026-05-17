from __future__ import annotations

from fastapi import APIRouter, Request

from daysync_core.db import connect_database, database_path_for_project
from daysync_core.export import export_sync_report_csv, export_sync_report_fcp7_xml, list_export_jobs

from ..schemas.models import ExportCsvRequest, ExportFcp7XmlRequest

router = APIRouter(prefix="/projects/{project_id}/exports", tags=["export"])


@router.get("/jobs")
def list_export_jobs_route(project_id: str, request: Request) -> dict[str, object]:
    root_path = request.app.state.runtime.resolve(project_id)
    with connect_database(database_path_for_project(root_path)) as connection:
        return {"items": list_export_jobs(connection, project_id)}


@router.post("/csv")
def export_csv_route(project_id: str, payload: ExportCsvRequest, request: Request) -> dict[str, object]:
    root_path = request.app.state.runtime.resolve(project_id)
    with connect_database(database_path_for_project(root_path)) as connection:
        return export_sync_report_csv(connection, project_id, payload.output_path)


@router.post("/fcp7-xml")
def export_fcp7_xml_route(
    project_id: str, payload: ExportFcp7XmlRequest, request: Request
) -> dict[str, object]:
    root_path = request.app.state.runtime.resolve(project_id)
    with connect_database(database_path_for_project(root_path)) as connection:
        return export_sync_report_fcp7_xml(connection, project_id, payload.output_path)
