from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from daysync_core.media import import_media, parse_ffprobe_payload
from daysync_core.search import search_subtitles
from daysync_core.subtitles import import_srt
from daysync_core.timeline import generate_flat_timeline
from daysync_core.utils import utc_now_iso


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


def test_search_subtitles_limit_applies_independently_per_track(
    project_workspace: tuple[dict[str, object], object]
) -> None:
    project, connection = project_workspace
    now = utc_now_iso()
    video_timeline_id = str(uuid4())
    audio_timeline_id = str(uuid4())
    video_track_id = str(uuid4())
    audio_track_id = str(uuid4())
    connection.execute(
        """
        INSERT INTO flat_timelines (id, project_id, media_type, name, gap_ms, sort_mode, created_at)
        VALUES (?, ?, 'video', 'video_flat_timeline', 1000, 'filename', ?)
        """,
        (video_timeline_id, project["id"], now),
    )
    connection.execute(
        """
        INSERT INTO flat_timelines (id, project_id, media_type, name, gap_ms, sort_mode, created_at)
        VALUES (?, ?, 'audio', 'audio_flat_timeline', 1000, 'filename', ?)
        """,
        (audio_timeline_id, project["id"], now),
    )
    connection.execute(
        """
        INSERT INTO subtitle_tracks (
          id, project_id, flat_timeline_id, track_type, source_type, language, original_path, created_at
        )
        VALUES (?, ?, ?, 'video_ref', 'srt_import', 'zh-CN', '', ?)
        """,
        (video_track_id, project["id"], video_timeline_id, now),
    )
    connection.execute(
        """
        INSERT INTO subtitle_tracks (
          id, project_id, flat_timeline_id, track_type, source_type, language, original_path, created_at
        )
        VALUES (?, ?, ?, 'external_audio', 'srt_import', 'zh-CN', '', ?)
        """,
        (audio_track_id, project["id"], audio_timeline_id, now),
    )

    for index in range(25):
        connection.execute(
            """
            INSERT INTO subtitles (
              id, track_id, subtitle_index, flat_start_ms, flat_end_ms,
              source_media_file_id, source_start_ms, source_end_ms,
              raw_text, normalized_text, mapping_status, mapping_warning, created_at
            )
            VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, 'ok', NULL, ?)
            """,
            (
                str(uuid4()),
                audio_track_id,
                index + 1,
                index * 1000,
                index * 1000 + 500,
                index * 1000,
                index * 1000 + 500,
                "我们到了这里",
                "我们到了这里",
                now,
            ),
        )

    for index in range(5):
        connection.execute(
            """
            INSERT INTO subtitles (
              id, track_id, subtitle_index, flat_start_ms, flat_end_ms,
              source_media_file_id, source_start_ms, source_end_ms,
              raw_text, normalized_text, mapping_status, mapping_warning, created_at
            )
            VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, 'ok', NULL, ?)
            """,
            (
                str(uuid4()),
                video_track_id,
                index + 1,
                100_000 + index * 1000,
                100_000 + index * 1000 + 500,
                100_000 + index * 1000,
                100_000 + index * 1000 + 500,
                "我们到了这里",
                "我们到了这里",
                now,
            ),
        )
    connection.commit()

    result = search_subtitles(connection, project["id"], "我们到了这里", 20)

    assert len(result["audio_results"]) == 20
    assert len(result["video_results"]) == 5
