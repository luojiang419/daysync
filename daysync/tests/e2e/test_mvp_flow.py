from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from services.api.main import app


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
        "services.api.main.ensure_ffmpeg_runtime",
        lambda: SimpleNamespace(to_dict=lambda: fake_ffmpeg_status),
    )
    monkeypatch.setattr(
        "services.api.routes.media.ensure_ffmpeg_runtime",
        lambda: SimpleNamespace(to_dict=lambda: fake_ffmpeg_status),
    )

    client = TestClient(app)
    project_root = tmp_path / "project"
    create_response = client.post(
        "/api/projects",
        json={
            "name": "纪录片样片 2026-01-01",
            "root_path": str(project_root),
            "shooting_date": "2026-01-01",
        },
    )
    assert create_response.status_code == 200
    project_id = create_response.json()["project"]["id"]

    media_import = client.post(
        f"/api/projects/{project_id}/media/import",
        json={
            "paths": [
                str(sample_root / "media" / "A001_C001.mov"),
                str(sample_root / "media" / "A001_C002.mov"),
                str(sample_root / "media" / "ZOOM0001.wav"),
            ],
            "session_id": None,
        },
    )
    assert media_import.status_code == 200
    imported = media_import.json()["imported"]
    video_ids = [item["id"] for item in imported if item["media_type"] == "video"]
    audio_ids = [item["id"] for item in imported if item["media_type"] == "audio"]

    video_timeline = client.post(
        f"/api/projects/{project_id}/flat-timelines",
        json={"media_type": "video", "media_file_ids": video_ids, "sort_mode": "filename", "gap_ms": 1000},
    )
    audio_timeline = client.post(
        f"/api/projects/{project_id}/flat-timelines",
        json={"media_type": "audio", "media_file_ids": audio_ids, "sort_mode": "filename", "gap_ms": 1000},
    )
    assert video_timeline.status_code == 200
    assert audio_timeline.status_code == 200

    video_subtitles = client.post(
        f"/api/projects/{project_id}/subtitles/import",
        json={
            "flat_timeline_id": video_timeline.json()["flat_timeline_id"],
            "track_type": "video_ref",
            "source_type": "srt_import",
            "path": str(sample_root / "subtitles" / "video_flat.srt"),
            "language": "zh-CN",
        },
    )
    audio_subtitles = client.post(
        f"/api/projects/{project_id}/subtitles/import",
        json={
            "flat_timeline_id": audio_timeline.json()["flat_timeline_id"],
            "track_type": "external_audio",
            "source_type": "srt_import",
            "path": str(sample_root / "subtitles" / "audio_flat.srt"),
            "language": "zh-CN",
        },
    )
    assert video_subtitles.json()["imported_count"] == 2
    assert audio_subtitles.json()["imported_count"] == 2

    search_response = client.get(
        f"/api/projects/{project_id}/subtitles/search",
        params={"q": "我们到了这里", "limit": 20},
    )
    assert search_response.status_code == 200
    search_data = search_response.json()
    assert len(search_data["video_results"]) == 1
    assert len(search_data["audio_results"]) == 1

    auto_candidates_response = client.post(
        f"/api/projects/{project_id}/sync/auto-candidates",
        json={
            "anchor_subtitle_id": search_data["video_results"][0]["subtitle_id"],
            "limit": 3,
            "context_radius": 1,
        },
    )
    assert auto_candidates_response.status_code == 200
    assert auto_candidates_response.json()["candidates"][0]["subtitle_id"] == search_data["audio_results"][0]["subtitle_id"]

    offset_cluster_response = client.post(
        f"/api/projects/{project_id}/sync/offset-cluster",
        json={
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
    assert offset_cluster_response.status_code == 200
    assert offset_cluster_response.json()["cluster_summary"]["candidate_count"] == 1

    cluster_candidate_response = client.post(
        f"/api/projects/{project_id}/sync/cluster-candidate",
        json={
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
    assert cluster_candidate_response.status_code == 200
    candidate_sync_result_id = cluster_candidate_response.json()["sync_result"]["id"]

    review_queue_response = client.get(f"/api/projects/{project_id}/sync/review-queue")
    assert review_queue_response.status_code == 200
    assert review_queue_response.json()["items"][0]["id"] == candidate_sync_result_id

    review_response = client.post(
        f"/api/projects/{project_id}/sync/results/{candidate_sync_result_id}/review",
        json={"action": "accepted", "new_offset_ms": None, "note": None},
    )
    assert review_response.status_code == 200
    assert review_response.json()["sync_result"]["status"] == "accepted_auto"

    sync_response = client.post(
        f"/api/projects/{project_id}/sync/manual-anchor",
        json={
            "video_subtitle_id": search_data["video_results"][0]["subtitle_id"],
            "audio_subtitle_id": search_data["audio_results"][0]["subtitle_id"],
        },
    )
    assert sync_response.status_code == 200
    assert sync_response.json()["sync_result"]["offset_ms"] == 574180

    export_response = client.post(
        f"/api/projects/{project_id}/exports/csv",
        json={"output_path": str(tmp_path / "exports" / "sync_report.csv")},
    )
    assert export_response.status_code == 200
    assert export_response.json()["row_count"] == 2
