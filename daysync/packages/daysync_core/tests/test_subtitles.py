from __future__ import annotations

import json
from pathlib import Path

import pytest

from daysync_core.errors import DaySyncError
from daysync_core.media import import_media, parse_ffprobe_payload
from daysync_core.subtitles import import_srt, normalize_subtitle_text, parse_srt
from daysync_core.timeline import generate_flat_timeline


def test_srt_parse_basic() -> None:
    content = "1\n00:00:00,000 --> 00:00:01,500\n你好世界\n"
    parsed = parse_srt(content)
    assert parsed[0].flat_start_ms == 0
    assert parsed[0].flat_end_ms == 1500
    assert parsed[0].raw_text == "你好世界"


def test_srt_parse_multiline() -> None:
    content = "1\n00:00:00,000 --> 00:00:01,500\n第一行\n第二行\n"
    parsed = parse_srt(content)
    assert parsed[0].raw_text == "第一行\n第二行"


def test_srt_parse_invalid() -> None:
    with pytest.raises(DaySyncError) as exc_info:
        parse_srt("1\ninvalid\n文本\n")
    assert exc_info.value.code == "SUBTITLE_PARSE_FAILED"


def test_normalize_chinese_text() -> None:
    assert normalize_subtitle_text("我当时，就觉着这地方不对。") == "我当时就觉着这地方不对"


def test_normalize_mixed_text() -> None:
    assert normalize_subtitle_text("  Hello，世界！ ") == "hello世界"


def test_import_srt_and_map(project_workspace: tuple[dict[str, object], object], sample_root: Path) -> None:
    project, connection = project_workspace
    video_path = sample_root / "media" / "A001_C001.mov"
    video_payload = json.loads((sample_root / "media" / "mock_video_001.json").read_text(encoding="utf-8"))
    imported = import_media(
        connection,
        project["id"],
        [str(video_path)],
        probe_func=lambda _: parse_ffprobe_payload(video_path, video_payload),
    )
    timeline = generate_flat_timeline(
        connection, project["id"], "video", [imported["imported"][0]["id"]], "filename", 1000
    )
    result = import_srt(
        connection,
        project["id"],
        timeline["flat_timeline_id"],
        "video_ref",
        "srt_import",
        str(sample_root / "subtitles" / "video_flat.srt"),
        "zh-CN",
    )
    assert result["imported_count"] == 2
    row = connection.execute(
        "SELECT source_start_ms, source_end_ms, mapping_status FROM subtitles ORDER BY subtitle_index LIMIT 1"
    ).fetchone()
    assert row["source_start_ms"] == 1000
    assert row["source_end_ms"] == 2500
    assert row["mapping_status"] == "ok"


def test_import_srt_cross_boundary_warning(
    project_workspace: tuple[dict[str, object], object], tmp_path: Path, sample_root: Path
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
    timeline = generate_flat_timeline(
        connection, project["id"], "video", [imported["imported"][0]["id"]], "filename", 1000
    )
    srt_path = tmp_path / "cross.srt"
    srt_path.write_text(
        "1\n00:00:09,500 --> 00:00:10,500\n跨边界字幕\n",
        encoding="utf-8",
    )
    result = import_srt(
        connection,
        project["id"],
        timeline["flat_timeline_id"],
        "video_ref",
        "srt_import",
        str(srt_path),
        "zh-CN",
    )
    assert result["warning_count"] == 1
