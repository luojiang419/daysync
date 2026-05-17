from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from daysync_core.utils import ensure_parent_directory

DB_FILE_NAME = "daysync.sqlite"
PROJECT_FILE_NAME = "daysync.project.json"
SCHEMA_VERSION = "0.1"


def database_path_for_project(root_path: Path | str) -> Path:
    return Path(root_path) / DB_FILE_NAME


def project_file_path(root_path: Path | str) -> Path:
    return Path(root_path) / PROJECT_FILE_NAME


def connect_database(db_path: Path | str) -> sqlite3.Connection:
    connection = sqlite3.connect(Path(db_path))
    connection.row_factory = sqlite3.Row
    apply_pragmas(connection)
    return connection


def apply_pragmas(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA journal_mode=WAL;")
    connection.execute("PRAGMA synchronous=NORMAL;")
    connection.execute("PRAGMA foreign_keys=ON;")


def initialize_database(db_path: Path | str) -> None:
    db_path = Path(db_path)
    ensure_parent_directory(db_path)
    schema = load_schema()
    with connect_database(db_path) as connection:
        connection.executescript(schema)
        connection.commit()


def load_schema() -> str:
    return (Path(__file__).with_name("schema.sql")).read_text(encoding="utf-8")


def write_project_metadata(root_path: Path | str, metadata: dict[str, object]) -> None:
    path = project_file_path(root_path)
    ensure_parent_directory(path)
    path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


def load_project_metadata(root_path: Path | str) -> dict[str, object]:
    return json.loads(project_file_path(root_path).read_text(encoding="utf-8"))


@contextmanager
def transaction(connection: sqlite3.Connection):
    try:
        yield connection
    except Exception:
        connection.rollback()
        raise
    else:
        connection.commit()
