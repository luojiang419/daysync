from __future__ import annotations

import json
from pathlib import Path

import pytest

from daysync_core.errors import DaySyncError
from daysync_core.media import import_media, parse_ffprobe_payload
from daysync_core.subtitles import import_srt
from daysync_core.sync import (
    analyze_offset_cluster,
    create_cluster_sync_candidate,
    create_manual_anchor_sync,
    list_sync_results,
    list_review_queue,
    recommend_auto_candidates,
    review_sync_result,
)
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
    assert result["candidates"][0]["reverse_match_consistent"] is True
    assert result["candidates"][0]["candidate_margin"] > 0


def test_recommend_auto_candidates_limit(
    project_workspace: tuple[dict[str, object], object], tmp_path: Path, sample_root: Path
) -> None:
    project, connection = project_workspace
    video_subtitle_id = _prepare_context_recommendation_fixture(project, connection, tmp_path, sample_root)
    result = recommend_auto_candidates(connection, project["id"], video_subtitle_id, limit=1, context_radius=1)

    assert result["limit"] == 1
    assert len(result["candidates"]) == 1


def test_analyze_offset_cluster_passes_with_three_inliers(
    project_workspace: tuple[dict[str, object], object], tmp_path: Path, sample_root: Path
) -> None:
    project, connection = project_workspace
    pair_ids = _prepare_cluster_fixture(project, connection, tmp_path, sample_root)
    result = analyze_offset_cluster(
        connection,
        project["id"],
        pairs=[
            {
                "video_subtitle_id": pair_ids["video_1"],
                "audio_subtitle_id": pair_ids["audio_good_1"],
            },
            {
                "video_subtitle_id": pair_ids["video_2"],
                "audio_subtitle_id": pair_ids["audio_good_2"],
            },
            {
                "video_subtitle_id": pair_ids["video_3"],
                "audio_subtitle_id": pair_ids["audio_good_3"],
            },
            {
                "video_subtitle_id": pair_ids["video_3"],
                "audio_subtitle_id": pair_ids["audio_bad"],
            },
        ],
        tolerance_ms=500,
        min_inlier_ratio=0.6,
        min_anchor_count=3,
        context_radius=1,
    )

    assert result["cluster_summary"]["passes"] is True
    assert result["cluster_summary"]["final_offset_ms"] == 574180
    assert result["cluster_summary"]["inlier_count"] == 3
    assert result["cluster_summary"]["candidate_count"] == 4
    outlier = next(item for item in result["pair_analyses"] if item["audio_subtitle_id"] == pair_ids["audio_bad"])
    assert outlier["is_inlier"] is False
    assert outlier["reverse_match_consistent"] is False


def test_analyze_offset_cluster_fails_when_not_enough_pairs(
    project_workspace: tuple[dict[str, object], object], tmp_path: Path, sample_root: Path
) -> None:
    project, connection = project_workspace
    pair_ids = _prepare_cluster_fixture(project, connection, tmp_path, sample_root)
    result = analyze_offset_cluster(
        connection,
        project["id"],
        pairs=[
            {
                "video_subtitle_id": pair_ids["video_1"],
                "audio_subtitle_id": pair_ids["audio_good_1"],
            },
            {
                "video_subtitle_id": pair_ids["video_2"],
                "audio_subtitle_id": pair_ids["audio_good_2"],
            },
        ],
        tolerance_ms=500,
        min_inlier_ratio=0.6,
        min_anchor_count=3,
        context_radius=1,
    )

    assert result["cluster_summary"]["passes"] is False
    assert "not_enough_anchor_pairs" in result["cluster_summary"]["reasons"]


def test_create_cluster_sync_candidate_and_list_review_queue(
    project_workspace: tuple[dict[str, object], object], tmp_path: Path, sample_root: Path
) -> None:
    project, connection = project_workspace
    pair_ids = _prepare_cluster_fixture(project, connection, tmp_path, sample_root)
    create_cluster_sync_candidate(
        connection,
        project["id"],
        pairs=[
            {
                "video_subtitle_id": pair_ids["video_1"],
                "audio_subtitle_id": pair_ids["audio_good_1"],
            },
            {
                "video_subtitle_id": pair_ids["video_2"],
                "audio_subtitle_id": pair_ids["audio_good_2"],
            },
            {
                "video_subtitle_id": pair_ids["video_3"],
                "audio_subtitle_id": pair_ids["audio_good_3"],
            },
        ],
    )

    queue = list_review_queue(connection, project["id"])
    assert len(queue) == 1
    assert queue[0]["status"] == "needs_review"
    assert queue[0]["confidence_breakdown"]["cluster_summary"]["passes"] is True


def test_review_sync_result_accept_adjust_and_reject(
    project_workspace: tuple[dict[str, object], object], tmp_path: Path, sample_root: Path
) -> None:
    project, connection = project_workspace
    pair_ids = _prepare_cluster_fixture(project, connection, tmp_path, sample_root)
    created = create_cluster_sync_candidate(
        connection,
        project["id"],
        pairs=[
            {
                "video_subtitle_id": pair_ids["video_1"],
                "audio_subtitle_id": pair_ids["audio_good_1"],
            },
            {
                "video_subtitle_id": pair_ids["video_2"],
                "audio_subtitle_id": pair_ids["audio_good_2"],
            },
            {
                "video_subtitle_id": pair_ids["video_3"],
                "audio_subtitle_id": pair_ids["audio_good_3"],
            },
        ],
    )
    sync_result_id = created["sync_result"]["id"]

    accepted = review_sync_result(connection, project["id"], sync_result_id, "accepted")
    assert accepted["sync_result"]["status"] == "accepted_auto"
    assert accepted["review_event"]["event_type"] == "accepted"

    second_created = create_cluster_sync_candidate(
        connection,
        project["id"],
        pairs=[
            {
                "video_subtitle_id": pair_ids["video_1"],
                "audio_subtitle_id": pair_ids["audio_good_1"],
            }
        ],
    )
    adjusted = review_sync_result(
        connection,
        project["id"],
        second_created["sync_result"]["id"],
        "adjusted",
        new_offset_ms=574280,
    )
    assert adjusted["sync_result"]["status"] == "accepted_manual"
    assert adjusted["sync_result"]["offset_ms"] == 574280

    third_created = create_cluster_sync_candidate(
        connection,
        project["id"],
        pairs=[
            {
                "video_subtitle_id": pair_ids["video_2"],
                "audio_subtitle_id": pair_ids["audio_good_2"],
            }
        ],
    )
    rejected = review_sync_result(connection, project["id"], third_created["sync_result"]["id"], "rejected")
    assert rejected["sync_result"]["status"] == "rejected"
    assert rejected["review_event"]["event_type"] == "rejected"


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


def _prepare_cluster_fixture(
    project: dict[str, object], connection, tmp_path: Path, sample_root: Path
) -> dict[str, str]:
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

    video_srt_path = tmp_path / "video_cluster.srt"
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
    audio_srt_path = tmp_path / "audio_cluster.srt"
    audio_srt_path.write_text(
        "\n".join(
            [
                "1",
                "00:00:09,34,180".replace(",", ":"),  # placeholder line replaced below
            ]
        ),
        encoding="utf-8",
    )
    audio_srt_path.write_text(
        "\n".join(
            [
                "1",
                "00:00:10,000 --> 00:00:11,000",
                "先等等",
                "",
                "2",
                "00:09:34,180 --> 00:09:35,180",
                "现在开始",
                "",
                "3",
                "00:09:35,680 --> 00:09:37,180",
                "我们到了这里",
                "",
                "4",
                "00:09:37,680 --> 00:09:38,680",
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

    subtitle_rows = connection.execute(
        """
        SELECT s.id, st.track_type, s.subtitle_index
        FROM subtitles s
        JOIN subtitle_tracks st ON st.id = s.track_id
        WHERE st.project_id = ?
        ORDER BY st.track_type, s.subtitle_index
        """,
        (project["id"],),
    ).fetchall()

    return {
        "video_1": next(row["id"] for row in subtitle_rows if row["track_type"] == "video_ref" and row["subtitle_index"] == 1),
        "video_2": next(row["id"] for row in subtitle_rows if row["track_type"] == "video_ref" and row["subtitle_index"] == 2),
        "video_3": next(row["id"] for row in subtitle_rows if row["track_type"] == "video_ref" and row["subtitle_index"] == 3),
        "audio_bad": next(row["id"] for row in subtitle_rows if row["track_type"] == "external_audio" and row["subtitle_index"] == 1),
        "audio_good_1": next(row["id"] for row in subtitle_rows if row["track_type"] == "external_audio" and row["subtitle_index"] == 2),
        "audio_good_2": next(row["id"] for row in subtitle_rows if row["track_type"] == "external_audio" and row["subtitle_index"] == 3),
        "audio_good_3": next(row["id"] for row in subtitle_rows if row["track_type"] == "external_audio" and row["subtitle_index"] == 4),
    }
