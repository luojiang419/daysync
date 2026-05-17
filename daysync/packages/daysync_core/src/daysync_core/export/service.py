from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

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
