from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
import xml.etree.ElementTree as ET

from daysync_core.errors import DaySyncError
from daysync_core.utils import new_uuid, utc_now_iso


CSV_COLUMNS = [
    "sync_result_id",
    "status",
    "source",
    "confidence_score",
    "video_file",
    "video_in_ms",
    "video_out_ms",
    "audio_file",
    "audio_in_ms",
    "audio_out_ms",
    "offset_ms",
    "video_anchor_text",
    "audio_anchor_text",
    "created_at",
]


def list_export_jobs(connection: sqlite3.Connection, project_id: str) -> list[dict[str, object]]:
    rows = connection.execute(
        """
        SELECT id, project_id, export_type, output_path, status, row_count, error_message, created_at, completed_at
        FROM export_jobs
        WHERE project_id = ?
        ORDER BY created_at DESC, rowid DESC
        """,
        (project_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def export_sync_report_csv(connection: sqlite3.Connection, project_id: str, output_path: str) -> dict[str, object]:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    export_job_id = new_uuid()
    created_at = utc_now_iso()
    connection.execute(
        """
        INSERT INTO export_jobs (id, project_id, export_type, output_path, status, created_at)
        VALUES (?, ?, 'csv', ?, 'running', ?)
        """,
        (export_job_id, project_id, str(target), created_at),
    )
    rows = connection.execute(
        """
        SELECT sr.id AS sync_result_id, sr.status, sr.source, sr.confidence_score,
               vm.filename AS video_file, sr.video_in_ms, sr.video_out_ms,
               am.filename AS audio_file, sr.audio_in_ms, sr.audio_out_ms, sr.offset_ms,
               vs.raw_text AS video_anchor_text, aus.raw_text AS audio_anchor_text, sr.created_at
        FROM sync_results sr
        JOIN media_files vm ON vm.id = sr.video_media_file_id
        JOIN media_files am ON am.id = sr.audio_media_file_id
        LEFT JOIN subtitles vs ON vs.id = sr.video_anchor_subtitle_id
        LEFT JOIN subtitles aus ON aus.id = sr.audio_anchor_subtitle_id
        WHERE sr.project_id = ?
          AND sr.status IN ('accepted_manual', 'accepted_auto')
        ORDER BY sr.created_at
        """,
        (project_id,),
    ).fetchall()

    try:
        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))
    except OSError as exc:
        connection.execute(
            """
            UPDATE export_jobs
            SET status = 'failed', error_message = ?, completed_at = ?
            WHERE id = ?
            """,
            (str(exc), utc_now_iso(), export_job_id),
        )
        connection.commit()
        raise DaySyncError("EXPORT_FAILED", f"Failed to export CSV: {exc}") from exc

    connection.execute(
        """
        UPDATE export_jobs
        SET status = 'succeeded', row_count = ?, completed_at = ?
        WHERE id = ?
        """,
        (len(rows), utc_now_iso(), export_job_id),
    )
    connection.commit()
    return {"output_path": str(target), "row_count": len(rows)}


def export_sync_report_fcp7_xml(
    connection: sqlite3.Connection, project_id: str, output_path: str
) -> dict[str, object]:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    export_job_id = new_uuid()
    created_at = utc_now_iso()
    connection.execute(
        """
        INSERT INTO export_jobs (id, project_id, export_type, output_path, status, created_at)
        VALUES (?, ?, 'fcp7_xml', ?, 'running', ?)
        """,
        (export_job_id, project_id, str(target), created_at),
    )
    rows = connection.execute(
        """
        SELECT sr.id AS sync_result_id, sr.status, sr.source, sr.confidence_score,
               sr.video_media_file_id, sr.audio_media_file_id,
               sr.video_in_ms, sr.video_out_ms, sr.audio_in_ms, sr.audio_out_ms, sr.offset_ms,
               vm.filename AS video_file, vm.original_path AS video_path, vm.duration_ms AS video_duration_ms,
               am.filename AS audio_file, am.original_path AS audio_path, am.duration_ms AS audio_duration_ms,
               vs.raw_text AS video_anchor_text, aus.raw_text AS audio_anchor_text
        FROM sync_results sr
        JOIN media_files vm ON vm.id = sr.video_media_file_id
        JOIN media_files am ON am.id = sr.audio_media_file_id
        LEFT JOIN subtitles vs ON vs.id = sr.video_anchor_subtitle_id
        LEFT JOIN subtitles aus ON aus.id = sr.audio_anchor_subtitle_id
        WHERE sr.project_id = ?
          AND sr.status IN ('accepted_manual', 'accepted_auto')
        ORDER BY sr.created_at
        """,
        (project_id,),
    ).fetchall()

    try:
        xml_content = _build_fcp7_xml(connection, project_id, rows)
        target.write_text(xml_content, encoding="utf-8")
    except OSError as exc:
        connection.execute(
            """
            UPDATE export_jobs
            SET status = 'failed', error_message = ?, completed_at = ?
            WHERE id = ?
            """,
            (str(exc), utc_now_iso(), export_job_id),
        )
        connection.commit()
        raise DaySyncError("EXPORT_FAILED", f"Failed to export FCP 7 XML: {exc}") from exc

    connection.execute(
        """
        UPDATE export_jobs
        SET status = 'succeeded', row_count = ?, completed_at = ?
        WHERE id = ?
        """,
        (len(rows), utc_now_iso(), export_job_id),
    )
    connection.commit()
    return {"output_path": str(target), "sequence_count": len(rows)}


def _build_fcp7_xml(
    connection: sqlite3.Connection, project_id: str, rows: list[sqlite3.Row]
) -> str:
    root = ET.Element("xmeml", version="5")
    project = ET.SubElement(root, "project")
    ET.SubElement(project, "name").text = f"DaySync Export {project_id}"
    children = ET.SubElement(project, "children")

    for row in rows:
        sequence = ET.SubElement(children, "sequence", id=f"sequence-{row['sync_result_id']}")
        _append_text(sequence, "name", f"{row['video_file']}__{row['audio_file']}")
        video_rate = _load_video_rate(connection, row["video_media_file_id"])
        timebase, ntsc_flag = _format_rate(video_rate)
        rate_node = ET.SubElement(sequence, "rate")
        _append_text(rate_node, "timebase", str(timebase))
        _append_text(rate_node, "ntsc", "TRUE" if ntsc_flag else "FALSE")

        layout = _build_sequence_layout(row, video_rate)
        _append_text(sequence, "duration", str(layout["sequence_duration_frames"]))
        timecode = ET.SubElement(sequence, "timecode")
        timecode_rate = ET.SubElement(timecode, "rate")
        _append_text(timecode_rate, "timebase", str(timebase))
        _append_text(timecode_rate, "ntsc", "TRUE" if ntsc_flag else "FALSE")
        _append_text(timecode, "string", "00:00:00:00")
        _append_text(timecode, "frame", "0")
        _append_text(timecode, "displayformat", "NDF")

        media = ET.SubElement(sequence, "media")
        video = ET.SubElement(media, "video")
        track = ET.SubElement(video, "track")
        video_clip_id = f"{row['sync_result_id']}-video"
        audio_clip_id = f"{row['sync_result_id']}-audio"
        video_clipitem = ET.SubElement(track, "clipitem", id=video_clip_id)
        _append_text(video_clipitem, "name", row["video_file"])
        _append_text(video_clipitem, "duration", str(_ms_to_frames(row["video_duration_ms"], video_rate)))
        _append_text(video_clipitem, "start", str(layout["video_timeline_start_frames"]))
        _append_text(video_clipitem, "end", str(layout["video_timeline_end_frames"]))
        _append_text(video_clipitem, "in", str(layout["video_in_frames"]))
        _append_text(video_clipitem, "out", str(layout["video_out_frames"]))
        _append_link(video_clipitem, video_clip_id)
        _append_link(video_clipitem, audio_clip_id)
        _append_sourcetrack(video_clipitem, "video", 1)
        _append_file_reference(
            video_clipitem,
            file_id=f"file-{row['sync_result_id']}-video",
            name=row["video_file"],
            original_path=row["video_path"],
            duration_ms=row["video_duration_ms"],
            rate=video_rate,
            stream_info=_load_video_stream(connection, row["video_media_file_id"]),
            mediatype="video",
        )

        audio = ET.SubElement(media, "audio")
        audio_track = ET.SubElement(audio, "track")
        audio_clipitem = ET.SubElement(audio_track, "clipitem", id=audio_clip_id)
        _append_text(audio_clipitem, "name", row["audio_file"])
        _append_text(audio_clipitem, "duration", str(_ms_to_frames(row["audio_duration_ms"], video_rate)))
        _append_text(audio_clipitem, "start", str(layout["audio_timeline_start_frames"]))
        _append_text(audio_clipitem, "end", str(layout["audio_timeline_end_frames"]))
        _append_text(audio_clipitem, "in", str(layout["audio_in_frames"]))
        _append_text(audio_clipitem, "out", str(layout["audio_out_frames"]))
        _append_link(audio_clipitem, video_clip_id)
        _append_link(audio_clipitem, audio_clip_id)
        _append_sourcetrack(audio_clipitem, "audio", 1)
        _append_file_reference(
            audio_clipitem,
            file_id=f"file-{row['sync_result_id']}-audio",
            name=row["audio_file"],
            original_path=row["audio_path"],
            duration_ms=row["audio_duration_ms"],
            rate=video_rate,
            stream_info=_load_audio_stream(connection, row["audio_media_file_id"]),
            mediatype="audio",
        )

    xml_body = ET.tostring(root, encoding="unicode")
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n{xml_body}\n'


def _build_sequence_layout(row: sqlite3.Row, rate: float) -> dict[str, int]:
    video_duration_ms = row["video_out_ms"] - row["video_in_ms"]
    audio_duration_ms = row["audio_out_ms"] - row["audio_in_ms"]
    if row["audio_in_ms"] < 0:
        video_timeline_start_ms = abs(row["audio_in_ms"])
        audio_timeline_start_ms = 0
        audio_in_ms = 0
        video_in_ms = row["video_in_ms"]
    elif row["video_in_ms"] < 0:
        audio_timeline_start_ms = abs(row["video_in_ms"])
        video_timeline_start_ms = 0
        video_in_ms = 0
        audio_in_ms = row["audio_in_ms"]
    else:
        video_timeline_start_ms = 0
        audio_timeline_start_ms = 0
        video_in_ms = row["video_in_ms"]
        audio_in_ms = row["audio_in_ms"]

    video_timeline_end_ms = video_timeline_start_ms + video_duration_ms
    audio_timeline_end_ms = audio_timeline_start_ms + audio_duration_ms
    sequence_duration_ms = max(video_timeline_end_ms, audio_timeline_end_ms)
    return {
        "video_timeline_start_frames": _ms_to_frames(video_timeline_start_ms, rate),
        "video_timeline_end_frames": _ms_to_frames(video_timeline_end_ms, rate),
        "audio_timeline_start_frames": _ms_to_frames(audio_timeline_start_ms, rate),
        "audio_timeline_end_frames": _ms_to_frames(audio_timeline_end_ms, rate),
        "video_in_frames": _ms_to_frames(video_in_ms, rate),
        "video_out_frames": _ms_to_frames(row["video_out_ms"], rate),
        "audio_in_frames": _ms_to_frames(audio_in_ms, rate),
        "audio_out_frames": _ms_to_frames(max(row["audio_out_ms"], 0), rate),
        "sequence_duration_frames": _ms_to_frames(sequence_duration_ms, rate),
    }


def _append_file_reference(
    clipitem: ET.Element,
    *,
    file_id: str,
    name: str,
    original_path: str,
    duration_ms: int,
    rate: float,
    stream_info: dict[str, int],
    mediatype: str,
) -> None:
    file_node = ET.SubElement(clipitem, "file", id=file_id)
    _append_text(file_node, "name", name)
    _append_text(file_node, "pathurl", Path(original_path).as_uri())
    _append_text(file_node, "duration", str(_ms_to_frames(duration_ms, rate)))
    timebase, ntsc_flag = _format_rate(rate)
    rate_node = ET.SubElement(file_node, "rate")
    _append_text(rate_node, "timebase", str(timebase))
    _append_text(rate_node, "ntsc", "TRUE" if ntsc_flag else "FALSE")
    media_node = ET.SubElement(file_node, "media")
    if mediatype == "video":
        video_node = ET.SubElement(media_node, "video")
        sample = ET.SubElement(video_node, "samplecharacteristics")
        _append_text(sample, "width", str(stream_info.get("width", 1920)))
        _append_text(sample, "height", str(stream_info.get("height", 1080)))
    else:
        audio_node = ET.SubElement(media_node, "audio")
        sample = ET.SubElement(audio_node, "samplecharacteristics")
        _append_text(sample, "depth", "16")
        _append_text(sample, "samplerate", str(stream_info.get("sample_rate", 48000)))


def _append_sourcetrack(node: ET.Element, mediatype: str, trackindex: int) -> None:
    sourcetrack = ET.SubElement(node, "sourcetrack")
    _append_text(sourcetrack, "mediatype", mediatype)
    _append_text(sourcetrack, "trackindex", str(trackindex))


def _append_link(node: ET.Element, linkclipref: str) -> None:
    link = ET.SubElement(node, "link")
    _append_text(link, "linkclipref", linkclipref)


def _append_text(parent: ET.Element, tag: str, value: str) -> ET.Element:
    node = ET.SubElement(parent, tag)
    node.text = value
    return node


def _load_video_rate(connection: sqlite3.Connection, media_file_id: str) -> float:
    row = connection.execute(
        """
        SELECT frame_rate_num, frame_rate_den
        FROM media_streams
        WHERE media_file_id = ? AND stream_type = 'video'
        ORDER BY stream_index
        LIMIT 1
        """,
        (media_file_id,),
    ).fetchone()
    if row is None or not row["frame_rate_num"] or not row["frame_rate_den"]:
        return 25.0
    return row["frame_rate_num"] / row["frame_rate_den"]


def _load_video_stream(connection: sqlite3.Connection, media_file_id: str) -> dict[str, int]:
    row = connection.execute(
        """
        SELECT width, height
        FROM media_streams
        WHERE media_file_id = ? AND stream_type = 'video'
        ORDER BY stream_index
        LIMIT 1
        """,
        (media_file_id,),
    ).fetchone()
    return dict(row) if row is not None else {"width": 1920, "height": 1080}


def _load_audio_stream(connection: sqlite3.Connection, media_file_id: str) -> dict[str, int]:
    row = connection.execute(
        """
        SELECT sample_rate
        FROM media_streams
        WHERE media_file_id = ? AND stream_type = 'audio'
        ORDER BY stream_index
        LIMIT 1
        """,
        (media_file_id,),
    ).fetchone()
    return dict(row) if row is not None else {"sample_rate": 48000}


def _ms_to_frames(value_ms: int | float, rate: float) -> int:
    return int(round((float(value_ms) / 1000.0) * rate))


def _format_rate(rate: float) -> tuple[int, bool]:
    rounded = round(rate, 3)
    if abs(rounded - 29.97) < 0.01:
        return 30, True
    if abs(rounded - 23.976) < 0.01:
        return 24, True
    if abs(rounded - 59.94) < 0.01:
        return 60, True
    return max(1, int(round(rate))), False
