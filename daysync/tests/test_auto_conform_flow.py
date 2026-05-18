from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from daysync_core.bridge import RuntimeDispatcher, RuntimeState, dispatch_message


def test_auto_conform_preview_and_apply_generate_full_day_sync_results(
    monkeypatch,
    tmp_path: Path,
) -> None:
    sample_root = Path(__file__).resolve().parents[1] / "sample_data"
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
    project_id = runtime_call(
        dispatcher,
        "project.create",
        {
            "name": "自动整日合板测试",
            "root_path": str(project_root),
            "shooting_date": "2026-05-18",
        },
    )["project"]["id"]

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

    video_srt = tmp_path / "video_auto_flat.srt"
    video_srt.write_text(
        "\n".join(
            [
                "1",
                "00:00:01,000 --> 00:00:02,500",
                "我们到了这里",
                "",
                "2",
                "00:00:05,000 --> 00:00:06,000",
                "继续往前走",
                "",
                "3",
                "00:00:12,000 --> 00:00:13,000",
                "已经接近出口",
                "",
            ]
        ),
        encoding="utf-8",
    )
    audio_srt = tmp_path / "audio_auto_flat.srt"
    audio_srt.write_text(
        "\n".join(
            [
                "1",
                "00:09:35,180 --> 00:09:36,680",
                "我们到了这里",
                "",
                "2",
                "00:09:39,120 --> 00:09:40,120",
                "继续往前走",
                "",
                "3",
                "00:09:46,200 --> 00:09:47,200",
                "已经接近出口",
                "",
            ]
        ),
        encoding="utf-8",
    )

    runtime_call(
        dispatcher,
        "subtitle.import",
        {
            "project_id": project_id,
            "flat_timeline_id": video_timeline["flat_timeline_id"],
            "track_type": "video_ref",
            "source_type": "srt_import",
            "path": str(video_srt),
            "language": "zh-CN",
        },
    )
    runtime_call(
        dispatcher,
        "subtitle.import",
        {
            "project_id": project_id,
            "flat_timeline_id": audio_timeline["flat_timeline_id"],
            "track_type": "external_audio",
            "source_type": "srt_import",
            "path": str(audio_srt),
            "language": "zh-CN",
        },
    )

    studio_snapshot = runtime_call(dispatcher, "studio.timeline", {"project_id": project_id})
    assert studio_snapshot["auto_conform_readiness"]["status"] == "ready"
    assert len(studio_snapshot["video_source_subtitle_groups"]) == 2
    assert len(studio_snapshot["audio_source_subtitle_groups"]) == 1

    preview_response = runtime_call(
        dispatcher,
        "sync.auto_conform_preview",
        {
            "project_id": project_id,
            "context_radius": 1,
            "min_anchor_count": 3,
            "tolerance_ms": 500,
            "min_inlier_ratio": 0.6,
        },
    )
    assert preview_response["ready_to_apply"] is True
    assert preview_response["auto_accept_decision"]["eligible"] is True
    assert preview_response["cluster_summary"]["passes"] is True
    assert preview_response["cluster_summary"]["final_offset_ms"] is not None
    assert len(preview_response["anchor_pairs"]) == 3
    assert len(preview_response["preview_segments"]) >= 2

    sync_results_before_apply = runtime_call(dispatcher, "sync.list_results", {"project_id": project_id})
    assert sync_results_before_apply["sync_results"] == []

    apply_response = runtime_call(
        dispatcher,
        "sync.apply_auto_conform",
        {
            "project_id": project_id,
            "offset_ms": preview_response["cluster_summary"]["final_offset_ms"],
            "representative_video_subtitle_id": preview_response["representative_pair"]["video_subtitle_id"],
            "representative_audio_subtitle_id": preview_response["representative_pair"]["audio_subtitle_id"],
        },
    )
    assert apply_response["generated_count"] >= 2
    assert apply_response["sync_result_summary"]["source"] == "auto_text"
    assert apply_response["sync_result_summary"]["status"] == "accepted_auto"

    sync_results_after_apply = runtime_call(dispatcher, "sync.list_results", {"project_id": project_id})
    assert sync_results_after_apply["sync_results"]
    assert all(item["source"] == "auto_text" for item in sync_results_after_apply["sync_results"])

    export_premiere = runtime_call(
        dispatcher,
        "export.fcp7_xml",
        {"project_id": project_id, "output_path": str(tmp_path / "exports" / "premiere.xml")},
    )
    export_davinci = runtime_call(
        dispatcher,
        "export.fcpxml",
        {"project_id": project_id, "output_path": str(tmp_path / "exports" / "davinci.fcpxml")},
    )
    assert export_premiere["sequence_count"] == 1
    assert export_davinci["project_count"] == 1


def test_xml_export_requires_confirmed_sync_results(monkeypatch, tmp_path: Path) -> None:
    sample_root = Path(__file__).resolve().parents[1] / "sample_data"
    fixtures = {
        "A001_C001.mov": json.loads((sample_root / "media" / "mock_video_001.json").read_text(encoding="utf-8")),
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
    project_id = runtime_call(
        dispatcher,
        "project.create",
        {
            "name": "导出前校验",
            "root_path": str(tmp_path / "empty_project"),
            "shooting_date": "2026-05-18",
        },
    )["project"]["id"]

    export_response = dispatch_message(
        dispatcher,
        {
            "id": "export.fcp7_xml",
            "method": "export.fcp7_xml",
            "payload": {
                "project_id": project_id,
                "output_path": str(tmp_path / "exports" / "empty.xml"),
            },
        },
    )
    assert export_response["ok"] is False
    assert export_response["error"]["code"] == "EXPORT_FAILED"
    assert "需先确认自动合板结果" in export_response["error"]["message"]


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
