from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ProjectCreateRequest(BaseModel):
    name: str
    root_path: str
    shooting_date: str | None = None


class ProjectOpenResponse(BaseModel):
    project: dict[str, Any]
    stats: dict[str, int]
    media_files: list[dict[str, Any]]
    flat_timelines: list[dict[str, Any]]
    sync_results: list[dict[str, Any]]
    project_settings: dict[str, Any]


class ProjectSettingsUpdateRequest(BaseModel):
    subtitle_workspace: dict[str, Any] = Field(default_factory=dict)
    export_workspace: dict[str, Any] = Field(default_factory=dict)


class MediaImportRequest(BaseModel):
    paths: list[str]
    session_id: str | None = None


class FlatTimelineCreateRequest(BaseModel):
    media_type: Literal["video", "audio"]
    media_file_ids: list[str]
    sort_mode: Literal["filename", "created_at", "manual"] = "filename"
    gap_ms: int = 1000


class SubtitleImportRequest(BaseModel):
    flat_timeline_id: str
    track_type: Literal["video_ref", "external_audio"]
    source_type: Literal["srt_import", "vtt_import", "json_import", "local_asr"] = "srt_import"
    path: str
    language: str | None = None


class ManualSyncRequest(BaseModel):
    video_subtitle_id: str
    audio_subtitle_id: str


class AutoCandidateRequest(BaseModel):
    anchor_subtitle_id: str
    limit: int = Field(default=5, ge=1, le=20)
    context_radius: int = Field(default=1, ge=0, le=3)


class OffsetClusterPairRequest(BaseModel):
    video_subtitle_id: str
    audio_subtitle_id: str


class OffsetClusterRequest(BaseModel):
    pairs: list[OffsetClusterPairRequest]
    tolerance_ms: int = Field(default=500, ge=0)
    min_inlier_ratio: float = Field(default=0.6, ge=0, le=1)
    min_anchor_count: int = Field(default=3, ge=1)
    context_radius: int = Field(default=1, ge=0, le=3)


class ClusterCandidateRequest(OffsetClusterRequest):
    note: str | None = None


class ReviewSyncResultRequest(BaseModel):
    action: Literal["accepted", "rejected", "adjusted", "commented"]
    new_offset_ms: int | None = None
    note: str | None = None


class ExportCsvRequest(BaseModel):
    output_path: str


class ExportFcp7XmlRequest(BaseModel):
    output_path: str


class ExportJsonRequest(BaseModel):
    output_path: str


class SearchQueryResponse(BaseModel):
    query: str
    video_results: list[dict[str, Any]]
    audio_results: list[dict[str, Any]]


class ErrorPayload(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorPayload
