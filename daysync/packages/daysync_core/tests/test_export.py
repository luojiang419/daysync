from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

from daysync_core.export import export_sync_report_csv, export_sync_report_fcp7_xml, list_export_jobs
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


def test_fcp7_xml_export_structure(
    project_workspace: tuple[dict[str, object], object], tmp_path: Path, sample_root: Path
) -> None:
    project, connection = project_workspace
    video_subtitle_id, audio_subtitle_id = _prepare_sync_fixture(project, connection, sample_root)
    create_manual_anchor_sync(connection, project["id"], video_subtitle_id, audio_subtitle_id)
    output_path = tmp_path / "sync_report_fcp7.xml"
    result = export_sync_report_fcp7_xml(connection, project["id"], str(output_path))

    assert result["sequence_count"] == 1
    content = output_path.read_text(encoding="utf-8")
    assert "<!DOCTYPE xmeml>" in content
    root = ET.fromstring(content.split("\n", 2)[2])
    assert root.tag == "xmeml"
    sequence_name = root.find("./project/children/sequence/name")
    assert sequence_name is not None
    assert "A001_C001.mov" in sequence_name.text
    pathurl = root.find(".//pathurl")
    assert pathurl is not None
    assert pathurl.text.startswith("file:///")


def test_list_export_jobs_returns_latest_first(
    project_workspace: tuple[dict[str, object], object], tmp_path: Path, sample_root: Path
) -> None:
    project, connection = project_workspace
    video_subtitle_id, audio_subtitle_id = _prepare_sync_fixture(project, connection, sample_root)
    create_manual_anchor_sync(connection, project["id"], video_subtitle_id, audio_subtitle_id)

    csv_path = tmp_path / "sync_report.csv"
    xml_path = tmp_path / "sync_report_fcp7.xml"
    export_sync_report_csv(connection, project["id"], str(csv_path))
    export_sync_report_fcp7_xml(connection, project["id"], str(xml_path))

    jobs = list_export_jobs(connection, project["id"])

    assert len(jobs) == 2
    assert jobs[0]["export_type"] == "fcp7_xml"
    assert jobs[0]["output_path"] == str(xml_path)
    assert jobs[0]["status"] == "succeeded"
    assert jobs[1]["export_type"] == "csv"
    assert jobs[1]["row_count"] == 1
