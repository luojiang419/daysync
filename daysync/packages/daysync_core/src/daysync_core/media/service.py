from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from daysync_core.errors import DaySyncError
from daysync_core.utils import new_uuid, utc_now_iso

from .ffprobe import probe_media

SUPPORTED_MEDIA_EXTENSIONS = {".mov", ".mp4", ".wav", ".m4a", ".mp3"}


def import_media(
    connection: sqlite3.Connection,
    project_id: str,
    paths: list[str],
    session_id: str | None = None,
    probe_func=None,
) -> dict[str, list[dict[str, object]]]:
    imported: list[dict[str, object]] = []
    failed: list[dict[str, object]] = []
    active_probe = probe_func or probe_media
    media_paths = _resolve_media_paths(paths, failed)

    for media_path in media_paths:
        try:
            probe = active_probe(media_path)
            media_id = new_uuid()
            imported_at = utc_now_iso()
            created_at_metadata = datetime.fromtimestamp(
                media_path.stat().st_mtime, tz=UTC
            ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            connection.execute(
                """
                INSERT INTO media_files (
                  id, project_id, session_id, media_type, original_path, filename, file_size, file_hash,
                  duration_ms, container, has_video, has_audio, created_at_metadata, imported_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    media_id,
                    project_id,
                    session_id,
                    probe["media_type"],
                    str(media_path),
                    media_path.name,
                    media_path.stat().st_size,
                    None,
                    probe["duration_ms"],
                    probe["container"],
                    int(probe["has_video"]),
                    int(probe["has_audio"]),
                    created_at_metadata,
                    imported_at,
                ),
            )
            for stream in probe["streams"]:
                connection.execute(
                    """
                    INSERT INTO media_streams (
                      id, media_file_id, stream_index, stream_type, codec, sample_rate, channels,
                      width, height, frame_rate_num, frame_rate_den, duration_ms, raw_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        stream["id"],
                        media_id,
                        stream["stream_index"],
                        stream["stream_type"],
                        stream["codec"],
                        stream["sample_rate"],
                        stream["channels"],
                        stream["width"],
                        stream["height"],
                        stream["frame_rate_num"],
                        stream["frame_rate_den"],
                        stream["duration_ms"],
                        stream["raw_json"],
                    ),
                )
            imported.append(
                {
                    "id": media_id,
                    "media_type": probe["media_type"],
                    "filename": media_path.name,
                    "duration_ms": probe["duration_ms"],
                    "has_video": probe["has_video"],
                    "has_audio": probe["has_audio"],
                }
            )
        except DaySyncError as exc:
            failed.append(
                {
                    "path": str(media_path),
                    "code": exc.code,
                    "message": exc.message,
                }
            )
        except Exception as exc:
            failed.append(
                {
                    "path": str(media_path),
                    "code": "MEDIA_IMPORT_FAILED",
                    "message": f"Failed to inspect media file: {exc}",
                }
            )

    connection.commit()
    return {"imported": imported, "failed": failed}


def list_media(connection: sqlite3.Connection, project_id: str) -> list[dict[str, object]]:
    rows = connection.execute(
        """
        SELECT id, project_id, session_id, media_type, original_path, filename, file_size, file_hash,
               duration_ms, container, has_video, has_audio, created_at_metadata, imported_at
        FROM media_files
        WHERE project_id = ?
        ORDER BY filename
        """,
        (project_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _resolve_media_paths(paths: list[str], failed: list[dict[str, object]]) -> list[Path]:
    resolved: list[Path] = []
    seen: set[str] = set()

    for raw_path in paths:
        candidate = Path(raw_path)
        if not candidate.exists():
            failed.append(
                {
                    "path": raw_path,
                    "code": "MEDIA_FILE_NOT_FOUND",
                    "message": f"Media path not found: {candidate}",
                }
            )
            continue

        if candidate.is_dir():
            directory_files = sorted(
                file_path
                for file_path in candidate.rglob("*")
                if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_MEDIA_EXTENSIONS
            )
            if not directory_files:
                failed.append(
                    {
                        "path": raw_path,
                        "code": "MEDIA_FILE_NOT_FOUND",
                        "message": f"No supported media files found in directory: {candidate}",
                    }
                )
                continue
            for file_path in directory_files:
                key = str(file_path.resolve())
                if key not in seen:
                    seen.add(key)
                    resolved.append(file_path)
            continue

        key = str(candidate.resolve())
        if key not in seen:
            seen.add(key)
            resolved.append(candidate)

    return resolved
