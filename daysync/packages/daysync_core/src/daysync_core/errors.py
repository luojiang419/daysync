from __future__ import annotations

from dataclasses import dataclass, field


ERROR_HTTP_STATUS: dict[str, int] = {
    "PROJECT_NOT_FOUND": 404,
    "PROJECT_PATH_INVALID": 400,
    "MEDIA_FILE_NOT_FOUND": 404,
    "MEDIA_TYPE_MISMATCH": 400,
    "MEDIA_DURATION_INVALID": 400,
    "FFMPEG_NOT_FOUND": 500,
    "SUBTITLE_PARSE_FAILED": 400,
    "SUBTITLE_MAPPING_FAILED": 400,
    "ANCHOR_SUBTITLE_INVALID": 400,
    "SYNC_RESULT_NOT_FOUND": 404,
    "EXPORT_FAILED": 500,
}


@dataclass(slots=True)
class DaySyncError(Exception):
    code: str
    message: str
    details: dict[str, object] = field(default_factory=dict)

    @property
    def http_status(self) -> int:
        return ERROR_HTTP_STATUS.get(self.code, 400)

    def to_dict(self) -> dict[str, object]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }
