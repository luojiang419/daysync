from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from daysync_core.db import (
    connect_database,
    create_project,
    database_path_for_project,
    open_project,
    project_snapshot,
    save_project_settings,
)
from daysync_core.errors import DaySyncError
from daysync_core.export import (
    export_sync_report_csv,
    export_sync_report_fcpxml,
    export_sync_report_fcp7_xml,
    export_sync_report_json,
    export_sync_report_otio,
    list_export_jobs,
)
from daysync_core.media import ensure_ffmpeg_runtime, get_ffmpeg_runtime_status, import_media
from daysync_core.search import search_subtitles
from daysync_core.studio import get_studio_timeline_snapshot
from daysync_core.subtitles import import_srt
from daysync_core.sync import (
    analyze_offset_cluster,
    create_cluster_sync_candidate,
    create_manual_anchor_sync,
    list_review_queue,
    list_sync_results,
    recommend_auto_candidates,
    review_sync_result,
)
from daysync_core.timeline import generate_flat_timeline, generate_flat_timeline_for_project_media


@dataclass
class RuntimeState:
    project_roots: dict[str, str] = field(default_factory=dict)
    ffmpeg_status: dict[str, object] | None = None

    def register(self, project_id: str, root_path: str) -> None:
        self.project_roots[project_id] = root_path

    def resolve(self, project_id: str) -> str:
        root_path = self.project_roots.get(project_id)
        if root_path is None:
            raise DaySyncError(
                "PROJECT_NOT_FOUND",
                "Project is not opened in the current runtime session",
                {"project_id": project_id},
            )
        return root_path


class RuntimeDispatcher:
    def __init__(self, state: RuntimeState | None = None) -> None:
        self.state = state or RuntimeState()
        self._handlers: dict[str, Any] = {
            "health.check": self.health_check,
            "project.create": self.project_create,
            "project.open": self.project_open,
            "project.save_settings": self.project_save_settings,
            "media.import": self.media_import,
            "timeline.create": self.timeline_create,
            "subtitle.import": self.subtitle_import,
            "subtitle.search": self.subtitle_search,
            "sync.manual_anchor": self.sync_manual_anchor,
            "sync.auto_candidates": self.sync_auto_candidates,
            "sync.offset_cluster": self.sync_offset_cluster,
            "sync.cluster_candidate": self.sync_cluster_candidate,
            "sync.review_queue": self.sync_review_queue,
            "sync.review_result": self.sync_review_result,
            "sync.list_results": self.sync_list_results,
            "export.list_jobs": self.export_list_jobs,
            "export.csv": self.export_csv,
            "export.fcp7_xml": self.export_fcp7_xml,
            "export.json": self.export_json,
            "export.otio": self.export_otio,
            "export.fcpxml": self.export_fcpxml,
            "studio.timeline": self.studio_timeline,
        }

    def dispatch(self, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        handler = self._handlers.get(method)
        if handler is None:
            raise DaySyncError("METHOD_NOT_FOUND", f"Unsupported runtime method: {method}", {"method": method})
        return handler(payload or {})

    def health_check(self, _: dict[str, Any]) -> dict[str, Any]:
        ffmpeg_status = self.state.ffmpeg_status
        if ffmpeg_status is None:
            ffmpeg_status = get_ffmpeg_runtime_status(auto_download=False).to_dict()
            self.state.ffmpeg_status = ffmpeg_status
        return {
            "status": "ok",
            "registered_projects": len(self.state.project_roots),
            "ffmpeg": ffmpeg_status,
        }

    def project_create(self, payload: dict[str, Any]) -> dict[str, Any]:
        project = create_project(
            self._require_str(payload, "root_path"),
            self._require_str(payload, "name"),
            self._optional_str(payload, "shooting_date"),
        )
        self.state.register(project["id"], project["root_path"])
        return project_snapshot(project["root_path"])

    def project_open(self, payload: dict[str, Any]) -> dict[str, Any]:
        project = open_project(self._require_str(payload, "root_path"))
        self.state.register(project["id"], project["root_path"])
        return project_snapshot(project["root_path"])

    def project_save_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        project_id = self._require_str(payload, "project_id")
        root_path = self.state.resolve(project_id)
        with connect_database(database_path_for_project(root_path)) as connection:
            settings = save_project_settings(
                connection,
                project_id,
                {
                    "subtitle_workspace": self._optional_dict(payload, "subtitle_workspace"),
                    "export_workspace": self._optional_dict(payload, "export_workspace"),
                },
            )
        return {"project_settings": settings}

    def media_import(self, payload: dict[str, Any]) -> dict[str, Any]:
        project_id = self._require_str(payload, "project_id")
        self.state.ffmpeg_status = ensure_ffmpeg_runtime().to_dict()
        root_path = self.state.resolve(project_id)
        with connect_database(database_path_for_project(root_path)) as connection:
            result = import_media(
                connection,
                project_id,
                self._require_str_list(payload, "paths"),
                self._optional_str(payload, "session_id"),
            )
            generated_timelines = []
            for media_type in ("video", "audio"):
                timeline = generate_flat_timeline_for_project_media(connection, project_id, media_type)
                if timeline is not None:
                    generated_timelines.append(
                        {
                            "media_type": media_type,
                            "flat_timeline_id": timeline["flat_timeline_id"],
                            "items": timeline["items"],
                        }
                    )
            return {**result, "generated_timelines": generated_timelines}

    def timeline_create(self, payload: dict[str, Any]) -> dict[str, Any]:
        project_id = self._require_str(payload, "project_id")
        root_path = self.state.resolve(project_id)
        with connect_database(database_path_for_project(root_path)) as connection:
            return generate_flat_timeline(
                connection,
                project_id,
                self._require_literal(payload, "media_type", {"video", "audio"}),
                self._require_str_list(payload, "media_file_ids"),
                self._require_literal(payload, "sort_mode", {"filename", "created_at", "manual"}, default="filename"),
                self._require_int(payload, "gap_ms", default=1000),
            )

    def subtitle_import(self, payload: dict[str, Any]) -> dict[str, Any]:
        project_id = self._require_str(payload, "project_id")
        root_path = self.state.resolve(project_id)
        with connect_database(database_path_for_project(root_path)) as connection:
            return import_srt(
                connection,
                project_id,
                self._require_str(payload, "flat_timeline_id"),
                self._require_literal(payload, "track_type", {"video_ref", "external_audio"}),
                self._require_literal(
                    payload,
                    "source_type",
                    {"srt_import", "vtt_import", "json_import", "local_asr"},
                    default="srt_import",
                ),
                self._require_str(payload, "path"),
                self._optional_str(payload, "language"),
            )

    def subtitle_search(self, payload: dict[str, Any]) -> dict[str, Any]:
        project_id = self._require_str(payload, "project_id")
        root_path = self.state.resolve(project_id)
        with connect_database(database_path_for_project(root_path)) as connection:
            return search_subtitles(
                connection,
                project_id,
                self._require_str(payload, "query"),
                self._require_int(payload, "limit", default=20),
            )

    def sync_manual_anchor(self, payload: dict[str, Any]) -> dict[str, Any]:
        project_id = self._require_str(payload, "project_id")
        root_path = self.state.resolve(project_id)
        with connect_database(database_path_for_project(root_path)) as connection:
            return create_manual_anchor_sync(
                connection,
                project_id,
                self._require_str(payload, "video_subtitle_id"),
                self._require_str(payload, "audio_subtitle_id"),
            )

    def sync_auto_candidates(self, payload: dict[str, Any]) -> dict[str, Any]:
        project_id = self._require_str(payload, "project_id")
        root_path = self.state.resolve(project_id)
        with connect_database(database_path_for_project(root_path)) as connection:
            return recommend_auto_candidates(
                connection,
                project_id,
                self._require_str(payload, "anchor_subtitle_id"),
                self._require_int(payload, "limit", default=5),
                self._require_int(payload, "context_radius", default=1),
            )

    def sync_offset_cluster(self, payload: dict[str, Any]) -> dict[str, Any]:
        project_id = self._require_str(payload, "project_id")
        root_path = self.state.resolve(project_id)
        with connect_database(database_path_for_project(root_path)) as connection:
            return analyze_offset_cluster(
                connection,
                project_id,
                pairs=self._require_pairs(payload),
                tolerance_ms=self._require_int(payload, "tolerance_ms", default=500),
                min_inlier_ratio=self._require_float(payload, "min_inlier_ratio", default=0.6),
                min_anchor_count=self._require_int(payload, "min_anchor_count", default=3),
                context_radius=self._require_int(payload, "context_radius", default=1),
            )

    def sync_cluster_candidate(self, payload: dict[str, Any]) -> dict[str, Any]:
        project_id = self._require_str(payload, "project_id")
        root_path = self.state.resolve(project_id)
        with connect_database(database_path_for_project(root_path)) as connection:
            return create_cluster_sync_candidate(
                connection,
                project_id,
                pairs=self._require_pairs(payload),
                tolerance_ms=self._require_int(payload, "tolerance_ms", default=500),
                min_inlier_ratio=self._require_float(payload, "min_inlier_ratio", default=0.6),
                min_anchor_count=self._require_int(payload, "min_anchor_count", default=3),
                context_radius=self._require_int(payload, "context_radius", default=1),
                note=self._optional_str(payload, "note"),
            )

    def sync_review_queue(self, payload: dict[str, Any]) -> dict[str, Any]:
        project_id = self._require_str(payload, "project_id")
        root_path = self.state.resolve(project_id)
        with connect_database(database_path_for_project(root_path)) as connection:
            return {"items": list_review_queue(connection, project_id)}

    def sync_review_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        project_id = self._require_str(payload, "project_id")
        root_path = self.state.resolve(project_id)
        with connect_database(database_path_for_project(root_path)) as connection:
            return review_sync_result(
                connection,
                project_id,
                self._require_str(payload, "sync_result_id"),
                self._require_literal(payload, "action", {"accepted", "rejected", "adjusted", "commented"}),
                self._optional_int(payload, "new_offset_ms"),
                self._optional_str(payload, "note"),
            )

    def sync_list_results(self, payload: dict[str, Any]) -> dict[str, Any]:
        project_id = self._require_str(payload, "project_id")
        root_path = self.state.resolve(project_id)
        with connect_database(database_path_for_project(root_path)) as connection:
            return {"sync_results": list_sync_results(connection, project_id)}

    def export_list_jobs(self, payload: dict[str, Any]) -> dict[str, Any]:
        project_id = self._require_str(payload, "project_id")
        root_path = self.state.resolve(project_id)
        with connect_database(database_path_for_project(root_path)) as connection:
            return {"items": list_export_jobs(connection, project_id)}

    def export_csv(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._export_with_output(payload, export_sync_report_csv)

    def export_fcp7_xml(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._export_with_output(payload, export_sync_report_fcp7_xml)

    def export_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._export_with_output(payload, export_sync_report_json)

    def export_otio(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._export_with_output(payload, export_sync_report_otio)

    def export_fcpxml(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._export_with_output(payload, export_sync_report_fcpxml)

    def studio_timeline(self, payload: dict[str, Any]) -> dict[str, Any]:
        project_id = self._require_str(payload, "project_id")
        root_path = self.state.resolve(project_id)
        with connect_database(database_path_for_project(root_path)) as connection:
            return get_studio_timeline_snapshot(connection, project_id)

    def _export_with_output(self, payload: dict[str, Any], handler: Any) -> dict[str, Any]:
        project_id = self._require_str(payload, "project_id")
        root_path = self.state.resolve(project_id)
        with connect_database(database_path_for_project(root_path)) as connection:
            return handler(connection, project_id, self._require_str(payload, "output_path"))

    def _require_pairs(self, payload: dict[str, Any]) -> list[dict[str, str]]:
        value = payload.get("pairs")
        if not isinstance(value, list):
            raise DaySyncError("INVALID_REQUEST", "pairs must be a list", {"field": "pairs"})
        pairs: list[dict[str, str]] = []
        for item in value:
            if not isinstance(item, dict):
                raise DaySyncError("INVALID_REQUEST", "pair must be an object", {"field": "pairs"})
            pairs.append(
                {
                    "video_subtitle_id": self._require_str(item, "video_subtitle_id"),
                    "audio_subtitle_id": self._require_str(item, "audio_subtitle_id"),
                }
            )
        return pairs

    @staticmethod
    def _require_str(payload: dict[str, Any], field: str) -> str:
        value = payload.get(field)
        if not isinstance(value, str) or not value:
            raise DaySyncError("INVALID_REQUEST", f"{field} must be a non-empty string", {"field": field})
        return value

    @staticmethod
    def _optional_str(payload: dict[str, Any], field: str) -> str | None:
        value = payload.get(field)
        if value is None:
            return None
        if not isinstance(value, str):
            raise DaySyncError("INVALID_REQUEST", f"{field} must be a string", {"field": field})
        return value

    @staticmethod
    def _require_int(payload: dict[str, Any], field: str, default: int | None = None) -> int:
        value = payload.get(field, default)
        if not isinstance(value, int):
            raise DaySyncError("INVALID_REQUEST", f"{field} must be an integer", {"field": field})
        return value

    @staticmethod
    def _optional_int(payload: dict[str, Any], field: str) -> int | None:
        value = payload.get(field)
        if value is None:
            return None
        if not isinstance(value, int):
            raise DaySyncError("INVALID_REQUEST", f"{field} must be an integer", {"field": field})
        return value

    @staticmethod
    def _require_float(payload: dict[str, Any], field: str, default: float | None = None) -> float:
        value = payload.get(field, default)
        if not isinstance(value, (int, float)):
            raise DaySyncError("INVALID_REQUEST", f"{field} must be a number", {"field": field})
        return float(value)

    @staticmethod
    def _require_str_list(payload: dict[str, Any], field: str) -> list[str]:
        value = payload.get(field)
        if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
            raise DaySyncError("INVALID_REQUEST", f"{field} must be a list of strings", {"field": field})
        return value

    @staticmethod
    def _optional_dict(payload: dict[str, Any], field: str) -> dict[str, Any]:
        value = payload.get(field)
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise DaySyncError("INVALID_REQUEST", f"{field} must be an object", {"field": field})
        return value

    @staticmethod
    def _require_literal(
        payload: dict[str, Any],
        field: str,
        allowed: set[str],
        default: str | None = None,
    ) -> str:
        value = payload.get(field, default)
        if not isinstance(value, str) or value not in allowed:
            raise DaySyncError(
                "INVALID_REQUEST",
                f"{field} must be one of {sorted(allowed)}",
                {"field": field, "allowed": sorted(allowed)},
            )
        return value


def dispatch_message(
    dispatcher: RuntimeDispatcher,
    message: dict[str, Any],
) -> dict[str, Any]:
    message_id = message.get("id")
    method = message.get("method")
    payload = message.get("payload")

    if not isinstance(method, str) or not method:
        return {
            "id": message_id,
            "ok": False,
            "error": {
                "code": "INVALID_MESSAGE",
                "message": "method must be a non-empty string",
                "details": {},
            },
        }

    if payload is None:
        payload = {}
    elif not isinstance(payload, dict):
        return {
            "id": message_id,
            "ok": False,
            "error": {
                "code": "INVALID_MESSAGE",
                "message": "payload must be an object",
                "details": {},
            },
        }

    try:
        result = dispatcher.dispatch(method, payload)
        return {"id": message_id, "ok": True, "result": result}
    except DaySyncError as exc:
        return {"id": message_id, "ok": False, "error": exc.to_dict()["error"]}
    except Exception as exc:
        return {
            "id": message_id,
            "ok": False,
            "error": {
                "code": "RUNTIME_INTERNAL_ERROR",
                "message": str(exc),
                "details": {"type": exc.__class__.__name__},
            },
        }
