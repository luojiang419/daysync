from __future__ import annotations

import json
from pathlib import Path

import pytest

from daysync_core.errors import DaySyncError
from daysync_core.media import import_media, parse_ffprobe_payload
from daysync_core.timeline import generate_flat_timeline, map_flat_to_source


def _import_video_assets(project: dict[str, object], connection, sample_root: Path) -> list[str]:
    video_one = sample_root / "media" / "A001_C001.mov"
    video_two = sample_root / "media" / "A001_C002.mov"
    payload_one = json.loads((sample_root / "media" / "mock_video_001.json").read_text(encoding="utf-8"))
    payload_two = json.loads((sample_root / "media" / "mock_video_002.json").read_text(encoding="utf-8"))

    imported = import_media(
        connection,
        project["id"],
        [str(video_one), str(video_two)],
        probe_func=lambda path: parse_ffprobe_payload(
            path,
            payload_one if Path(path).name == "A001_C001.mov" else payload_two,
        ),
    )
    return [row["id"] for row in imported["imported"]]


def test_generate_flat_timeline_two_items(
    project_workspace: tuple[dict[str, object], object], sample_root: Path
) -> None:
    project, connection = project_workspace
    media_ids = _import_video_assets(project, connection, sample_root)
    result = generate_flat_timeline(connection, project["id"], "video", media_ids, "filename", 1000)
    assert result["items"][0]["flat_start_ms"] == 0
    assert result["items"][0]["flat_end_ms"] == 10000
    assert result["items"][1]["flat_start_ms"] == 11000
    assert result["items"][1]["flat_end_ms"] == 21000


def test_flat_timeline_media_type_mismatch(
    project_workspace: tuple[dict[str, object], object], sample_root: Path
) -> None:
    project, connection = project_workspace
    media_ids = _import_video_assets(project, connection, sample_root)
    audio_path = sample_root / "media" / "ZOOM0001.wav"
    audio_payload = json.loads((sample_root / "media" / "mock_audio_001.json").read_text(encoding="utf-8"))
    audio_result = import_media(
        connection,
        project["id"],
        [str(audio_path)],
        probe_func=lambda _: parse_ffprobe_payload(audio_path, audio_payload),
    )
    with pytest.raises(DaySyncError) as exc_info:
        generate_flat_timeline(
            connection,
            project["id"],
            "video",
            media_ids + [audio_result["imported"][0]["id"]],
            "manual",
            1000,
        )
    assert exc_info.value.code == "MEDIA_TYPE_MISMATCH"


def test_map_flat_to_source_ok() -> None:
    items = [
        {
            "media_file_id": "one",
            "flat_start_ms": 0,
            "flat_end_ms": 10000,
            "source_start_ms": 0,
            "source_end_ms": 10000,
            "gap_after_ms": 1000,
        },
        {
            "media_file_id": "two",
            "flat_start_ms": 11000,
            "flat_end_ms": 21000,
            "source_start_ms": 0,
            "source_end_ms": 10000,
            "gap_after_ms": 1000,
        },
    ]
    result = map_flat_to_source(items, 12000, 13000)
    assert result["media_file_id"] == "two"
    assert result["source_start_ms"] == 1000
    assert result["source_end_ms"] == 2000


def test_map_flat_to_source_gap() -> None:
    items = [
        {
            "media_file_id": "one",
            "flat_start_ms": 0,
            "flat_end_ms": 10000,
            "source_start_ms": 0,
            "source_end_ms": 10000,
            "gap_after_ms": 1000,
        }
    ]
    result = map_flat_to_source(items, 10050, 10100)
    assert result["mapping_warning"] == "subtitle_in_gap"


def test_map_subtitle_cross_boundary() -> None:
    items = [
        {
            "media_file_id": "one",
            "flat_start_ms": 0,
            "flat_end_ms": 10000,
            "source_start_ms": 0,
            "source_end_ms": 10000,
            "gap_after_ms": 1000,
        }
    ]
    result = map_flat_to_source(items, 9500, 10100)
    assert result["mapping_status"] == "warning"
    assert result["mapping_warning"] == "subtitle_crosses_media_boundary"
