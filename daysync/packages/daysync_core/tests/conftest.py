from __future__ import annotations

from pathlib import Path

import pytest

from daysync_core.db import connect_database, create_project, database_path_for_project


@pytest.fixture()
def sample_root() -> Path:
    return Path(__file__).resolve().parents[3] / "sample_data"


@pytest.fixture()
def project_workspace(tmp_path: Path) -> tuple[dict[str, object], object]:
    root_path = tmp_path / "project"
    project = create_project(str(root_path), "测试项目", "2026-05-17")
    connection = connect_database(database_path_for_project(root_path))
    try:
        yield project, connection
    finally:
        connection.close()
