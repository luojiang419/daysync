from __future__ import annotations

import json
import sqlite3

from daysync_core.errors import DaySyncError
from daysync_core.utils import new_uuid, utc_now_iso


def create_manual_anchor_sync(
    connection: sqlite3.Connection,
    project_id: str,
    video_subtitle_id: str,
    audio_subtitle_id: str,
) -> dict[str, object]:
    video_anchor = _load_anchor(connection, project_id, video_subtitle_id, "video_ref")
    audio_anchor = _load_anchor(connection, project_id, audio_subtitle_id, "external_audio")
    if video_anchor["source_start_ms"] is None or audio_anchor["source_start_ms"] is None:
        raise DaySyncError(
            "ANCHOR_SUBTITLE_INVALID",
            "Selected subtitles do not have mapped source times",
        )

    offset_ms = audio_anchor["source_start_ms"] - video_anchor["source_start_ms"]
    video_media = _load_media(connection, video_anchor["source_media_file_id"])
    sync_id = new_uuid()
    now = utc_now_iso()
    sync_result = {
        "id": sync_id,
        "project_id": project_id,
        "session_id": None,
        "video_media_file_id": video_anchor["source_media_file_id"],
        "audio_media_file_id": audio_anchor["source_media_file_id"],
        "video_in_ms": 0,
        "video_out_ms": video_media["duration_ms"],
        "audio_in_ms": offset_ms,
        "audio_out_ms": offset_ms + video_media["duration_ms"],
        "offset_ms": offset_ms,
        "drift_ppm": None,
        "confidence_score": 1.0,
        "status": "accepted_manual",
        "source": "manual_anchor",
        "video_anchor_subtitle_id": video_subtitle_id,
        "audio_anchor_subtitle_id": audio_subtitle_id,
        "confidence_breakdown_json": json.dumps({"manual_anchor": True}),
        "created_at": now,
        "updated_at": now,
    }
    connection.execute(
        """
        INSERT INTO sync_results (
          id, project_id, session_id, video_media_file_id, audio_media_file_id, video_in_ms, video_out_ms,
          audio_in_ms, audio_out_ms, offset_ms, drift_ppm, confidence_score, status, source,
          video_anchor_subtitle_id, audio_anchor_subtitle_id, confidence_breakdown_json, created_at, updated_at
        )
        VALUES (:id, :project_id, :session_id, :video_media_file_id, :audio_media_file_id, :video_in_ms,
                :video_out_ms, :audio_in_ms, :audio_out_ms, :offset_ms, :drift_ppm, :confidence_score,
                :status, :source, :video_anchor_subtitle_id, :audio_anchor_subtitle_id,
                :confidence_breakdown_json, :created_at, :updated_at)
        """,
        sync_result,
    )
    connection.commit()
    return sync_result


def list_sync_results(connection: sqlite3.Connection, project_id: str) -> list[dict[str, object]]:
    rows = connection.execute(
        """
        SELECT sr.id, sr.project_id, sr.video_media_file_id, sr.audio_media_file_id, sr.video_in_ms,
               sr.video_out_ms, sr.audio_in_ms, sr.audio_out_ms, sr.offset_ms, sr.confidence_score,
               sr.status, sr.source, sr.video_anchor_subtitle_id, sr.audio_anchor_subtitle_id,
               sr.created_at, sr.updated_at,
               vm.filename AS video_file, am.filename AS audio_file,
               vs.raw_text AS video_anchor_text, aus.raw_text AS audio_anchor_text
        FROM sync_results sr
        JOIN media_files vm ON vm.id = sr.video_media_file_id
        JOIN media_files am ON am.id = sr.audio_media_file_id
        LEFT JOIN subtitles vs ON vs.id = sr.video_anchor_subtitle_id
        LEFT JOIN subtitles aus ON aus.id = sr.audio_anchor_subtitle_id
        WHERE sr.project_id = ?
        ORDER BY sr.created_at DESC
        """,
        (project_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _load_anchor(
    connection: sqlite3.Connection, project_id: str, subtitle_id: str, expected_track_type: str
) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT s.id, s.source_media_file_id, s.source_start_ms, s.source_end_ms, st.track_type
        FROM subtitles s
        JOIN subtitle_tracks st ON st.id = s.track_id
        WHERE s.id = ? AND st.project_id = ?
        """,
        (subtitle_id, project_id),
    ).fetchone()
    if row is None or row["track_type"] != expected_track_type or row["source_media_file_id"] is None:
        raise DaySyncError("ANCHOR_SUBTITLE_INVALID", "Selected anchor subtitle is invalid")
    return row


def _load_media(connection: sqlite3.Connection, media_file_id: str) -> sqlite3.Row:
    row = connection.execute(
        "SELECT id, duration_ms FROM media_files WHERE id = ?",
        (media_file_id,),
    ).fetchone()
    if row is None:
        raise DaySyncError("MEDIA_FILE_NOT_FOUND", "Media file not found for sync result")
    return row
