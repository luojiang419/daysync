from __future__ import annotations

from pathlib import Path

from daysync_core.db import (
    connect_database,
    create_project,
    database_path_for_project,
    project_snapshot,
    save_project_settings,
)


def test_project_snapshot_returns_default_settings(tmp_path: Path) -> None:
    root_path = tmp_path / "project"
    create_project(str(root_path), "测试项目", "2026-05-17")
    snapshot = project_snapshot(str(root_path))
    assert snapshot["project_settings"]["subtitle_workspace"]["query"] == ""
    assert snapshot["project_settings"]["export_workspace"]["status_filter"] == "all"


def test_project_settings_persist_across_snapshot(tmp_path: Path) -> None:
    root_path = tmp_path / "project"
    project = create_project(str(root_path), "测试项目", "2026-05-17")
    with connect_database(database_path_for_project(root_path)) as connection:
        save_project_settings(
            connection,
            project["id"],
            {
                "subtitle_workspace": {
                    "query": "我们到了这里",
                    "video_srt_path": "D:\\subs\\video.srt",
                    "cluster_samples": [
                        {
                            "video_subtitle_id": "video-1",
                            "video_text": "我们到了这里",
                            "video_source_filename": "A001.mov",
                            "audio_subtitle_id": "audio-1",
                            "audio_text": "我们到了这里",
                            "audio_source_filename": "ZOOM0001.wav",
                        }
                    ],
                },
                "export_workspace": {
                    "status_filter": "accepted_auto",
                    "source_filter": "auto_text",
                    "min_confidence_filter": "0.8",
                },
            },
        )

    snapshot = project_snapshot(str(root_path))
    assert snapshot["project_settings"]["subtitle_workspace"]["query"] == "我们到了这里"
    assert snapshot["project_settings"]["subtitle_workspace"]["video_srt_path"] == "D:\\subs\\video.srt"
    assert snapshot["project_settings"]["export_workspace"]["status_filter"] == "accepted_auto"
    assert snapshot["project_settings"]["export_workspace"]["source_filter"] == "auto_text"
