from __future__ import annotations

import json
from pathlib import Path

import pytest

from daysync_core.errors import DaySyncError
from daysync_core.media import import_media, parse_ffprobe_payload
from daysync_core.subtitles import import_srt
from daysync_core.sync import create_manual_anchor_sync, list_sync_results, recommend_auto_candidates
from daysync_core.timeline import generate_flat_timeline


def _prepare_sync_fixture(project: dict[str, object], connection, sample_root: Path) -> tuple[str, str]:
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
    subtitles = connection.execute(
        """
        SELECT s.id, st.track_type
        FROM subtitles s
        JOIN subtitle_tracks st ON st.id = s.track_id
        ORDER BY s.created_at, s.subtitle_index
        """
    ).fetchall()
    video_subtitle_id = next(row["id"] for row in subtitles if row["track_type"] == "video_ref")
    audio_subtitle_id = next(row["id"] for row in subtitles if row["track_type"] == "external_audio")
    return video_subtitle_id, audio_subtitle_id


def test_manual_anchor_offset(
    project_workspace: tuple[dict[str, object], object], sample_root: Path
) -> None:
    project, connection = project_workspace
    video_subtitle_id, audio_subtitle_id = _prepare_sync_fixture(project, connection, sample_root)
    result = create_manual_anchor_sync(connection, project["id"], video_subtitle_id, audio_subtitle_id)
    assert result["offset_ms"] == 574180
    assert result["status"] == "accepted_manual"


def test_manual_anchor_rejects_unmapped(project_workspace: tuple[dict[str, object], object]) -> None:
    project, connection = project_workspace
    with pytest.raises(DaySyncError) as exc_info:
        create_manual_anchor_sync(connection, project["id"], "missing-video", "missing-audio")
    assert exc_info.value.code == "ANCHOR_SUBTITLE_INVALID"


def test_list_sync_results(project_workspace: tuple[dict[str, object], object], sample_root: Path) -> None:
    project, connection = project_workspace
    video_subtitle_id, audio_subtitle_id = _prepare_sync_fixture(project, connection, sample_root)
    create_manual_anchor_sync(connection, project["id"], video_subtitle_id, audio_subtitle_id)
    rows = list_sync_results(connection, project["id"])
    assert rows[0]["video_anchor_text"] == "我们到了这里"


def test_recommend_auto_candidates_prefers_context_match(
    project_workspace: tuple[dict[str, object], object], tmp_path: Path, sample_root: Path
) -> None:
    project, connection = project_workspace
    video_subtitle_id = _prepare_context_recommendation_fixture(project, connection, tmp_path, sample_root)
    result = recommend_auto_candidates(connection, project["id"], video_subtitle_id, limit=3, context_radius=1)

    assert result["target_track_type"] == "external_audio"
    assert result["candidates"][0]["raw_text"] == "我们到了这里"
    assert result["candidates"][0]["source_start_ms"] == 575180
    assert result["candidates"][0]["context_similarity"] > result["candidates"][1]["context_similarity"]
    assert result["candidates"][0]["final_score"] > result["candidates"][1]["final_score"]


def test_recommend_auto_candidates_limit(
    project_workspace: tuple[dict[str, object], object], tmp_path: Path, sample_root: Path
) -> None:
    project, connection = project_workspace
    video_subtitle_id = _prepare_context_recommendation_fixture(project, connection, tmp_path, sample_root)
    result = recommend_auto_candidates(connection, project["id"], video_subtitle_id, limit=1, context_radius=1)

    assert result["limit"] == 1
    assert len(result["candidates"]) == 1


def _prepare_context_recommendation_fixture(
    project: dict[str, object], connection, tmp_path: Path, sample_root: Path
) -> str:
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

    video_srt_path = tmp_path / "video_context.srt"
    video_srt_path.write_text(
        "\n".join(
            [
                "1",
                "00:00:00,000 --> 00:00:01,000",
                "现在开始",
                "",
                "2",
                "00:00:01,500 --> 00:00:03,000",
                "我们到了这里",
                "",
                "3",
                "00:00:03,500 --> 00:00:04,500",
                "继续往前走",
                "",
            ]
        ),
        encoding="utf-8",
    )
    audio_srt_path = tmp_path / "audio_context.srt"
    audio_srt_path.write_text(
        "\n".join(
            [
                "1",
                "00:00:10,000 --> 00:00:11,000",
                "先等等",
                "",
                "2",
                "00:00:11,500 --> 00:00:13,000",
                "我们到了这里",
                "",
                "3",
                "00:00:13,500 --> 00:00:14,500",
                "先回去吧",
                "",
                "4",
                "00:09:34,000 --> 00:09:35,000",
                "现在开始",
                "",
                "5",
                "00:09:35,180 --> 00:09:36,680",
                "我们到了这里",
                "",
                "6",
                "00:09:39,000 --> 00:09:40,000",
                "继续往前走",
                "",
            ]
        ),
        encoding="utf-8",
    )

    import_srt(
        connection,
        project["id"],
        video_timeline["flat_timeline_id"],
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
    row = connection.execute(
        """
        SELECT s.id
        FROM subtitles s
        JOIN subtitle_tracks st ON st.id = s.track_id
        WHERE st.project_id = ? AND st.track_type = 'video_ref' AND s.subtitle_index = 2
        """,
        (project["id"],),
    ).fetchone()
    assert row is not None
    return row["id"]
