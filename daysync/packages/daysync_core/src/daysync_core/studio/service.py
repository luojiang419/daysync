from __future__ import annotations

import sqlite3
from statistics import median


def get_studio_timeline_snapshot(
    connection: sqlite3.Connection,
    project_id: str,
) -> dict[str, object]:
    video_timeline = _load_latest_flat_timeline(connection, project_id, "video")
    audio_timeline = _load_latest_flat_timeline(connection, project_id, "audio")
    video_clips = (
        _load_timeline_clips(connection, video_timeline["id"], "video")
        if video_timeline is not None
        else []
    )
    audio_clips = (
        _load_timeline_clips(connection, audio_timeline["id"], "audio")
        if audio_timeline is not None
        else []
    )

    video_subtitle_track = _load_latest_subtitle_track(connection, project_id, "video_ref")
    audio_subtitle_track = _load_latest_subtitle_track(connection, project_id, "external_audio")
    video_subtitles = (
        _load_subtitle_cues(connection, video_subtitle_track["id"], "video_ref")
        if video_subtitle_track is not None
        else []
    )
    audio_subtitles = (
        _load_subtitle_cues(connection, audio_subtitle_track["id"], "external_audio")
        if audio_subtitle_track is not None
        else []
    )

    accepted_rows = _load_latest_accepted_sync_rows(connection, project_id)
    sync_segments = _build_sync_segments(accepted_rows, video_clips, audio_clips)

    return {
        "project_id": project_id,
        "video_timeline": _to_timeline_track_meta(video_timeline, len(video_clips)),
        "audio_timeline": _to_timeline_track_meta(audio_timeline, len(audio_clips)),
        "video_subtitle_track": _to_subtitle_track_meta(
            video_subtitle_track,
            len(video_subtitles),
        ),
        "audio_subtitle_track": _to_subtitle_track_meta(
            audio_subtitle_track,
            len(audio_subtitles),
        ),
        "video_clips": video_clips,
        "audio_clips": audio_clips,
        "video_subtitles": video_subtitles,
        "audio_subtitles": audio_subtitles,
        "sync_segments": sync_segments,
        "accepted_sync_summary": _build_accepted_sync_summary(sync_segments),
    }


def _load_latest_flat_timeline(
    connection: sqlite3.Connection,
    project_id: str,
    media_type: str,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT ft.id, ft.project_id, ft.media_type, ft.name, ft.gap_ms, ft.sort_mode, ft.created_at,
               COALESCE(MAX(fti.flat_end_ms), 0) AS total_duration_ms
        FROM flat_timelines ft
        LEFT JOIN flat_timeline_items fti ON fti.flat_timeline_id = ft.id
        WHERE ft.project_id = ? AND ft.media_type = ?
        GROUP BY ft.id, ft.project_id, ft.media_type, ft.name, ft.gap_ms, ft.sort_mode, ft.created_at
        ORDER BY ft.created_at DESC, ft.rowid DESC
        LIMIT 1
        """,
        (project_id, media_type),
    ).fetchone()


def _load_timeline_clips(
    connection: sqlite3.Connection,
    flat_timeline_id: str,
    media_type: str,
) -> list[dict[str, object]]:
    rows = connection.execute(
        """
        SELECT fti.id, fti.flat_timeline_id, fti.media_file_id, fti.item_index,
               fti.flat_start_ms, fti.flat_end_ms, fti.source_start_ms, fti.source_end_ms,
               fti.gap_after_ms, mf.media_type, mf.filename, mf.original_path, mf.has_video, mf.has_audio
        FROM flat_timeline_items fti
        JOIN media_files mf ON mf.id = fti.media_file_id
        WHERE fti.flat_timeline_id = ?
        ORDER BY fti.item_index
        """,
        (flat_timeline_id,),
    ).fetchall()
    return [
        {
            "id": row["id"],
            "timeline_id": row["flat_timeline_id"],
            "media_file_id": row["media_file_id"],
            "item_index": row["item_index"],
            "media_type": media_type,
            "filename": row["filename"],
            "original_path": row["original_path"],
            "flat_start_ms": row["flat_start_ms"],
            "flat_end_ms": row["flat_end_ms"],
            "source_start_ms": row["source_start_ms"],
            "source_end_ms": row["source_end_ms"],
            "gap_after_ms": row["gap_after_ms"],
            "has_video": bool(row["has_video"]),
            "has_audio": bool(row["has_audio"]),
        }
        for row in rows
    ]


def _load_latest_subtitle_track(
    connection: sqlite3.Connection,
    project_id: str,
    track_type: str,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT st.id, st.project_id, st.flat_timeline_id, st.track_type, st.source_type,
               st.language, st.original_path, st.created_at,
               COALESCE(MAX(s.flat_end_ms), 0) AS total_duration_ms
        FROM subtitle_tracks st
        LEFT JOIN subtitles s ON s.track_id = st.id
        WHERE st.project_id = ? AND st.track_type = ?
        GROUP BY st.id, st.project_id, st.flat_timeline_id, st.track_type, st.source_type,
                 st.language, st.original_path, st.created_at
        ORDER BY st.created_at DESC, st.rowid DESC
        LIMIT 1
        """,
        (project_id, track_type),
    ).fetchone()


def _load_subtitle_cues(
    connection: sqlite3.Connection,
    track_id: str,
    track_type: str,
) -> list[dict[str, object]]:
    rows = connection.execute(
        """
        SELECT s.id, s.track_id, s.subtitle_index, s.flat_start_ms, s.flat_end_ms,
               s.source_start_ms, s.source_end_ms, s.raw_text, s.mapping_status, s.mapping_warning,
               mf.filename AS source_filename
        FROM subtitles s
        LEFT JOIN media_files mf ON mf.id = s.source_media_file_id
        WHERE s.track_id = ?
        ORDER BY s.subtitle_index
        """,
        (track_id,),
    ).fetchall()
    return [
        {
            "subtitle_id": row["id"],
            "track_id": row["track_id"],
            "track_type": track_type,
            "subtitle_index": row["subtitle_index"],
            "flat_start_ms": row["flat_start_ms"],
            "flat_end_ms": row["flat_end_ms"],
            "source_start_ms": row["source_start_ms"],
            "source_end_ms": row["source_end_ms"],
            "raw_text": row["raw_text"],
            "mapping_status": row["mapping_status"],
            "mapping_warning": row["mapping_warning"],
            "source_filename": row["source_filename"],
        }
        for row in rows
    ]


def _load_latest_accepted_sync_rows(
    connection: sqlite3.Connection,
    project_id: str,
) -> list[sqlite3.Row]:
    rows = connection.execute(
        """
        SELECT sr.id, sr.project_id, sr.video_media_file_id, sr.audio_media_file_id,
               sr.video_in_ms, sr.video_out_ms, sr.audio_in_ms, sr.audio_out_ms,
               sr.offset_ms, sr.status, sr.source, sr.created_at, sr.updated_at
        FROM sync_results sr
        WHERE sr.project_id = ?
          AND sr.status IN ('accepted_manual', 'accepted_auto')
        ORDER BY sr.created_at DESC, sr.rowid DESC
        """,
        (project_id,),
    ).fetchall()
    latest_by_range: dict[
        tuple[str, str, int, int, int, int],
        sqlite3.Row,
    ] = {}
    for row in rows:
        key = (
            row["video_media_file_id"],
            row["audio_media_file_id"],
            row["video_in_ms"],
            row["video_out_ms"],
            row["audio_in_ms"],
            row["audio_out_ms"],
        )
        latest_by_range.setdefault(key, row)
    return list(latest_by_range.values())


def _build_sync_segments(
    accepted_rows: list[sqlite3.Row],
    video_clips: list[dict[str, object]],
    audio_clips: list[dict[str, object]],
) -> list[dict[str, object]]:
    segments: list[dict[str, object]] = []
    for row in accepted_rows:
        video_clip = _find_clip_for_source_range(
            video_clips,
            str(row["video_media_file_id"]),
            int(row["video_in_ms"]),
            int(row["video_out_ms"]),
        )
        audio_clip = _find_clip_for_source_range(
            audio_clips,
            str(row["audio_media_file_id"]),
            int(row["audio_in_ms"]),
            int(row["audio_out_ms"]),
        )
        if video_clip is None or audio_clip is None:
            continue

        video_flat_start_ms = int(video_clip["flat_start_ms"]) + (
            int(row["video_in_ms"]) - int(video_clip["source_start_ms"])
        )
        video_flat_end_ms = int(video_clip["flat_start_ms"]) + (
            int(row["video_out_ms"]) - int(video_clip["source_start_ms"])
        )
        audio_flat_start_ms = int(audio_clip["flat_start_ms"]) + (
            int(row["audio_in_ms"]) - int(audio_clip["source_start_ms"])
        )
        audio_flat_end_ms = int(audio_clip["flat_start_ms"]) + (
            int(row["audio_out_ms"]) - int(audio_clip["source_start_ms"])
        )

        segments.append(
            {
                "sync_result_id": row["id"],
                "video_media_file_id": row["video_media_file_id"],
                "audio_media_file_id": row["audio_media_file_id"],
                "video_filename": video_clip["filename"],
                "audio_filename": audio_clip["filename"],
                "video_original_path": video_clip["original_path"],
                "audio_original_path": audio_clip["original_path"],
                "video_flat_start_ms": video_flat_start_ms,
                "video_flat_end_ms": video_flat_end_ms,
                "audio_flat_start_ms": audio_flat_start_ms,
                "audio_flat_end_ms": audio_flat_end_ms,
                "video_in_ms": row["video_in_ms"],
                "video_out_ms": row["video_out_ms"],
                "audio_in_ms": row["audio_in_ms"],
                "audio_out_ms": row["audio_out_ms"],
                "offset_ms": row["offset_ms"],
                "status": row["status"],
                "source": row["source"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )
    return sorted(segments, key=lambda item: (item["video_flat_start_ms"], item["audio_flat_start_ms"]))


def _find_clip_for_source_range(
    clips: list[dict[str, object]],
    media_file_id: str,
    start_ms: int,
    end_ms: int,
) -> dict[str, object] | None:
    for clip in clips:
        if clip["media_file_id"] != media_file_id:
            continue
        if int(clip["source_start_ms"]) <= start_ms and end_ms <= int(clip["source_end_ms"]):
            return clip
    return None


def _build_accepted_sync_summary(
    sync_segments: list[dict[str, object]],
) -> dict[str, object]:
    if not sync_segments:
        return {
            "status": "missing",
            "accepted_count": 0,
            "median_offset_ms": None,
            "latest_source": None,
            "latest_updated_at": None,
        }
    latest_segment = max(sync_segments, key=lambda item: item["updated_at"])
    return {
        "status": "ready",
        "accepted_count": len(sync_segments),
        "median_offset_ms": int(round(median([int(item["offset_ms"]) for item in sync_segments]))),
        "latest_source": latest_segment["source"],
        "latest_updated_at": latest_segment["updated_at"],
    }


def _to_timeline_track_meta(
    row: sqlite3.Row | None,
    item_count: int,
) -> dict[str, object] | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "kind": f"{row['media_type']}_timeline",
        "name": row["name"],
        "media_type": row["media_type"],
        "gap_ms": row["gap_ms"],
        "sort_mode": row["sort_mode"],
        "item_count": item_count,
        "total_duration_ms": row["total_duration_ms"],
        "created_at": row["created_at"],
    }


def _to_subtitle_track_meta(
    row: sqlite3.Row | None,
    cue_count: int,
) -> dict[str, object] | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "kind": row["track_type"],
        "name": row["track_type"],
        "track_type": row["track_type"],
        "source_type": row["source_type"],
        "language": row["language"],
        "original_path": row["original_path"],
        "cue_count": cue_count,
        "total_duration_ms": row["total_duration_ms"],
        "created_at": row["created_at"],
    }
