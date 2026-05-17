from __future__ import annotations

import json
from pathlib import Path
import xml.etree.ElementTree as ET

from daysync_core.export import (
    export_sync_report_csv,
    export_sync_report_fcpxml,
    export_sync_report_fcp7_xml,
    export_sync_report_json,
    export_sync_report_otio,
    list_export_jobs,
)
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


def test_json_export_contains_sync_results(
    project_workspace: tuple[dict[str, object], object], tmp_path: Path, sample_root: Path
) -> None:
    project, connection = project_workspace
    video_subtitle_id, audio_subtitle_id = _prepare_sync_fixture(project, connection, sample_root)
    create_manual_anchor_sync(connection, project["id"], video_subtitle_id, audio_subtitle_id)
    output_path = tmp_path / "sync_report.json"

    result = export_sync_report_json(connection, project["id"], str(output_path))

    assert result["item_count"] == 1
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["project_id"] == project["id"]
    assert payload["item_count"] == 1
    assert payload["sync_results"][0]["video_anchor_text"] == "我们到了这里"
    assert payload["sync_results"][0]["audio_anchor_text"] == "我们到了这里"


def test_otio_export_builds_timeline_structure(
    project_workspace: tuple[dict[str, object], object], tmp_path: Path, sample_root: Path
) -> None:
    project, connection = project_workspace
    video_subtitle_id, audio_subtitle_id = _prepare_sync_fixture(project, connection, sample_root)
    create_manual_anchor_sync(connection, project["id"], video_subtitle_id, audio_subtitle_id)
    output_path = tmp_path / "sync_report.otio"

    result = export_sync_report_otio(connection, project["id"], str(output_path))

    assert result["item_count"] == 1
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["OTIO_SCHEMA"] == "Timeline.1"
    assert payload["tracks"]["OTIO_SCHEMA"] == "Stack.1"
    assert len(payload["tracks"]["children"]) == 2
    assert payload["tracks"]["children"][0]["kind"] == "Video"
    assert payload["tracks"]["children"][1]["kind"] == "Audio"
    assert payload["tracks"]["children"][0]["children"][0]["OTIO_SCHEMA"] == "Clip.2"
    assert (
        payload["tracks"]["children"][0]["children"][0]["media_references"]["DEFAULT_MEDIA"]["target_url"]
        .startswith("file:///")
    )


def test_fcpxml_export_builds_project_collection(
    project_workspace: tuple[dict[str, object], object], tmp_path: Path, sample_root: Path
) -> None:
    project, connection = project_workspace
    video_subtitle_id, audio_subtitle_id = _prepare_sync_fixture(project, connection, sample_root)
    create_manual_anchor_sync(connection, project["id"], video_subtitle_id, audio_subtitle_id)
    output_path = tmp_path / "sync_report.fcpxml"

    result = export_sync_report_fcpxml(connection, project["id"], str(output_path))

    assert result["project_count"] == 1
    content = output_path.read_text(encoding="utf-8")
    assert "<!DOCTYPE fcpxml>" in content
    root = ET.fromstring(content.split("\n", 2)[2])
    assert root.tag == "fcpxml"
    event = root.find("./event")
    assert event is not None
    project_node = root.find("./event/project")
    assert project_node is not None
    sequence = root.find("./event/project/sequence")
    assert sequence is not None
    assert sequence.attrib["format"].startswith("r_video_format_")
    primary_clip = root.find(".//spine/asset-clip")
    assert primary_clip is not None
    assert primary_clip.attrib["srcEnable"] in {"video", "audio"}
    nested_clip = primary_clip.find("./asset-clip")
    assert nested_clip is not None
    assert nested_clip.attrib["srcEnable"] in {"video", "audio"}


def test_list_export_jobs_returns_latest_first(
    project_workspace: tuple[dict[str, object], object], tmp_path: Path, sample_root: Path
) -> None:
    project, connection = project_workspace
    video_subtitle_id, audio_subtitle_id = _prepare_sync_fixture(project, connection, sample_root)
    create_manual_anchor_sync(connection, project["id"], video_subtitle_id, audio_subtitle_id)

    csv_path = tmp_path / "sync_report.csv"
    xml_path = tmp_path / "sync_report_fcp7.xml"
    json_path = tmp_path / "sync_report.json"
    otio_path = tmp_path / "sync_report.otio"
    fcpxml_path = tmp_path / "sync_report.fcpxml"
    export_sync_report_csv(connection, project["id"], str(csv_path))
    export_sync_report_fcp7_xml(connection, project["id"], str(xml_path))
    export_sync_report_json(connection, project["id"], str(json_path))
    export_sync_report_otio(connection, project["id"], str(otio_path))
    export_sync_report_fcpxml(connection, project["id"], str(fcpxml_path))

    jobs = list_export_jobs(connection, project["id"])

    assert len(jobs) == 5
    assert jobs[0]["export_type"] == "fcpxml"
    assert jobs[0]["output_path"] == str(fcpxml_path)
    assert jobs[0]["status"] == "succeeded"
    assert jobs[1]["export_type"] == "otio"
    assert jobs[2]["export_type"] == "json"
    assert jobs[3]["export_type"] == "fcp7_xml"
    assert jobs[4]["export_type"] == "csv"
    assert jobs[4]["row_count"] == 1
