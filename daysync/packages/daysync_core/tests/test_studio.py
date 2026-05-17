from __future__ import annotations

import json
from pathlib import Path

from daysync_core.media import import_media, parse_ffprobe_payload
from daysync_core.studio import get_studio_timeline_snapshot
from daysync_core.subtitles import import_srt
from daysync_core.sync import create_manual_anchor_sync
from daysync_core.timeline import generate_flat_timeline

from .test_sync import _prepare_sync_fixture


def test_studio_snapshot_returns_tracks_subtitles_and_sync_segments(
    project_workspace: tuple[dict[str, object], object], sample_root: Path
) -> None:
    project, connection = project_workspace
    video_subtitle_id, audio_subtitle_id = _prepare_sync_fixture(project, connection, sample_root)
    create_manual_anchor_sync(connection, project["id"], video_subtitle_id, audio_subtitle_id)

    snapshot = get_studio_timeline_snapshot(connection, project["id"])

    assert snapshot["video_timeline"] is not None
    assert snapshot["audio_timeline"] is not None
    assert len(snapshot["video_clips"]) == 1
    assert len(snapshot["audio_clips"]) == 1
    assert len(snapshot["video_subtitles"]) == 2
    assert len(snapshot["audio_subtitles"]) == 2
    assert len(snapshot["sync_segments"]) == 1
    assert snapshot["accepted_sync_summary"]["status"] == "ready"
    assert snapshot["accepted_sync_summary"]["accepted_count"] == 1


def test_studio_snapshot_handles_missing_subtitles_and_sync_gracefully(
    project_workspace: tuple[dict[str, object], object], sample_root: Path
) -> None:
    project, connection = project_workspace
    video_path = sample_root / "media" / "A001_C001.mov"
    audio_path = sample_root / "media" / "ZOOM0001.wav"
    video_payload = json.loads((sample_root / "media" / "mock_video_001.json").read_text(encoding="utf-8"))
    audio_payload = json.loads((sample_root / "media" / "mock_audio_001.json").read_text(encoding="utf-8"))
    imported = import_media(
        connection,
        project["id"],
        [str(video_path), str(audio_path)],
        probe_func=lambda path: parse_ffprobe_payload(
            path,
            video_payload if Path(path).suffix.lower() == ".mov" else audio_payload,
        ),
    )
    video_id = next(item["id"] for item in imported["imported"] if item["media_type"] == "video")
    audio_id = next(item["id"] for item in imported["imported"] if item["media_type"] == "audio")
    generate_flat_timeline(connection, project["id"], "video", [video_id], "filename", 1000)
    generate_flat_timeline(connection, project["id"], "audio", [audio_id], "filename", 1000)

    snapshot = get_studio_timeline_snapshot(connection, project["id"])

    assert snapshot["video_timeline"] is not None
    assert snapshot["audio_timeline"] is not None
    assert snapshot["video_subtitle_track"] is None
    assert snapshot["audio_subtitle_track"] is None
    assert snapshot["video_subtitles"] == []
    assert snapshot["audio_subtitles"] == []
    assert snapshot["sync_segments"] == []
    assert snapshot["accepted_sync_summary"]["status"] == "missing"


def test_studio_snapshot_prefers_latest_timeline(
    project_workspace: tuple[dict[str, object], object], sample_root: Path, tmp_path: Path
) -> None:
    project, connection = project_workspace
    video_path_1 = sample_root / "media" / "A001_C001.mov"
    video_path_2 = sample_root / "media" / "A001_C002.mov"
    audio_path = sample_root / "media" / "ZOOM0001.wav"
    video_payload_1 = json.loads((sample_root / "media" / "mock_video_001.json").read_text(encoding="utf-8"))
    video_payload_2 = json.loads((sample_root / "media" / "mock_video_002.json").read_text(encoding="utf-8"))
    audio_payload = json.loads((sample_root / "media" / "mock_audio_001.json").read_text(encoding="utf-8"))
    imported = import_media(
        connection,
        project["id"],
        [str(video_path_1), str(video_path_2), str(audio_path)],
        probe_func=lambda path: parse_ffprobe_payload(
            path,
            video_payload_1
            if Path(path).name == "A001_C001.mov"
            else video_payload_2
            if Path(path).name == "A001_C002.mov"
            else audio_payload,
        ),
    )
    video_ids = [item["id"] for item in imported["imported"] if item["media_type"] == "video"]
    audio_ids = [item["id"] for item in imported["imported"] if item["media_type"] == "audio"]
    first_video_timeline = generate_flat_timeline(
        connection,
        project["id"],
        "video",
        [video_ids[0]],
        "filename",
        1000,
    )
    second_video_timeline = generate_flat_timeline(
        connection,
        project["id"],
        "video",
        video_ids,
        "filename",
        1000,
    )
    audio_timeline = generate_flat_timeline(
        connection,
        project["id"],
        "audio",
        audio_ids,
        "filename",
        1000,
    )

    video_srt_path = tmp_path / "video_latest.srt"
    video_srt_path.write_text(
        "\n".join(
            [
                "1",
                "00:00:00,000 --> 00:00:01,000",
                "现在开始",
            ]
        ),
        encoding="utf-8",
    )
    audio_srt_path = tmp_path / "audio_latest.srt"
    audio_srt_path.write_text(
        "\n".join(
            [
                "1",
                "00:00:00,000 --> 00:00:01,000",
                "现在开始",
            ]
        ),
        encoding="utf-8",
    )

    import_srt(
        connection,
        project["id"],
        second_video_timeline["flat_timeline_id"],
        "video_ref",
        "srt_import",
        str(video_srt_path),
        "zh-CN",
    )
    import_srt(
        connection,
        project["id"],
        audio_timeline["flat_timeline_id"],
        "external_audio",
        "srt_import",
        str(audio_srt_path),
        "zh-CN",
    )

    snapshot = get_studio_timeline_snapshot(connection, project["id"])

    assert snapshot["video_timeline"]["id"] == second_video_timeline["flat_timeline_id"]
    assert snapshot["video_timeline"]["id"] != first_video_timeline["flat_timeline_id"]
    assert len(snapshot["video_clips"]) == 2
