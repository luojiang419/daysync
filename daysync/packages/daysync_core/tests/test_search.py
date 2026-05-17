from __future__ import annotations

import json
from pathlib import Path

from daysync_core.media import import_media, parse_ffprobe_payload
from daysync_core.search import search_subtitles
from daysync_core.subtitles import import_srt
from daysync_core.timeline import generate_flat_timeline


def test_search_subtitles_grouped(
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
    video_timeline = generate_flat_timeline(connection, project["id"], "video", [video_id], "filename", 1000)
    audio_timeline = generate_flat_timeline(connection, project["id"], "audio", [audio_id], "filename", 1000)
    import_srt(
        connection,
        project["id"],
        video_timeline["flat_timeline_id"],
        "video_ref",
        "srt_import",
        str(sample_root / "subtitles" / "video_flat.srt"),
        "zh-CN",
    )
    import_srt(
        connection,
        project["id"],
        audio_timeline["flat_timeline_id"],
        "external_audio",
        "srt_import",
        str(sample_root / "subtitles" / "audio_flat.srt"),
        "zh-CN",
    )
    result = search_subtitles(connection, project["id"], "我们到了这里", 20)
    assert len(result["video_results"]) == 1
    assert len(result["audio_results"]) == 1
    assert result["video_results"][0]["source_start_ms"] == 1000


def test_search_subtitles_limit(
    project_workspace: tuple[dict[str, object], object], sample_root: Path
) -> None:
    project, connection = project_workspace
    video_path = sample_root / "media" / "A001_C001.mov"
    video_payload = json.loads((sample_root / "media" / "mock_video_001.json").read_text(encoding="utf-8"))
    imported = import_media(
        connection,
        project["id"],
        [str(video_path)],
        probe_func=lambda _: parse_ffprobe_payload(video_path, video_payload),
    )
    video_timeline = generate_flat_timeline(
        connection, project["id"], "video", [imported["imported"][0]["id"]], "filename", 1000
    )
    import_srt(
        connection,
        project["id"],
        video_timeline["flat_timeline_id"],
        "video_ref",
        "srt_import",
        str(sample_root / "subtitles" / "video_flat.srt"),
        "zh-CN",
    )
    result = search_subtitles(connection, project["id"], "这里", 1)
    assert len(result["video_results"]) == 1
