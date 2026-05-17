from __future__ import annotations

from dataclasses import dataclass, field

from daysync_core.errors import DaySyncError


@dataclass
class AppState:
    project_roots: dict[str, str] = field(default_factory=dict)
    ffmpeg_status: dict[str, object] | None = None

    def register(self, project_id: str, root_path: str) -> None:
        self.project_roots[project_id] = root_path

    def resolve(self, project_id: str) -> str:
        root_path = self.project_roots.get(project_id)
        if root_path is None:
            raise DaySyncError(
                "PROJECT_NOT_FOUND",
                "Project is not opened in the current service session",
                {"project_id": project_id},
            )
        return root_path
