from __future__ import annotations

import sqlite3
from pathlib import Path

from daysync_core.errors import DaySyncError
from daysync_core.timeline.service import list_flat_timelines, map_flat_to_source
from daysync_core.utils import new_uuid, utc_now_iso

from .normalize import normalize_subtitle_text
from .srt import parse_srt


def import_srt(
    connection: sqlite3.Connection,
    project_id: str,
    flat_timeline_id: str,
    track_type: str,
    source_type: str,
    path: str,
    language: str | None = None,
) -> dict[str, object]:
    srt_path = Path(path)
    if not srt_path.exists():
        raise DaySyncError(
            "SUBTITLE_PARSE_FAILED",
            f"SRT file not found: {srt_path}",
            {"path": str(srt_path)},
        )

    timeline_rows = list_flat_timelines(connection, project_id)
    matching_timeline = next((row for row in timeline_rows if row["id"] == flat_timeline_id), None)
    if matching_timeline is None:
        raise DaySyncError(
            "SUBTITLE_MAPPING_FAILED",
            "Flat timeline not found for subtitle import",
            {"flat_timeline_id": flat_timeline_id},
        )

    parsed = parse_srt(srt_path.read_text(encoding="utf-8"))
    connection.execute(
        """
        DELETE FROM subtitle_tracks
        WHERE project_id = ? AND track_type = ?
        """,
        (project_id, track_type),
    )
    track_id = new_uuid()
    created_at = utc_now_iso()
    connection.execute(
        """
        INSERT INTO subtitle_tracks (
          id, project_id, flat_timeline_id, track_type, source_type, language, original_path, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (track_id, project_id, flat_timeline_id, track_type, source_type, language, str(srt_path), created_at),
    )

    warning_count = 0
    failed_count = 0
    for subtitle in parsed:
        mapping = map_flat_to_source(
            matching_timeline["items"], subtitle.flat_start_ms, subtitle.flat_end_ms
        )
        normalized_text = normalize_subtitle_text(subtitle.raw_text)
        if mapping["mapping_status"] == "warning":
            warning_count += 1
        if mapping["mapping_status"] == "failed":
            failed_count += 1
        connection.execute(
            """
            INSERT INTO subtitles (
              id, track_id, subtitle_index, flat_start_ms, flat_end_ms,
              source_media_file_id, source_start_ms, source_end_ms,
              raw_text, normalized_text, mapping_status, mapping_warning, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_uuid(),
                track_id,
                subtitle.subtitle_index,
                subtitle.flat_start_ms,
                subtitle.flat_end_ms,
                mapping["media_file_id"],
                mapping["source_start_ms"],
                mapping["source_end_ms"],
                subtitle.raw_text,
                normalized_text,
                mapping["mapping_status"],
                mapping["mapping_warning"],
                created_at,
            ),
        )

    connection.commit()
    return {
        "track_id": track_id,
        "imported_count": len(parsed),
        "warning_count": warning_count,
        "failed_count": failed_count,
    }
