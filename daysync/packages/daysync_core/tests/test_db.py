from __future__ import annotations

from pathlib import Path

from daysync_core.db import connect_database, create_project, database_path_for_project


def test_db_init_creates_tables(tmp_path: Path) -> None:
    project = create_project(str(tmp_path / "project"), "测试", "2026-05-17")
    with connect_database(database_path_for_project(project["root_path"])) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            ).fetchall()
        }
    assert "projects" in tables
    assert "media_files" in tables
    assert "subtitles_fts" in tables


def test_db_pragmas(tmp_path: Path) -> None:
    project = create_project(str(tmp_path / "project"), "测试", "2026-05-17")
    with connect_database(database_path_for_project(project["root_path"])) as connection:
        journal_mode = connection.execute("PRAGMA journal_mode;").fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_keys;").fetchone()[0]
    assert journal_mode.lower() == "wal"
    assert foreign_keys == 1
