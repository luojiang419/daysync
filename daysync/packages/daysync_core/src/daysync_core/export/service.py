from __future__ import annotations

import csv
import json
import math
import sqlite3
from pathlib import Path
import xml.etree.ElementTree as ET

from daysync_core.errors import DaySyncError
from daysync_core.studio import get_studio_timeline_snapshot
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
    rows = _load_sync_export_rows(connection, project_id)

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


def export_sync_report_json(connection: sqlite3.Connection, project_id: str, output_path: str) -> dict[str, object]:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    export_job_id = new_uuid()
    created_at = utc_now_iso()
    connection.execute(
        """
        INSERT INTO export_jobs (id, project_id, export_type, output_path, status, created_at)
        VALUES (?, ?, 'json', ?, 'running', ?)
        """,
        (export_job_id, project_id, str(target), created_at),
    )
    rows = _load_sync_export_rows(connection, project_id)
    payload = {
        "project_id": project_id,
        "exported_at": created_at,
        "item_count": len(rows),
        "sync_results": [dict(row) for row in rows],
    }

    try:
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
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
        raise DaySyncError("EXPORT_FAILED", f"Failed to export JSON: {exc}") from exc

    connection.execute(
        """
        UPDATE export_jobs
        SET status = 'succeeded', row_count = ?, completed_at = ?
        WHERE id = ?
        """,
        (len(rows), utc_now_iso(), export_job_id),
    )
    connection.commit()
    return {"output_path": str(target), "item_count": len(rows)}


def export_sync_report_otio(connection: sqlite3.Connection, project_id: str, output_path: str) -> dict[str, object]:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    export_job_id = new_uuid()
    created_at = utc_now_iso()
    connection.execute(
        """
        INSERT INTO export_jobs (id, project_id, export_type, output_path, status, created_at)
        VALUES (?, ?, 'otio', ?, 'running', ?)
        """,
        (export_job_id, project_id, str(target), created_at),
    )
    segments = _load_continuous_export_segments(connection, project_id)

    try:
        otio_payload = _build_otio_timeline(connection, project_id, segments, created_at)
        target.write_text(json.dumps(otio_payload, ensure_ascii=False, indent=2), encoding="utf-8")
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
        raise DaySyncError("EXPORT_FAILED", f"Failed to export OTIO: {exc}") from exc

    connection.execute(
        """
        UPDATE export_jobs
        SET status = 'succeeded', row_count = ?, completed_at = ?
        WHERE id = ?
        """,
        (len(segments), utc_now_iso(), export_job_id),
    )
    connection.commit()
    return {"output_path": str(target), "item_count": len(segments)}


def export_sync_report_fcpxml(connection: sqlite3.Connection, project_id: str, output_path: str) -> dict[str, object]:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    export_job_id = new_uuid()
    created_at = utc_now_iso()
    connection.execute(
        """
        INSERT INTO export_jobs (id, project_id, export_type, output_path, status, created_at)
        VALUES (?, ?, 'fcpxml', ?, 'running', ?)
        """,
        (export_job_id, project_id, str(target), created_at),
    )
    segments = _load_continuous_export_segments(connection, project_id)

    try:
        fcpxml_content = _build_fcpxml(connection, project_id, segments)
        target.write_text(fcpxml_content, encoding="utf-8")
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
        raise DaySyncError("EXPORT_FAILED", f"Failed to export FCPXML: {exc}") from exc

    connection.execute(
        """
        UPDATE export_jobs
        SET status = 'succeeded', row_count = ?, completed_at = ?
        WHERE id = ?
        """,
        (_project_count_for_segments(segments), utc_now_iso(), export_job_id),
    )
    connection.commit()
    return {"output_path": str(target), "project_count": _project_count_for_segments(segments)}


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
    segments = _load_continuous_export_segments(connection, project_id)

    try:
        xml_content = _build_fcp7_xml(connection, project_id, segments)
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
        (_sequence_count_for_segments(segments), utc_now_iso(), export_job_id),
    )
    connection.commit()
    return {"output_path": str(target), "sequence_count": _sequence_count_for_segments(segments)}


def _load_sync_export_rows(connection: sqlite3.Connection, project_id: str) -> list[sqlite3.Row]:
    return connection.execute(
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


def _load_rich_sync_export_rows(connection: sqlite3.Connection, project_id: str) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT sr.id AS sync_result_id, sr.status, sr.source, sr.confidence_score,
               sr.video_media_file_id, sr.audio_media_file_id,
               sr.video_in_ms, sr.video_out_ms, sr.audio_in_ms, sr.audio_out_ms, sr.offset_ms,
               vm.filename AS video_file, vm.original_path AS video_path, vm.duration_ms AS video_duration_ms,
               vm.has_video AS video_has_video, vm.has_audio AS video_has_audio,
               am.filename AS audio_file, am.original_path AS audio_path, am.duration_ms AS audio_duration_ms,
               am.has_video AS audio_has_video, am.has_audio AS audio_has_audio,
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


def _load_continuous_export_segments(
    connection: sqlite3.Connection,
    project_id: str,
) -> list[dict[str, object]]:
    snapshot = get_studio_timeline_snapshot(connection, project_id)
    sync_segments = snapshot["sync_segments"]
    if not sync_segments:
        return []

    sync_result_rows = connection.execute(
        """
        SELECT sr.id, sr.confidence_score, sr.status, sr.source, sr.created_at, sr.updated_at,
               vs.raw_text AS video_anchor_text, aus.raw_text AS audio_anchor_text
        FROM sync_results sr
        LEFT JOIN subtitles vs ON vs.id = sr.video_anchor_subtitle_id
        LEFT JOIN subtitles aus ON aus.id = sr.audio_anchor_subtitle_id
        WHERE sr.id IN ({placeholders})
        """.format(placeholders=",".join("?" for _ in sync_segments)),
        [segment["sync_result_id"] for segment in sync_segments],
    ).fetchall()
    sync_result_by_id = {row["id"]: dict(row) for row in sync_result_rows}

    media_ids = sorted(
        {
            *[segment["video_media_file_id"] for segment in sync_segments],
            *[segment["audio_media_file_id"] for segment in sync_segments],
        }
    )
    media_rows = connection.execute(
        """
        SELECT id, duration_ms, has_video, has_audio, filename, original_path
        FROM media_files
        WHERE id IN ({placeholders})
        """.format(placeholders=",".join("?" for _ in media_ids)),
        media_ids,
    ).fetchall()
    media_by_id = {row["id"]: dict(row) for row in media_rows}

    segments: list[dict[str, object]] = []
    for segment in sync_segments:
        sync_result = sync_result_by_id[segment["sync_result_id"]]
        video_media = media_by_id[segment["video_media_file_id"]]
        audio_media = media_by_id[segment["audio_media_file_id"]]
        timeline_start_ms = int(segment["video_flat_start_ms"])
        timeline_end_ms = int(segment["video_flat_end_ms"])
        segments.append(
            {
                **segment,
                "confidence_score": sync_result["confidence_score"],
                "status": sync_result["status"],
                "source": sync_result["source"],
                "video_anchor_text": sync_result["video_anchor_text"],
                "audio_anchor_text": sync_result["audio_anchor_text"],
                "created_at": sync_result["created_at"],
                "updated_at": sync_result["updated_at"],
                "timeline_start_ms": timeline_start_ms,
                "timeline_end_ms": timeline_end_ms,
                "timeline_duration_ms": timeline_end_ms - timeline_start_ms,
                "video_duration_ms": int(video_media["duration_ms"]),
                "video_has_video": int(video_media["has_video"]),
                "video_has_audio": int(video_media["has_audio"]),
                "video_file": video_media["filename"],
                "video_path": video_media["original_path"],
                "audio_duration_ms": int(audio_media["duration_ms"]),
                "audio_has_video": int(audio_media["has_video"]),
                "audio_has_audio": int(audio_media["has_audio"]),
                "audio_file": audio_media["filename"],
                "audio_path": audio_media["original_path"],
            }
        )
    return sorted(
        segments,
        key=lambda item: (item["timeline_start_ms"], item["timeline_end_ms"], item["sync_result_id"]),
    )


def _build_fcpxml(connection: sqlite3.Connection, project_id: str, segments: list[dict[str, object]]) -> str:
    root = ET.Element("fcpxml", version="1.10")
    resources = ET.SubElement(root, "resources")
    audio_format_id = "r_audio_format"
    ET.SubElement(resources, "format", id=audio_format_id, name="FFFrameRateUndefined")
    event = ET.SubElement(root, "event", name=f"DaySync Export {project_id}")

    if segments:
        first_segment = segments[0]
        rate_num, rate_den = _load_video_rate_info(connection, first_segment["video_media_file_id"])
        video_stream = _load_video_stream(connection, first_segment["video_media_file_id"])
        sequence_format_id = "r_video_format_main"
        format_attrs = {
            "id": sequence_format_id,
            "frameDuration": _rate_to_fcpx_time(rate_num, rate_den),
            "width": str(video_stream.get("width", 1920)),
            "height": str(video_stream.get("height", 1080)),
            "fieldOrder": "progressive",
        }
        predefined_name = _guess_fcpx_format_name(
            int(video_stream.get("width", 1920)),
            int(video_stream.get("height", 1080)),
            rate_num,
            rate_den,
        )
        if predefined_name:
            format_attrs["name"] = predefined_name
        ET.SubElement(resources, "format", **format_attrs)
        asset_maps = _append_fcpxml_assets(
            connection=connection,
            resources=resources,
            segments=segments,
            sequence_format_id=sequence_format_id,
            audio_format_id=audio_format_id,
        )

        project = ET.SubElement(
            event,
            "project",
            name=f"DaySync Synced Timeline {project_id}",
            id="project_main",
        )
        sequence_duration_ms = max(int(segment["timeline_end_ms"]) for segment in segments)
        sequence = ET.SubElement(
            project,
            "sequence",
            format=sequence_format_id,
            duration=_ms_to_fcpx_time(sequence_duration_ms),
            tcStart="0s",
            tcFormat="NDF",
        )
        spine = ET.SubElement(sequence, "spine")
        for segment in segments:
            _append_fcpxml_continuous_pair(
                spine=spine,
                segment=segment,
                video_asset_id=asset_maps["video"][segment["video_media_file_id"]],
                audio_asset_id=asset_maps["audio"][segment["audio_media_file_id"]],
                video_role="video",
                audio_role="dialogue",
            )

    xml_body = ET.tostring(root, encoding="unicode")
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n{xml_body}\n'


def _append_fcpxml_assets(
    *,
    connection: sqlite3.Connection,
    resources: ET.Element,
    segments: list[dict[str, object]],
    sequence_format_id: str,
    audio_format_id: str,
) -> dict[str, dict[str, str]]:
    video_asset_ids: dict[str, str] = {}
    audio_asset_ids: dict[str, str] = {}
    for index, media_file_id in enumerate(_ordered_unique_ids(segments, "video_media_file_id"), start=1):
        segment = next(item for item in segments if item["video_media_file_id"] == media_file_id)
        video_audio_stream = _load_audio_stream(connection, media_file_id)
        video_asset_id = f"r_video_asset_{index}"
        video_asset_ids[media_file_id] = video_asset_id
        video_asset = ET.SubElement(
            resources,
            "asset",
            id=video_asset_id,
            name=segment["video_file"],
            start="0s",
            duration=_ms_to_fcpx_time(segment["video_duration_ms"]),
            hasVideo="1" if segment["video_has_video"] else "0",
            hasAudio="1" if segment["video_has_audio"] else "0",
            format=sequence_format_id,
            audioSources="1",
            audioChannels=str(video_audio_stream.get("channels", 2)),
            audioRate=str(video_audio_stream.get("sample_rate", 48000)),
        )
        ET.SubElement(video_asset, "media-rep", kind="original-media", src=Path(segment["video_path"]).as_uri())

    for index, media_file_id in enumerate(_ordered_unique_ids(segments, "audio_media_file_id"), start=1):
        segment = next(item for item in segments if item["audio_media_file_id"] == media_file_id)
        audio_stream = _load_audio_stream(connection, media_file_id)
        audio_asset_id = f"r_audio_asset_{index}"
        audio_asset_ids[media_file_id] = audio_asset_id
        audio_asset = ET.SubElement(
            resources,
            "asset",
            id=audio_asset_id,
            name=segment["audio_file"],
            start="0s",
            duration=_ms_to_fcpx_time(segment["audio_duration_ms"]),
            hasVideo="1" if segment["audio_has_video"] else "0",
            hasAudio="1" if segment["audio_has_audio"] else "0",
            format=audio_format_id,
            audioSources="1",
            audioChannels=str(audio_stream.get("channels", 2)),
            audioRate=str(audio_stream.get("sample_rate", 48000)),
        )
        ET.SubElement(audio_asset, "media-rep", kind="original-media", src=Path(segment["audio_path"]).as_uri())

    return {"video": video_asset_ids, "audio": audio_asset_ids}


def _append_fcpxml_continuous_pair(
    *,
    spine: ET.Element,
    segment: dict[str, object],
    video_asset_id: str,
    audio_asset_id: str,
    video_role: str,
    audio_role: str,
) -> None:
    duration_ms = int(segment["timeline_duration_ms"])
    primary = ET.SubElement(
        spine,
        "asset-clip",
        name=segment["video_file"],
        ref=video_asset_id,
        offset=_ms_to_fcpx_time(segment["timeline_start_ms"]),
        start=_ms_to_fcpx_time(segment["video_in_ms"]),
        duration=_ms_to_fcpx_time(duration_ms),
        srcEnable="video",
        videoRole=video_role,
    )
    ET.SubElement(
        primary,
        "asset-clip",
        name=segment["audio_file"],
        ref=audio_asset_id,
        lane="-1",
        offset="0s",
        start=_ms_to_fcpx_time(segment["audio_in_ms"]),
        duration=_ms_to_fcpx_time(duration_ms),
        srcEnable="audio",
        audioRole=audio_role,
    )


def _build_otio_timeline(
    connection: sqlite3.Connection, project_id: str, segments: list[dict[str, object]], exported_at: str
) -> dict[str, object]:
    master_rate = _load_master_rate(connection, segments)
    video_children = _build_otio_track_children(segments, master_rate, "video")
    audio_children = _build_otio_track_children(segments, master_rate, "audio")

    return {
        "OTIO_SCHEMA": "Timeline.1",
        "name": f"DaySync OTIO Export {project_id}",
        "global_start_time": _build_otio_rational_time(0, master_rate),
        "metadata": {
            "daysync": {
                "project_id": project_id,
                "exported_at": exported_at,
                "sync_result_count": len(segments),
            }
        },
        "tracks": {
            "OTIO_SCHEMA": "Stack.1",
            "name": "tracks",
            "source_range": None,
            "effects": [],
            "markers": [],
            "enabled": True,
            "metadata": {"daysync": {"export_type": "otio"}},
            "children": [
                {
                    "OTIO_SCHEMA": "Track.1",
                    "name": "V1",
                    "kind": "Video",
                    "source_range": None,
                    "effects": [],
                    "markers": [],
                    "enabled": True,
                    "metadata": {"daysync": {"track_role": "video"}},
                    "children": video_children,
                },
                {
                    "OTIO_SCHEMA": "Track.1",
                    "name": "A1",
                    "kind": "Audio",
                    "source_range": None,
                    "effects": [],
                    "markers": [],
                    "enabled": True,
                    "metadata": {"daysync": {"track_role": "audio"}},
                    "children": audio_children,
                },
            ],
        },
    }


def _build_fcp7_xml(
    connection: sqlite3.Connection, project_id: str, segments: list[dict[str, object]]
) -> str:
    root = ET.Element("xmeml", version="5")
    project = ET.SubElement(root, "project")
    ET.SubElement(project, "name").text = f"DaySync Export {project_id}"
    children = ET.SubElement(project, "children")

    if segments:
        sequence = ET.SubElement(children, "sequence", id=f"sequence-{project_id}")
        _append_text(sequence, "name", f"DaySync Synced Timeline {project_id}")
        video_rate = _load_video_rate(connection, segments[0]["video_media_file_id"])
        timebase, ntsc_flag = _format_rate(video_rate)
        rate_node = ET.SubElement(sequence, "rate")
        _append_text(rate_node, "timebase", str(timebase))
        _append_text(rate_node, "ntsc", "TRUE" if ntsc_flag else "FALSE")

        sequence_duration_ms = max(int(segment["timeline_end_ms"]) for segment in segments)
        _append_text(sequence, "duration", str(_ms_to_frames(sequence_duration_ms, video_rate)))
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
        audio = ET.SubElement(media, "audio")
        audio_track = ET.SubElement(audio, "track")
        for segment in segments:
            layout = _build_continuous_sequence_layout(segment, video_rate)
            video_clip_id = f"{segment['sync_result_id']}-video"
            audio_clip_id = f"{segment['sync_result_id']}-audio"

            video_clipitem = ET.SubElement(track, "clipitem", id=video_clip_id)
            _append_text(video_clipitem, "name", segment["video_file"])
            _append_text(video_clipitem, "duration", str(_ms_to_frames(segment["video_duration_ms"], video_rate)))
            _append_text(video_clipitem, "start", str(layout["timeline_start_frames"]))
            _append_text(video_clipitem, "end", str(layout["timeline_end_frames"]))
            _append_text(video_clipitem, "in", str(layout["video_in_frames"]))
            _append_text(video_clipitem, "out", str(layout["video_out_frames"]))
            _append_link(video_clipitem, video_clip_id)
            _append_link(video_clipitem, audio_clip_id)
            _append_sourcetrack(video_clipitem, "video", 1)
            _append_file_reference(
                video_clipitem,
                file_id=f"file-{segment['video_media_file_id']}-video",
                name=segment["video_file"],
                original_path=segment["video_path"],
                duration_ms=segment["video_duration_ms"],
                rate=video_rate,
                stream_info=_load_video_stream(connection, segment["video_media_file_id"]),
                mediatype="video",
            )

            audio_clipitem = ET.SubElement(audio_track, "clipitem", id=audio_clip_id)
            _append_text(audio_clipitem, "name", segment["audio_file"])
            _append_text(audio_clipitem, "duration", str(_ms_to_frames(segment["audio_duration_ms"], video_rate)))
            _append_text(audio_clipitem, "start", str(layout["timeline_start_frames"]))
            _append_text(audio_clipitem, "end", str(layout["timeline_end_frames"]))
            _append_text(audio_clipitem, "in", str(layout["audio_in_frames"]))
            _append_text(audio_clipitem, "out", str(layout["audio_out_frames"]))
            _append_link(audio_clipitem, video_clip_id)
            _append_link(audio_clipitem, audio_clip_id)
            _append_sourcetrack(audio_clipitem, "audio", 1)
            _append_file_reference(
                audio_clipitem,
                file_id=f"file-{segment['audio_media_file_id']}-audio",
                name=segment["audio_file"],
                original_path=segment["audio_path"],
                duration_ms=segment["audio_duration_ms"],
                rate=video_rate,
                stream_info=_load_audio_stream(connection, segment["audio_media_file_id"]),
                mediatype="audio",
            )

    xml_body = ET.tostring(root, encoding="unicode")
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n{xml_body}\n'


def _build_sequence_layout(row: sqlite3.Row, rate: float) -> dict[str, int]:
    layout_ms = _build_sequence_layout_ms(row)
    return {
        "video_timeline_start_frames": _ms_to_frames(layout_ms["video_timeline_start_ms"], rate),
        "video_timeline_end_frames": _ms_to_frames(layout_ms["video_timeline_end_ms"], rate),
        "audio_timeline_start_frames": _ms_to_frames(layout_ms["audio_timeline_start_ms"], rate),
        "audio_timeline_end_frames": _ms_to_frames(layout_ms["audio_timeline_end_ms"], rate),
        "video_in_frames": _ms_to_frames(layout_ms["video_in_ms"], rate),
        "video_out_frames": _ms_to_frames(row["video_out_ms"], rate),
        "audio_in_frames": _ms_to_frames(layout_ms["audio_in_ms"], rate),
        "audio_out_frames": _ms_to_frames(max(row["audio_out_ms"], 0), rate),
        "sequence_duration_frames": _ms_to_frames(layout_ms["sequence_duration_ms"], rate),
    }


def _build_sequence_layout_ms(row: sqlite3.Row) -> dict[str, int]:
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
        "video_timeline_start_ms": video_timeline_start_ms,
        "video_timeline_end_ms": video_timeline_end_ms,
        "audio_timeline_start_ms": audio_timeline_start_ms,
        "audio_timeline_end_ms": audio_timeline_end_ms,
        "video_in_ms": video_in_ms,
        "audio_in_ms": audio_in_ms,
        "sequence_duration_ms": sequence_duration_ms,
    }


def _build_otio_gap(duration_ms: int, rate: float, name: str) -> dict[str, object]:
    return {
        "OTIO_SCHEMA": "Gap.1",
        "name": name,
        "source_range": _build_otio_time_range(0, duration_ms, rate),
        "effects": [],
        "markers": [],
        "enabled": True,
        "metadata": {},
    }


def _build_otio_clip(
    *,
    name: str,
    media_path: str,
    media_duration_ms: int,
    clip_start_ms: int,
    clip_duration_ms: int,
    rate: float,
    metadata: dict[str, object],
) -> dict[str, object]:
    return {
        "OTIO_SCHEMA": "Clip.2",
        "name": name,
        "source_range": _build_otio_time_range(clip_start_ms, clip_duration_ms, rate),
        "effects": [],
        "markers": [],
        "enabled": True,
        "metadata": metadata,
        "active_media_reference_key": "DEFAULT_MEDIA",
        "media_references": {
            "DEFAULT_MEDIA": {
                "OTIO_SCHEMA": "ExternalReference.1",
                "name": name,
                "available_range": _build_otio_time_range(0, media_duration_ms, rate),
                "available_image_bounds": None,
                "metadata": {},
                "target_url": Path(media_path).as_uri(),
            }
        },
    }


def _build_otio_time_range(start_ms: int, duration_ms: int, rate: float) -> dict[str, object]:
    return {
        "OTIO_SCHEMA": "TimeRange.1",
        "start_time": _build_otio_rational_time(start_ms, rate),
        "duration": _build_otio_rational_time(duration_ms, rate),
    }


def _build_otio_rational_time(value_ms: int | float, rate: float) -> dict[str, object]:
    return {
        "OTIO_SCHEMA": "RationalTime.1",
        "rate": rate,
        "value": _ms_to_frames(value_ms, rate),
    }


def _build_otio_clip_metadata(row: sqlite3.Row, clip_role: str) -> dict[str, object]:
    return {
        "daysync": {
            "sync_result_id": row["sync_result_id"],
            "clip_role": clip_role,
            "status": row["status"],
            "source": row["source"],
            "confidence_score": row["confidence_score"],
            "offset_ms": row["offset_ms"],
            "video_anchor_text": row["video_anchor_text"],
            "audio_anchor_text": row["audio_anchor_text"],
            "created_at": row["created_at"],
        }
    }


def _load_master_rate(connection: sqlite3.Connection, rows: list[sqlite3.Row]) -> float:
    if not rows:
        return 25.0
    return _load_video_rate(connection, rows[0]["video_media_file_id"])


def _build_otio_track_children(
    segments: list[dict[str, object]],
    rate: float,
    clip_role: str,
) -> list[dict[str, object]]:
    children: list[dict[str, object]] = []
    cursor_ms = 0
    for segment in segments:
        if segment["timeline_start_ms"] > cursor_ms:
            children.append(
                _build_otio_gap(segment["timeline_start_ms"] - cursor_ms, rate, f"{clip_role}-gap")
            )
        if clip_role == "video":
            name = segment["video_file"]
            media_path = segment["video_path"]
            media_duration_ms = segment["video_duration_ms"]
            clip_start_ms = segment["video_in_ms"]
        else:
            name = segment["audio_file"]
            media_path = segment["audio_path"]
            media_duration_ms = segment["audio_duration_ms"]
            clip_start_ms = segment["audio_in_ms"]

        children.append(
            _build_otio_clip(
                name=name,
                media_path=media_path,
                media_duration_ms=media_duration_ms,
                clip_start_ms=clip_start_ms,
                clip_duration_ms=segment["timeline_duration_ms"],
                rate=rate,
                metadata=_build_otio_clip_metadata(segment, clip_role),
            )
        )
        cursor_ms = segment["timeline_end_ms"]
    return children


def _ms_to_fcpx_time(value_ms: int | float) -> str:
    numerator = int(round(float(value_ms)))
    denominator = 1000
    if numerator == 0:
        return "0s"
    gcd_value = math.gcd(abs(numerator), denominator)
    reduced_numerator = numerator // gcd_value
    reduced_denominator = denominator // gcd_value
    if reduced_denominator == 1:
        return f"{reduced_numerator}s"
    return f"{reduced_numerator}/{reduced_denominator}s"


def _rate_to_fcpx_time(rate_num: int, rate_den: int) -> str:
    if rate_num <= 0 or rate_den <= 0:
        return "1/25s"
    return f"{rate_den}/{rate_num}s"


def _guess_fcpx_format_name(width: int, height: int, rate_num: int, rate_den: int) -> str | None:
    if height != 1080:
        return None
    rounded_rate = round(rate_num / rate_den, 3) if rate_den else 25.0
    if abs(rounded_rate - 23.976) < 0.01:
        suffix = "2398"
    elif abs(rounded_rate - 24.0) < 0.01:
        suffix = "24"
    elif abs(rounded_rate - 25.0) < 0.01:
        suffix = "25"
    elif abs(rounded_rate - 29.97) < 0.01:
        suffix = "2997"
    elif abs(rounded_rate - 30.0) < 0.01:
        suffix = "30"
    elif abs(rounded_rate - 50.0) < 0.01:
        suffix = "50"
    elif abs(rounded_rate - 59.94) < 0.01:
        suffix = "5994"
    elif abs(rounded_rate - 60.0) < 0.01:
        suffix = "60"
    else:
        return None
    return f"FFVideoFormat1080p{suffix}"


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
    numerator, denominator = _load_video_rate_info(connection, media_file_id)
    return numerator / denominator


def _load_video_rate_info(connection: sqlite3.Connection, media_file_id: str) -> tuple[int, int]:
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
        return 25, 1
    return int(row["frame_rate_num"]), int(row["frame_rate_den"])


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
        SELECT sample_rate, channels
        FROM media_streams
        WHERE media_file_id = ? AND stream_type = 'audio'
        ORDER BY stream_index
        LIMIT 1
        """,
        (media_file_id,),
    ).fetchone()
    return dict(row) if row is not None else {"sample_rate": 48000, "channels": 2}


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


def _build_continuous_sequence_layout(segment: dict[str, object], rate: float) -> dict[str, int]:
    return {
        "timeline_start_frames": _ms_to_frames(segment["timeline_start_ms"], rate),
        "timeline_end_frames": _ms_to_frames(segment["timeline_end_ms"], rate),
        "video_in_frames": _ms_to_frames(segment["video_in_ms"], rate),
        "video_out_frames": _ms_to_frames(segment["video_out_ms"], rate),
        "audio_in_frames": _ms_to_frames(segment["audio_in_ms"], rate),
        "audio_out_frames": _ms_to_frames(segment["audio_out_ms"], rate),
    }


def _ordered_unique_ids(segments: list[dict[str, object]], key: str) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for segment in segments:
        value = str(segment[key])
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _sequence_count_for_segments(segments: list[dict[str, object]]) -> int:
    return 1 if segments else 0


def _project_count_for_segments(segments: list[dict[str, object]]) -> int:
    return 1 if segments else 0
