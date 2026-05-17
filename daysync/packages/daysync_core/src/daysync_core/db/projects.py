from __future__ import annotations

import sqlite3
from pathlib import Path

from daysync_core.errors import DaySyncError
from daysync_core.media.service import list_media
from daysync_core.sync.service import list_sync_results
from daysync_core.timeline.service import list_flat_timelines
from daysync_core.utils import new_uuid, utc_now_iso

from .database import (
    DB_FILE_NAME,
    SCHEMA_VERSION,
    PROJECT_FILE_NAME,
    connect_database,
    database_path_for_project,
    initialize_database,
    load_project_metadata,
    project_file_path,
    transaction,
    write_project_metadata,
)


def create_project(root_path: str, name: str, shooting_date: str | None) -> dict[str, object]:
    path = Path(root_path)
    path.mkdir(parents=True, exist_ok=True)
    metadata_path = project_file_path(path)
    db_path = database_path_for_project(path)

    if metadata_path.exists() or db_path.exists():
        raise DaySyncError(
            "PROJECT_PATH_INVALID",
            f"Project already exists at {path}",
            {"root_path": str(path)},
        )

    _assert_writable(path)
    now = utc_now_iso()
    project = {
        "id": new_uuid(),
        "name": name,
        "root_path": str(path),
        "shooting_date": shooting_date,
        "schema_version": SCHEMA_VERSION,
        "created_at": now,
        "updated_at": now,
    }

    initialize_database(db_path)
    with connect_database(db_path) as connection, transaction(connection):
        _upsert_project_record(connection, project)
    write_project_metadata(path, project)
    return project


def open_project(root_path: str) -> dict[str, object]:
    path = Path(root_path)
    metadata_path = project_file_path(path)
    db_path = database_path_for_project(path)

    if not metadata_path.exists() or not db_path.exists():
        raise DaySyncError(
            "PROJECT_NOT_FOUND",
            f"Project not found at {path}",
            {"root_path": str(path)},
        )

    project = load_project_metadata(path)
    with connect_database(db_path) as connection:
        row = connection.execute(
            "SELECT id, name, root_path, shooting_date, schema_version, created_at, updated_at "
            "FROM projects WHERE id = ?",
            (project["id"],),
        ).fetchone()
        if row is None:
            raise DaySyncError(
                "PROJECT_NOT_FOUND",
                f"Project database record not found at {path}",
                {"root_path": str(path)},
            )
        return dict(row)


def project_snapshot(root_path: str) -> dict[str, object]:
    project = open_project(root_path)
    db_path = database_path_for_project(root_path)
    with connect_database(db_path) as connection:
        stats = {
            "media_count": connection.execute(
                "SELECT COUNT(*) FROM media_files WHERE project_id = ?",
                (project["id"],),
            ).fetchone()[0],
            "subtitle_count": connection.execute(
                "SELECT COUNT(*) FROM subtitles s "
                "JOIN subtitle_tracks st ON st.id = s.track_id "
                "WHERE st.project_id = ?",
                (project["id"],),
            ).fetchone()[0],
            "sync_result_count": connection.execute(
                "SELECT COUNT(*) FROM sync_results WHERE project_id = ?",
                (project["id"],),
            ).fetchone()[0],
        }
        return {
            "project": project,
            "stats": stats,
            "media_files": list_media(connection, project["id"]),
            "flat_timelines": list_flat_timelines(connection, project["id"]),
            "sync_results": list_sync_results(connection, project["id"]),
        }


def _upsert_project_record(connection: sqlite3.Connection, project: dict[str, object]) -> None:
    connection.execute(
        """
        INSERT INTO projects (id, name, root_path, shooting_date, schema_version, created_at, updated_at)
        VALUES (:id, :name, :root_path, :shooting_date, :schema_version, :created_at, :updated_at)
        ON CONFLICT(id) DO UPDATE SET
          name = excluded.name,
          root_path = excluded.root_path,
          shooting_date = excluded.shooting_date,
          schema_version = excluded.schema_version,
          updated_at = excluded.updated_at
        """,
        project,
    )


def _assert_writable(path: Path) -> None:
    probe = path / ".daysync_write_probe"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        raise DaySyncError(
            "PROJECT_PATH_INVALID",
            f"Project path is not writable: {path}",
            {"root_path": str(path), "reason": str(exc)},
        ) from exc
