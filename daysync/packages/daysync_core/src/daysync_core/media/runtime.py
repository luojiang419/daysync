from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

from daysync_core.errors import DaySyncError
from daysync_core.utils import utc_now_iso

FFMPEG_ARCHIVE_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
FFMPEG_ARCHIVE_SHA256_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip.sha256"


@dataclass(slots=True)
class FFmpegRuntimeStatus:
    ready: bool
    source: str | None
    version: str | None
    root_path: str
    ffmpeg_path: str | None
    ffprobe_path: str | None
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def workspace_root() -> Path:
    return Path(__file__).resolve().parents[5]


def ffmpeg_runtime_root(root_path: Path | None = None) -> Path:
    base_root = root_path or workspace_root()
    return base_root / "tools" / "ffmpeg" / "windows-x64"


def resolve_ffmpeg_binary(root_path: Path | None = None) -> str:
    status = ensure_ffmpeg_runtime(root_path=root_path)
    if not status.ffmpeg_path:
        raise DaySyncError("FFMPEG_NOT_FOUND", status.error or "ffmpeg executable was not found")
    return status.ffmpeg_path


def resolve_ffprobe_binary(root_path: Path | None = None) -> str:
    status = ensure_ffmpeg_runtime(root_path=root_path)
    if not status.ffprobe_path:
        raise DaySyncError("FFMPEG_NOT_FOUND", status.error or "ffprobe executable was not found")
    return status.ffprobe_path


def get_ffmpeg_runtime_status(
    root_path: Path | None = None,
    *,
    auto_download: bool = False,
) -> FFmpegRuntimeStatus:
    runtime_root = ffmpeg_runtime_root(root_path)

    env_pair = _resolve_env_pair()
    if env_pair is not None:
        return _build_status(runtime_root, "env", env_pair[0], env_pair[1])

    local_pair = _resolve_project_local_pair(runtime_root)
    if local_pair is not None:
        return _build_status(runtime_root, "project-local", local_pair[0], local_pair[1])

    path_pair = _resolve_path_pair()
    if path_pair is not None:
        return _build_status(runtime_root, "path", path_pair[0], path_pair[1])

    if auto_download:
        return _download_and_install_runtime(runtime_root)

    return FFmpegRuntimeStatus(
        ready=False,
        source=None,
        version=_read_manifest_value(runtime_root, "version"),
        root_path=str(runtime_root),
        ffmpeg_path=None,
        ffprobe_path=None,
        error="ffmpeg/ffprobe are not available yet",
    )


def ensure_ffmpeg_runtime(root_path: Path | None = None) -> FFmpegRuntimeStatus:
    status = get_ffmpeg_runtime_status(root_path=root_path, auto_download=True)
    if not status.ready:
        raise DaySyncError("FFMPEG_NOT_FOUND", status.error or "Failed to prepare FFmpeg runtime")
    return status


def ffmpeg_status_from_exception(
    error: Exception,
    root_path: Path | None = None,
) -> FFmpegRuntimeStatus:
    runtime_root = ffmpeg_runtime_root(root_path)
    error_message = error.message if isinstance(error, DaySyncError) else str(error)
    return FFmpegRuntimeStatus(
        ready=False,
        source=None,
        version=_read_manifest_value(runtime_root, "version"),
        root_path=str(runtime_root),
        ffmpeg_path=None,
        ffprobe_path=None,
        error=error_message,
    )


def _resolve_env_pair() -> tuple[Path, Path] | None:
    ffmpeg_value = os.getenv("DAYSYNC_FFMPEG_BIN")
    ffprobe_value = os.getenv("DAYSYNC_FFPROBE_BIN")
    if not ffmpeg_value or not ffprobe_value:
        return None
    ffmpeg_path = Path(ffmpeg_value)
    ffprobe_path = Path(ffprobe_value)
    if ffmpeg_path.exists() and ffprobe_path.exists():
        return ffmpeg_path, ffprobe_path
    return None


def _resolve_project_local_pair(runtime_root: Path) -> tuple[Path, Path] | None:
    ffmpeg_path = runtime_root / "current" / "bin" / "ffmpeg.exe"
    ffprobe_path = runtime_root / "current" / "bin" / "ffprobe.exe"
    if ffmpeg_path.exists() and ffprobe_path.exists():
        return ffmpeg_path, ffprobe_path
    return None


def _resolve_path_pair() -> tuple[Path, Path] | None:
    ffmpeg_bin = shutil.which("ffmpeg")
    ffprobe_bin = shutil.which("ffprobe")
    if ffmpeg_bin and ffprobe_bin:
        return Path(ffmpeg_bin), Path(ffprobe_bin)
    return None


def _build_status(
    runtime_root: Path,
    source: str,
    ffmpeg_path: Path,
    ffprobe_path: Path,
) -> FFmpegRuntimeStatus:
    version = _read_manifest_value(runtime_root, "version") or _parse_version_from_path(ffmpeg_path)
    return FFmpegRuntimeStatus(
        ready=True,
        source=source,
        version=version,
        root_path=str(runtime_root),
        ffmpeg_path=str(ffmpeg_path),
        ffprobe_path=str(ffprobe_path),
        error=None,
    )


def _download_and_install_runtime(runtime_root: Path) -> FFmpegRuntimeStatus:
    downloads_dir = runtime_root / "downloads"
    versions_dir = runtime_root / "versions"
    current_dir = runtime_root / "current"
    downloads_dir.mkdir(parents=True, exist_ok=True)
    versions_dir.mkdir(parents=True, exist_ok=True)

    archive_path = downloads_dir / "ffmpeg-release-essentials.zip"
    archive_bytes = _download_bytes(FFMPEG_ARCHIVE_URL)
    archive_path.write_bytes(archive_bytes)

    expected_sha256 = _download_bytes(FFMPEG_ARCHIVE_SHA256_URL).decode("utf-8").strip().split()[0]
    actual_sha256 = hashlib.sha256(archive_bytes).hexdigest()
    if actual_sha256.lower() != expected_sha256.lower():
        raise DaySyncError(
            "FFMPEG_NOT_FOUND",
            "Downloaded FFmpeg archive failed checksum validation",
            {"expected_sha256": expected_sha256, "actual_sha256": actual_sha256},
        )

    with zipfile.ZipFile(archive_path) as archive:
        top_level_members = [Path(name).parts[0] for name in archive.namelist() if name and not name.endswith("/")]
        if not top_level_members:
            raise DaySyncError("FFMPEG_NOT_FOUND", "Downloaded FFmpeg archive is empty")
        release_folder = top_level_members[0]
        extracted_root = versions_dir / release_folder
        if extracted_root.exists():
            shutil.rmtree(extracted_root)
        archive.extractall(versions_dir)

    extracted_bin_dir = extracted_root / "bin"
    ffmpeg_path = extracted_bin_dir / "ffmpeg.exe"
    ffprobe_path = extracted_bin_dir / "ffprobe.exe"
    if not ffmpeg_path.exists() or not ffprobe_path.exists():
        raise DaySyncError(
            "FFMPEG_NOT_FOUND",
            "Downloaded FFmpeg archive does not contain ffmpeg.exe and ffprobe.exe",
        )

    if current_dir.exists():
        shutil.rmtree(current_dir)
    shutil.copytree(extracted_root, current_dir)

    manifest = {
        "version": _parse_version_from_path(extracted_root),
        "source_url": FFMPEG_ARCHIVE_URL,
        "sha256": actual_sha256,
        "installed_at": utc_now_iso(),
        "archive_name": archive_path.name,
        "root_path": str(current_dir),
    }
    (runtime_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return FFmpegRuntimeStatus(
        ready=True,
        source="downloaded",
        version=manifest["version"],
        root_path=str(runtime_root),
        ffmpeg_path=str(current_dir / "bin" / "ffmpeg.exe"),
        ffprobe_path=str(current_dir / "bin" / "ffprobe.exe"),
        error=None,
    )


def _download_bytes(url: str) -> bytes:
    try:
        response = httpx.get(url, timeout=120.0, follow_redirects=True)
        response.raise_for_status()
        return response.content
    except httpx.HTTPError as exc:
        raise DaySyncError(
            "FFMPEG_NOT_FOUND",
            f"Failed to download FFmpeg runtime from {url}",
            {"url": url, "reason": str(exc)},
        ) from exc


def _read_manifest_value(runtime_root: Path, key: str) -> str | None:
    manifest_path = runtime_root / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    value = manifest.get(key)
    return value if isinstance(value, str) else None


def _parse_version_from_path(path: Path) -> str | None:
    match = re.search(r"ffmpeg-(?P<version>[\d.]+)-essentials_build", str(path))
    if match is not None:
        return match.group("version")
    return None
