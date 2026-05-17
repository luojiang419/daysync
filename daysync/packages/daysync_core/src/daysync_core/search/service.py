from __future__ import annotations

import sqlite3

from daysync_core.subtitles.normalize import normalize_subtitle_text


def search_subtitles(connection: sqlite3.Connection, project_id: str, query: str, limit: int = 20) -> dict[str, object]:
    normalized_query = normalize_subtitle_text(query)
    rows = []
    if normalized_query or query:
        try:
            rows = connection.execute(
                """
                SELECT s.id AS subtitle_id, st.track_type, s.raw_text, s.normalized_text,
                       s.source_media_file_id, s.source_start_ms, s.source_end_ms,
                       s.flat_start_ms, s.flat_end_ms, mf.filename AS source_filename,
                       -bm25(subtitles_fts) AS relevance_score
                FROM subtitles_fts
                JOIN subtitles s ON s.subtitle_pk = subtitles_fts.rowid
                JOIN subtitle_tracks st ON st.id = s.track_id
                LEFT JOIN media_files mf ON mf.id = s.source_media_file_id
                WHERE st.project_id = ?
                  AND subtitles_fts MATCH ?
                ORDER BY bm25(subtitles_fts), s.flat_start_ms
                LIMIT ?
                """,
                (project_id, normalized_query or query, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []

    if not rows:
        rows = connection.execute(
            """
            SELECT s.id AS subtitle_id, st.track_type, s.raw_text, s.normalized_text,
                   s.source_media_file_id, s.source_start_ms, s.source_end_ms,
                   s.flat_start_ms, s.flat_end_ms, mf.filename AS source_filename,
                   0.0 AS relevance_score
            FROM subtitles s
            JOIN subtitle_tracks st ON st.id = s.track_id
            LEFT JOIN media_files mf ON mf.id = s.source_media_file_id
            WHERE st.project_id = ?
              AND (s.normalized_text LIKE ? OR s.raw_text LIKE ?)
            ORDER BY s.flat_start_ms
            LIMIT ?
            """,
            (project_id, f"%{normalized_query}%", f"%{query}%", limit),
        ).fetchall()

    results = [dict(row) for row in rows]
    return {
        "query": query,
        "video_results": [row for row in results if row["track_type"] == "video_ref"],
        "audio_results": [row for row in results if row["track_type"] == "external_audio"],
    }
