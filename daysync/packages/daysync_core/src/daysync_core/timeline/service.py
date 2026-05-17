from __future__ import annotations

import sqlite3

from daysync_core.errors import DaySyncError
from daysync_core.utils import new_uuid, utc_now_iso


def generate_flat_timeline(
    connection: sqlite3.Connection,
    project_id: str,
    media_type: str,
    media_file_ids: list[str],
    sort_mode: str,
    gap_ms: int,
) -> dict[str, object]:
    if gap_ms < 0:
        raise DaySyncError("MEDIA_DURATION_INVALID", "gap_ms must be >= 0", {"gap_ms": gap_ms})
    if not media_file_ids:
        raise DaySyncError("MEDIA_FILE_NOT_FOUND", "At least one media file must be selected")

    media_rows = connection.execute(
        """
        SELECT id, filename, media_type, duration_ms, created_at_metadata, imported_at
        FROM media_files
        WHERE project_id = ?
          AND id IN ({placeholders})
        """.format(placeholders=",".join("?" for _ in media_file_ids)),
        (project_id, *media_file_ids),
    ).fetchall()

    if len(media_rows) != len(media_file_ids):
        raise DaySyncError("MEDIA_FILE_NOT_FOUND", "One or more media files were not found")

    for row in media_rows:
        if row["media_type"] != media_type:
            raise DaySyncError(
                "MEDIA_TYPE_MISMATCH",
                "Selected media contain mixed media types",
                {"expected": media_type, "actual": row["media_type"]},
            )
        if row["duration_ms"] <= 0:
            raise DaySyncError(
                "MEDIA_DURATION_INVALID",
                f"Media duration is invalid for {row['filename']}",
                {"media_file_id": row["id"]},
            )

    media = [dict(row) for row in media_rows]
    ordered_media = _order_media(media, media_file_ids, sort_mode)
    timeline_id = new_uuid()
    timeline_name = f"{media_type}_flat_timeline"
    created_at = utc_now_iso()
    connection.execute(
        """
        INSERT INTO flat_timelines (id, project_id, media_type, name, gap_ms, sort_mode, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (timeline_id, project_id, media_type, timeline_name, gap_ms, sort_mode, created_at),
    )

    current_ms = 0
    items: list[dict[str, object]] = []
    for index, media_row in enumerate(ordered_media):
        flat_start_ms = current_ms
        flat_end_ms = flat_start_ms + media_row["duration_ms"]
        item = {
            "id": new_uuid(),
            "flat_timeline_id": timeline_id,
            "media_file_id": media_row["id"],
            "item_index": index,
            "flat_start_ms": flat_start_ms,
            "flat_end_ms": flat_end_ms,
            "source_start_ms": 0,
            "source_end_ms": media_row["duration_ms"],
            "gap_after_ms": gap_ms,
            "filename": media_row["filename"],
        }
        connection.execute(
            """
            INSERT INTO flat_timeline_items (
              id, flat_timeline_id, media_file_id, item_index, flat_start_ms, flat_end_ms,
              source_start_ms, source_end_ms, gap_after_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["id"],
                timeline_id,
                item["media_file_id"],
                item["item_index"],
                item["flat_start_ms"],
                item["flat_end_ms"],
                item["source_start_ms"],
                item["source_end_ms"],
                item["gap_after_ms"],
            ),
        )
        items.append(item)
        current_ms = flat_end_ms + gap_ms

    connection.commit()
    return {"flat_timeline_id": timeline_id, "items": items}


def map_flat_to_source(
    items: list[dict[str, object]], flat_start_ms: int, flat_end_ms: int | None = None
) -> dict[str, object]:
    for item in items:
        if item["flat_start_ms"] <= flat_start_ms < item["flat_end_ms"]:
            source_start_ms = flat_start_ms - item["flat_start_ms"] + item["source_start_ms"]
            source_end_ms = None
            mapping_status = "ok"
            mapping_warning = None
            if flat_end_ms is not None:
                source_end_ms = flat_end_ms - item["flat_start_ms"] + item["source_start_ms"]
                if flat_end_ms > item["flat_end_ms"]:
                    mapping_status = "warning"
                    mapping_warning = "subtitle_crosses_media_boundary"
            return {
                "media_file_id": item["media_file_id"],
                "source_start_ms": source_start_ms,
                "source_end_ms": source_end_ms,
                "mapping_status": mapping_status,
                "mapping_warning": mapping_warning,
            }

    for item in items:
        gap_start = item["flat_end_ms"]
        gap_end = item["flat_end_ms"] + item["gap_after_ms"]
        if gap_start <= flat_start_ms < gap_end:
            return {
                "media_file_id": None,
                "source_start_ms": None,
                "source_end_ms": None,
                "mapping_status": "warning",
                "mapping_warning": "subtitle_in_gap",
            }

    return {
        "media_file_id": None,
        "source_start_ms": None,
        "source_end_ms": None,
        "mapping_status": "failed",
        "mapping_warning": "no_matching_flat_item",
    }


def map_source_to_flat(items: list[dict[str, object]], media_file_id: str, source_ms: int) -> dict[str, object]:
    for item in items:
        if item["media_file_id"] != media_file_id:
            continue
        if item["source_start_ms"] <= source_ms <= item["source_end_ms"]:
            return {
                "flat_ms": source_ms - item["source_start_ms"] + item["flat_start_ms"],
                "mapping_status": "ok",
                "mapping_warning": None,
            }
    return {"flat_ms": None, "mapping_status": "warning", "mapping_warning": "source_time_out_of_range"}


def list_flat_timelines(connection: sqlite3.Connection, project_id: str) -> list[dict[str, object]]:
    timeline_rows = connection.execute(
        """
        SELECT id, project_id, media_type, name, gap_ms, sort_mode, created_at
        FROM flat_timelines
        WHERE project_id = ?
        ORDER BY created_at
        """,
        (project_id,),
    ).fetchall()
    timelines: list[dict[str, object]] = []
    for timeline_row in timeline_rows:
        timeline = dict(timeline_row)
        items = connection.execute(
            """
            SELECT fti.id, fti.flat_timeline_id, fti.media_file_id, fti.item_index, fti.flat_start_ms,
                   fti.flat_end_ms, fti.source_start_ms, fti.source_end_ms, fti.gap_after_ms, mf.filename
            FROM flat_timeline_items fti
            JOIN media_files mf ON mf.id = fti.media_file_id
            WHERE fti.flat_timeline_id = ?
            ORDER BY fti.item_index
            """,
            (timeline["id"],),
        ).fetchall()
        timeline["items"] = [dict(item) for item in items]
        timelines.append(timeline)
    return timelines


def _order_media(
    media: list[dict[str, object]], media_file_ids: list[str], sort_mode: str
) -> list[dict[str, object]]:
    if sort_mode == "manual":
        order_map = {media_id: index for index, media_id in enumerate(media_file_ids)}
        return sorted(media, key=lambda row: order_map[row["id"]])
    if sort_mode == "created_at":
        return sorted(media, key=lambda row: (row["created_at_metadata"] or "", row["filename"]))
    return sorted(media, key=lambda row: row["filename"])
