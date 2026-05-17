from __future__ import annotations

from pathlib import Path

from daysync_core.export import export_sync_report_csv
from daysync_core.sync import create_manual_anchor_sync

from .test_sync import _prepare_sync_fixture


def test_csv_export_columns(
    project_workspace: tuple[dict[str, object], object], tmp_path: Path, sample_root: Path
) -> None:
    project, connection = project_workspace
    video_subtitle_id, audio_subtitle_id = _prepare_sync_fixture(project, connection, sample_root)
    create_manual_anchor_sync(connection, project["id"], video_subtitle_id, audio_subtitle_id)
    output_path = tmp_path / "sync_report.csv"
    export_sync_report_csv(connection, project["id"], str(output_path))
    header = output_path.read_text(encoding="utf-8").splitlines()[0]
    assert (
        header
        == "sync_result_id,status,source,confidence_score,video_file,video_in_ms,video_out_ms,"
        "audio_file,audio_in_ms,audio_out_ms,offset_ms,video_anchor_text,audio_anchor_text,created_at"
    )


def test_csv_export_utf8(
    project_workspace: tuple[dict[str, object], object], tmp_path: Path, sample_root: Path
) -> None:
    project, connection = project_workspace
    video_subtitle_id, audio_subtitle_id = _prepare_sync_fixture(project, connection, sample_root)
    create_manual_anchor_sync(connection, project["id"], video_subtitle_id, audio_subtitle_id)
    output_path = tmp_path / "sync_report.csv"
    export_sync_report_csv(connection, project["id"], str(output_path))
    content = output_path.read_text(encoding="utf-8")
    assert "我们到了这里" in content
