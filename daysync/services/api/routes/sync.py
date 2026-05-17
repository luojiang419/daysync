from __future__ import annotations

from fastapi import APIRouter, Request

from daysync_core.db import connect_database, database_path_for_project
from daysync_core.sync import (
    analyze_offset_cluster,
    create_cluster_sync_candidate,
    create_manual_anchor_sync,
    list_sync_results,
    list_review_queue,
    recommend_auto_candidates,
    review_sync_result,
)

from ..schemas.models import (
    AutoCandidateRequest,
    ClusterCandidateRequest,
    ManualSyncRequest,
    OffsetClusterRequest,
    ReviewSyncResultRequest,
)

router = APIRouter(prefix="/projects/{project_id}/sync", tags=["sync"])


@router.post("/manual-anchor")
def manual_anchor_sync_route(
    project_id: str, payload: ManualSyncRequest, request: Request
) -> dict[str, object]:
    root_path = request.app.state.runtime.resolve(project_id)
    with connect_database(database_path_for_project(root_path)) as connection:
        return create_manual_anchor_sync(
            connection,
            project_id,
            payload.video_subtitle_id,
            payload.audio_subtitle_id,
        )


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


@router.post("/offset-cluster")
def offset_cluster_route(
    project_id: str, payload: OffsetClusterRequest, request: Request
) -> dict[str, object]:
    root_path = request.app.state.runtime.resolve(project_id)
    with connect_database(database_path_for_project(root_path)) as connection:
        return analyze_offset_cluster(
            connection,
            project_id,
            pairs=[
                {
                    "video_subtitle_id": pair.video_subtitle_id,
                    "audio_subtitle_id": pair.audio_subtitle_id,
                }
                for pair in payload.pairs
            ],
            tolerance_ms=payload.tolerance_ms,
            min_inlier_ratio=payload.min_inlier_ratio,
            min_anchor_count=payload.min_anchor_count,
            context_radius=payload.context_radius,
        )


@router.post("/cluster-candidate")
def cluster_candidate_route(
    project_id: str, payload: ClusterCandidateRequest, request: Request
) -> dict[str, object]:
    root_path = request.app.state.runtime.resolve(project_id)
    with connect_database(database_path_for_project(root_path)) as connection:
        return create_cluster_sync_candidate(
            connection,
            project_id,
            pairs=[
                {
                    "video_subtitle_id": pair.video_subtitle_id,
                    "audio_subtitle_id": pair.audio_subtitle_id,
                }
                for pair in payload.pairs
            ],
            tolerance_ms=payload.tolerance_ms,
            min_inlier_ratio=payload.min_inlier_ratio,
            min_anchor_count=payload.min_anchor_count,
            context_radius=payload.context_radius,
            note=payload.note,
        )


@router.get("/review-queue")
def review_queue_route(project_id: str, request: Request) -> dict[str, object]:
    root_path = request.app.state.runtime.resolve(project_id)
    with connect_database(database_path_for_project(root_path)) as connection:
        return {"items": list_review_queue(connection, project_id)}


@router.post("/results/{sync_result_id}/review")
def review_sync_result_route(
    project_id: str,
    sync_result_id: str,
    payload: ReviewSyncResultRequest,
    request: Request,
) -> dict[str, object]:
    root_path = request.app.state.runtime.resolve(project_id)
    with connect_database(database_path_for_project(root_path)) as connection:
        return review_sync_result(
            connection,
            project_id,
            sync_result_id,
            payload.action,
            payload.new_offset_ms,
            payload.note,
        )


@router.get("/results")
def list_sync_results_route(project_id: str, request: Request) -> dict[str, object]:
    root_path = request.app.state.runtime.resolve(project_id)
    with connect_database(database_path_for_project(root_path)) as connection:
        return {"sync_results": list_sync_results(connection, project_id)}
