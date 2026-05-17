from __future__ import annotations

import json
from pathlib import Path

import pytest

from daysync_core.errors import DaySyncError
from daysync_core.media import import_media, parse_ffprobe_payload, probe_media


def test_parse_ffprobe_video_json(sample_root: Path) -> None:
    payload = json.loads((sample_root / "media" / "mock_video_001.json").read_text(encoding="utf-8"))
    result = parse_ffprobe_payload(sample_root / "media" / "A001_C001.mov", payload)
    assert result["media_type"] == "video"
    assert result["duration_ms"] == 10000
    assert result["has_video"] is True
    assert result["has_audio"] is True
    assert result["streams"][0]["stream_type"] == "video"


def test_parse_ffprobe_audio_json(sample_root: Path) -> None:
    payload = json.loads((sample_root / "media" / "mock_audio_001.json").read_text(encoding="utf-8"))
    result = parse_ffprobe_payload(sample_root / "media" / "ZOOM0001.wav", payload)
    assert result["media_type"] == "audio"
    assert result["duration_ms"] == 600000
    assert result["has_video"] is False
    assert result["has_audio"] is True


def test_ffprobe_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dummy_file = tmp_path / "missing_ffprobe.mov"
    dummy_file.write_text("placeholder", encoding="utf-8")
    monkeypatch.setattr(
        "daysync_core.media.ffprobe.resolve_ffprobe_binary",
        lambda: (_ for _ in ()).throw(DaySyncError("FFMPEG_NOT_FOUND", "ffprobe executable was not found")),
    )
    with pytest.raises(DaySyncError) as exc_info:
        probe_media(dummy_file)
    assert exc_info.value.code == "FFMPEG_NOT_FOUND"


def test_import_video(project_workspace: tuple[dict[str, object], object], sample_root: Path) -> None:
    project, connection = project_workspace
    source = sample_root / "media" / "A001_C001.mov"
    payload = json.loads((sample_root / "media" / "mock_video_001.json").read_text(encoding="utf-8"))
    result = import_media(
        connection,
        project["id"],
        [str(source)],
        probe_func=lambda _: parse_ffprobe_payload(source, payload),
    )
    assert result["failed"] == []
    assert result["imported"][0]["filename"] == "A001_C001.mov"


def test_import_audio(project_workspace: tuple[dict[str, object], object], sample_root: Path) -> None:
    project, connection = project_workspace
    source = sample_root / "media" / "ZOOM0001.wav"
    payload = json.loads((sample_root / "media" / "mock_audio_001.json").read_text(encoding="utf-8"))
    result = import_media(
        connection,
        project["id"],
        [str(source)],
        probe_func=lambda _: parse_ffprobe_payload(source, payload),
    )
    assert result["imported"][0]["media_type"] == "audio"


def test_import_missing_file(project_workspace: tuple[dict[str, object], object]) -> None:
    project, connection = project_workspace
    result = import_media(connection, project["id"], ["X:/not-found.mov"])
    assert result["failed"][0]["code"] == "MEDIA_FILE_NOT_FOUND"


def test_import_directory_expands_supported_media(
    project_workspace: tuple[dict[str, object], object], tmp_path: Path, sample_root: Path
) -> None:
    project, connection = project_workspace
    video_dir = tmp_path / "video"
    audio_dir = tmp_path / "audio"
    video_dir.mkdir()
    audio_dir.mkdir()
    video_file = video_dir / "A001_C001.mov"
    audio_file = audio_dir / "ZOOM0001.wav"
    video_file.write_text("video", encoding="utf-8")
    audio_file.write_text("audio", encoding="utf-8")
    (video_dir / "notes.txt").write_text("ignore", encoding="utf-8")
    video_payload = json.loads((sample_root / "media" / "mock_video_001.json").read_text(encoding="utf-8"))
    audio_payload = json.loads((sample_root / "media" / "mock_audio_001.json").read_text(encoding="utf-8"))

    def fake_probe(path: Path) -> dict[str, object]:
        if path.name.endswith(".mov"):
            return parse_ffprobe_payload(path, video_payload)
        return parse_ffprobe_payload(path, audio_payload)

    result = import_media(
        connection,
        project["id"],
        [str(video_dir), str(audio_dir)],
        probe_func=fake_probe,
    )

    assert result["failed"] == []
    assert len(result["imported"]) == 2
    assert {item["filename"] for item in result["imported"]} == {"A001_C001.mov", "ZOOM0001.wav"}


def test_import_empty_directory_reports_failure(
    project_workspace: tuple[dict[str, object], object], tmp_path: Path
) -> None:
    project, connection = project_workspace
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    result = import_media(connection, project["id"], [str(empty_dir)])

    assert result["imported"] == []
    assert result["failed"][0]["code"] == "MEDIA_FILE_NOT_FOUND"
