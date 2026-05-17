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
from daysync_core.media import import_media, parse_ffprobe_payload
from daysync_core.subtitles import import_srt
from daysync_core.sync import create_manual_anchor_sync
from daysync_core.timeline import generate_flat_timeline

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
    assert "DaySync Synced Timeline" in sequence_name.text
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


def test_fcp7_xml_export_uses_single_sequence_for_multi_segment_track_sync(
    project_workspace: tuple[dict[str, object], object], tmp_path: Path, sample_root: Path
) -> None:
    project, connection = project_workspace
    _prepare_multi_segment_export_fixture(project, connection, tmp_path, sample_root)
    output_path = tmp_path / "sync_report_fcp7.xml"

    result = export_sync_report_fcp7_xml(connection, project["id"], str(output_path))

    assert result["sequence_count"] == 1
    root = ET.fromstring(output_path.read_text(encoding="utf-8").split("\n", 2)[2])
    assert len(root.findall("./project/children/sequence")) == 1
    assert len(root.findall(".//media/video/track/clipitem")) == 2
    assert len(root.findall(".//media/audio/track/clipitem")) == 2


def test_fcpxml_export_uses_single_project_for_multi_segment_track_sync(
    project_workspace: tuple[dict[str, object], object], tmp_path: Path, sample_root: Path
) -> None:
    project, connection = project_workspace
    _prepare_multi_segment_export_fixture(project, connection, tmp_path, sample_root)
    output_path = tmp_path / "sync_report.fcpxml"

    result = export_sync_report_fcpxml(connection, project["id"], str(output_path))

    assert result["project_count"] == 1
    root = ET.fromstring(output_path.read_text(encoding="utf-8").split("\n", 2)[2])
    assert len(root.findall("./event/project")) == 1
    assert len(root.findall("./event/project/sequence/spine/asset-clip")) == 2


def test_otio_export_uses_continuous_track_sync_segments(
    project_workspace: tuple[dict[str, object], object], tmp_path: Path, sample_root: Path
) -> None:
    project, connection = project_workspace
    _prepare_multi_segment_export_fixture(project, connection, tmp_path, sample_root)
    output_path = tmp_path / "sync_report.otio"

    result = export_sync_report_otio(connection, project["id"], str(output_path))

    assert result["item_count"] == 2
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    video_children = payload["tracks"]["children"][0]["children"]
    audio_children = payload["tracks"]["children"][1]["children"]
    assert len([item for item in video_children if item["OTIO_SCHEMA"] == "Clip.2"]) == 2
    assert len([item for item in audio_children if item["OTIO_SCHEMA"] == "Clip.2"]) == 2


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


def _prepare_multi_segment_export_fixture(
    project: dict[str, object],
    connection,
    tmp_path: Path,
    sample_root: Path,
) -> None:
    video_path_1 = sample_root / "media" / "A001_C001.mov"
    video_path_2 = sample_root / "media" / "A001_C002.mov"
    audio_path = sample_root / "media" / "ZOOM0001.wav"
    video_payload_1 = json.loads((sample_root / "media" / "mock_video_001.json").read_text(encoding="utf-8"))
    video_payload_2 = json.loads((sample_root / "media" / "mock_video_002.json").read_text(encoding="utf-8"))
    audio_payload = json.loads((sample_root / "media" / "mock_audio_001.json").read_text(encoding="utf-8"))
    imported = import_media(
        connection,
        project["id"],
        [str(video_path_1), str(video_path_2), str(audio_path)],
        probe_func=lambda path: parse_ffprobe_payload(
            path,
            video_payload_1
            if Path(path).name == "A001_C001.mov"
            else video_payload_2
            if Path(path).name == "A001_C002.mov"
            else audio_payload,
        ),
    )
    video_ids = [item["id"] for item in imported["imported"] if item["media_type"] == "video"]
    audio_ids = [item["id"] for item in imported["imported"] if item["media_type"] == "audio"]
    video_timeline = generate_flat_timeline(connection, project["id"], "video", video_ids, "filename", 1000)
    audio_timeline = generate_flat_timeline(connection, project["id"], "audio", audio_ids, "filename", 1000)

    anchor_offset_ms = 574180
    first_video_anchor_ms = 1000
    second_video_anchor_ms = int(video_timeline["items"][1]["flat_start_ms"]) + 500
    video_srt_path = tmp_path / "video_track_sync.srt"
    video_srt_path.write_text(
        "\n".join(
            [
                "1",
                f"{_format_srt_timestamp(first_video_anchor_ms)} --> {_format_srt_timestamp(first_video_anchor_ms + 1000)}",
                "我们到了这里",
                "",
                "2",
                f"{_format_srt_timestamp(second_video_anchor_ms)} --> {_format_srt_timestamp(second_video_anchor_ms + 1000)}",
                "继续往前走",
                "",
            ]
        ),
        encoding="utf-8",
    )
    audio_srt_path = tmp_path / "audio_track_sync.srt"
    audio_srt_path.write_text(
        "\n".join(
            [
                "1",
                f"{_format_srt_timestamp(first_video_anchor_ms + anchor_offset_ms)} --> {_format_srt_timestamp(first_video_anchor_ms + anchor_offset_ms + 1000)}",
                "我们到了这里",
                "",
                "2",
                f"{_format_srt_timestamp(second_video_anchor_ms + anchor_offset_ms)} --> {_format_srt_timestamp(second_video_anchor_ms + anchor_offset_ms + 1000)}",
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
    video_subtitle_id = next(
        row["id"]
        for row in subtitle_rows
        if row["track_type"] == "video_ref" and row["subtitle_index"] == 1
    )
    audio_subtitle_id = next(
        row["id"]
        for row in subtitle_rows
        if row["track_type"] == "external_audio" and row["subtitle_index"] == 1
    )
    create_manual_anchor_sync(connection, project["id"], video_subtitle_id, audio_subtitle_id)


def _format_srt_timestamp(value_ms: int) -> str:
    hours = value_ms // 3_600_000
    minutes = (value_ms % 3_600_000) // 60_000
    seconds = (value_ms % 60_000) // 1_000
    milliseconds = value_ms % 1_000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
