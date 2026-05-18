from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from daysync_core.bridge import RuntimeDispatcher, RuntimeState, dispatch_message


def test_mvp_flow(monkeypatch, tmp_path: Path) -> None:
    sample_root = Path(__file__).resolve().parents[2] / "sample_data"
    fixtures = {
        "A001_C001.mov": json.loads((sample_root / "media" / "mock_video_001.json").read_text(encoding="utf-8")),
        "A001_C002.mov": json.loads((sample_root / "media" / "mock_video_002.json").read_text(encoding="utf-8")),
        "ZOOM0001.wav": json.loads((sample_root / "media" / "mock_audio_001.json").read_text(encoding="utf-8")),
    }

    def fake_probe(media_path: Path) -> dict[str, object]:
        from daysync_core.media.ffprobe import parse_ffprobe_payload

        return parse_ffprobe_payload(media_path, fixtures[media_path.name])

    fake_ffmpeg_status = {
        "ready": True,
        "source": "test",
        "version": "8.1.1",
        "root_path": str(tmp_path / "ffmpeg"),
        "ffmpeg_path": str(tmp_path / "ffmpeg" / "ffmpeg.exe"),
        "ffprobe_path": str(tmp_path / "ffmpeg" / "ffprobe.exe"),
        "error": None,
    }

    monkeypatch.setattr("daysync_core.media.service.probe_media", fake_probe)
    monkeypatch.setattr(
        "daysync_core.bridge.dispatcher.ensure_ffmpeg_runtime",
        lambda: SimpleNamespace(to_dict=lambda: fake_ffmpeg_status),
    )
    dispatcher = RuntimeDispatcher(RuntimeState())
    project_root = tmp_path / "project"
    create_response = runtime_call(
        dispatcher,
        "project.create",
        {
            "name": "纪录片样片 2026-01-01",
            "root_path": str(project_root),
            "shooting_date": "2026-01-01",
        },
    )
    project_id = create_response["project"]["id"]
    assert create_response["project_settings"]["subtitle_workspace"]["query"] == ""

    media_import = runtime_call(
        dispatcher,
        "media.import",
        {
            "project_id": project_id,
            "paths": [
                str(sample_root / "media" / "A001_C001.mov"),
                str(sample_root / "media" / "A001_C002.mov"),
                str(sample_root / "media" / "ZOOM0001.wav"),
            ],
            "session_id": None,
        },
    )
    imported = media_import["imported"]
    video_ids = [item["id"] for item in imported if item["media_type"] == "video"]
    audio_ids = [item["id"] for item in imported if item["media_type"] == "audio"]

    video_timeline = runtime_call(
        dispatcher,
        "timeline.create",
        {
            "project_id": project_id,
            "media_type": "video",
            "media_file_ids": video_ids,
            "sort_mode": "filename",
            "gap_ms": 1000,
        },
    )
    audio_timeline = runtime_call(
        dispatcher,
        "timeline.create",
        {
            "project_id": project_id,
            "media_type": "audio",
            "media_file_ids": audio_ids,
            "sort_mode": "filename",
            "gap_ms": 1000,
        },
    )

    video_subtitles = runtime_call(
        dispatcher,
        "subtitle.import",
        {
            "project_id": project_id,
            "flat_timeline_id": video_timeline["flat_timeline_id"],
            "track_type": "video_ref",
            "source_type": "srt_import",
            "path": str(sample_root / "subtitles" / "video_flat.srt"),
            "language": "zh-CN",
        },
    )
    audio_subtitles = runtime_call(
        dispatcher,
        "subtitle.import",
        {
            "project_id": project_id,
            "flat_timeline_id": audio_timeline["flat_timeline_id"],
            "track_type": "external_audio",
            "source_type": "srt_import",
            "path": str(sample_root / "subtitles" / "audio_flat.srt"),
            "language": "zh-CN",
        },
    )
    assert video_subtitles["imported_count"] == 2
    assert audio_subtitles["imported_count"] == 2

    search_data = runtime_call(
        dispatcher,
        "subtitle.search",
        {
            "project_id": project_id,
            "query": "我们到了这里",
            "limit": 20,
        },
    )
    assert len(search_data["video_results"]) == 1
    assert len(search_data["audio_results"]) == 1

    auto_candidates_response = runtime_call(
        dispatcher,
        "sync.auto_candidates",
        {
            "project_id": project_id,
            "anchor_subtitle_id": search_data["video_results"][0]["subtitle_id"],
            "limit": 3,
            "context_radius": 1,
        },
    )
    assert auto_candidates_response["candidates"][0]["subtitle_id"] == search_data["audio_results"][0]["subtitle_id"]

    offset_cluster_response = runtime_call(
        dispatcher,
        "sync.offset_cluster",
        {
            "project_id": project_id,
            "pairs": [
                {
                    "video_subtitle_id": search_data["video_results"][0]["subtitle_id"],
                    "audio_subtitle_id": search_data["audio_results"][0]["subtitle_id"],
                }
            ],
            "tolerance_ms": 500,
            "min_inlier_ratio": 0.6,
            "min_anchor_count": 3,
            "context_radius": 1,
        },
    )
    assert offset_cluster_response["cluster_summary"]["candidate_count"] == 1

    cluster_candidate_response = runtime_call(
        dispatcher,
        "sync.cluster_candidate",
        {
            "project_id": project_id,
            "pairs": [
                {
                    "video_subtitle_id": search_data["video_results"][0]["subtitle_id"],
                    "audio_subtitle_id": search_data["audio_results"][0]["subtitle_id"],
                }
            ],
            "tolerance_ms": 500,
            "min_inlier_ratio": 0.6,
            "min_anchor_count": 3,
            "context_radius": 1,
            "note": None,
        },
    )
    candidate_sync_result_id = cluster_candidate_response["sync_result"]["id"]

    review_queue_response = runtime_call(dispatcher, "sync.review_queue", {"project_id": project_id})
    assert review_queue_response["items"][0]["id"] == candidate_sync_result_id

    review_response = runtime_call(
        dispatcher,
        "sync.review_result",
        {
            "project_id": project_id,
            "sync_result_id": candidate_sync_result_id,
            "action": "accepted",
            "new_offset_ms": None,
            "note": None,
        },
    )
    assert review_response["sync_result"]["status"] == "accepted_auto"

    sync_response = runtime_call(
        dispatcher,
        "sync.manual_anchor",
        {
            "project_id": project_id,
            "video_subtitle_id": search_data["video_results"][0]["subtitle_id"],
            "audio_subtitle_id": search_data["audio_results"][0]["subtitle_id"],
        },
    )
    assert sync_response["sync_result"]["offset_ms"] == 574180

    export_response = runtime_call(
        dispatcher,
        "export.csv",
        {"project_id": project_id, "output_path": str(tmp_path / "exports" / "sync_report.csv")},
    )
    assert export_response["row_count"] == 3

    export_xml_response = runtime_call(
        dispatcher,
        "export.fcp7_xml",
        {"project_id": project_id, "output_path": str(tmp_path / "exports" / "sync_report_fcp7.xml")},
    )
    assert export_xml_response["sequence_count"] == 1

    export_json_response = runtime_call(
        dispatcher,
        "export.json",
        {"project_id": project_id, "output_path": str(tmp_path / "exports" / "sync_report.json")},
    )
    assert export_json_response["item_count"] == 3

    export_otio_response = runtime_call(
        dispatcher,
        "export.otio",
        {"project_id": project_id, "output_path": str(tmp_path / "exports" / "sync_report.otio")},
    )
    assert export_otio_response["item_count"] == 2

    export_fcpxml_response = runtime_call(
        dispatcher,
        "export.fcpxml",
        {"project_id": project_id, "output_path": str(tmp_path / "exports" / "sync_report.fcpxml")},
    )
    assert export_fcpxml_response["project_count"] == 1

    export_jobs_response = runtime_call(dispatcher, "export.list_jobs", {"project_id": project_id})
    export_jobs = export_jobs_response["items"]
    assert len(export_jobs) == 5
    assert export_jobs[0]["export_type"] == "fcpxml"
    assert export_jobs[0]["status"] == "succeeded"
    assert export_jobs[1]["export_type"] == "otio"
    assert export_jobs[2]["export_type"] == "json"
    assert export_jobs[3]["export_type"] == "fcp7_xml"
    assert export_jobs[4]["export_type"] == "csv"

    settings_response = runtime_call(
        dispatcher,
        "project.save_settings",
        {
            "project_id": project_id,
            "subtitle_workspace": {
                "query": "继续往前走",
                "video_srt_path": str(sample_root / "subtitles" / "video_flat.srt"),
            },
            "export_workspace": {
                "status_filter": "accepted_auto",
                "source_filter": "auto_text",
                "min_confidence_filter": "0.8",
            },
        },
    )

    reopen_response = runtime_call(
        dispatcher,
        "project.open",
        {"root_path": str(project_root)},
    )
    assert reopen_response["project_settings"]["subtitle_workspace"]["query"] == "继续往前走"
    assert reopen_response["project_settings"]["export_workspace"]["status_filter"] == "accepted_auto"


def runtime_call(
    dispatcher: RuntimeDispatcher,
    method: str,
    payload: dict[str, object],
) -> dict[str, object]:
    response = dispatch_message(
        dispatcher,
        {
            "id": method,
            "method": method,
            "payload": payload,
        },
    )
    assert response["ok"] is True, response
    return response["result"]
