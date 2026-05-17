from __future__ import annotations

import io
import zipfile
from pathlib import Path

import httpx
import pytest

from daysync_core.errors import DaySyncError
from daysync_core.media.runtime import ensure_ffmpeg_runtime, get_ffmpeg_runtime_status


class DummyResponse:
    def __init__(self, content: bytes, status_code: int = 200) -> None:
        self.content = content
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "request failed",
                request=httpx.Request("GET", "https://example.com"),
                response=httpx.Response(self.status_code),
            )


def test_ffmpeg_runtime_prefers_env_over_local_and_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime_root = tmp_path / "tools" / "ffmpeg" / "windows-x64"
    local_bin = runtime_root / "current" / "bin"
    local_bin.mkdir(parents=True, exist_ok=True)
    (local_bin / "ffmpeg.exe").write_text("local", encoding="utf-8")
    (local_bin / "ffprobe.exe").write_text("local", encoding="utf-8")

    env_dir = tmp_path / "env-bin"
    env_dir.mkdir()
    env_ffmpeg = env_dir / "ffmpeg.exe"
    env_ffprobe = env_dir / "ffprobe.exe"
    env_ffmpeg.write_text("env", encoding="utf-8")
    env_ffprobe.write_text("env", encoding="utf-8")
    monkeypatch.setenv("DAYSYNC_FFMPEG_BIN", str(env_ffmpeg))
    monkeypatch.setenv("DAYSYNC_FFPROBE_BIN", str(env_ffprobe))
    monkeypatch.setattr("daysync_core.media.runtime.shutil.which", lambda _: str(tmp_path / "path.exe"))

    status = get_ffmpeg_runtime_status(root_path=tmp_path, auto_download=False)
    assert status.ready is True
    assert status.source == "env"
    assert status.ffmpeg_path == str(env_ffmpeg)


def test_ffmpeg_runtime_prefers_project_local_over_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime_root = tmp_path / "tools" / "ffmpeg" / "windows-x64" / "current" / "bin"
    runtime_root.mkdir(parents=True, exist_ok=True)
    ffmpeg_path = runtime_root / "ffmpeg.exe"
    ffprobe_path = runtime_root / "ffprobe.exe"
    ffmpeg_path.write_text("local", encoding="utf-8")
    ffprobe_path.write_text("local", encoding="utf-8")
    monkeypatch.delenv("DAYSYNC_FFMPEG_BIN", raising=False)
    monkeypatch.delenv("DAYSYNC_FFPROBE_BIN", raising=False)
    monkeypatch.setattr("daysync_core.media.runtime.shutil.which", lambda _: str(tmp_path / "path.exe"))

    status = get_ffmpeg_runtime_status(root_path=tmp_path, auto_download=False)
    assert status.ready is True
    assert status.source == "project-local"
    assert status.ffprobe_path == str(ffprobe_path)


def test_ffmpeg_runtime_uses_path_when_local_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("DAYSYNC_FFMPEG_BIN", raising=False)
    monkeypatch.delenv("DAYSYNC_FFPROBE_BIN", raising=False)
    path_dir = tmp_path / "path-bin"
    path_dir.mkdir()
    ffmpeg_path = path_dir / "ffmpeg.exe"
    ffprobe_path = path_dir / "ffprobe.exe"
    ffmpeg_path.write_text("path", encoding="utf-8")
    ffprobe_path.write_text("path", encoding="utf-8")

    def fake_which(binary: str) -> str | None:
        if binary == "ffmpeg":
            return str(ffmpeg_path)
        if binary == "ffprobe":
            return str(ffprobe_path)
        return None

    monkeypatch.setattr("daysync_core.media.runtime.shutil.which", fake_which)

    status = get_ffmpeg_runtime_status(root_path=tmp_path, auto_download=False)
    assert status.ready is True
    assert status.source == "path"


def test_ffmpeg_runtime_auto_download_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("DAYSYNC_FFMPEG_BIN", raising=False)
    monkeypatch.delenv("DAYSYNC_FFPROBE_BIN", raising=False)
    monkeypatch.setattr("daysync_core.media.runtime.shutil.which", lambda _: None)
    archive_bytes = _build_ffmpeg_zip_bytes()
    checksum = __import__("hashlib").sha256(archive_bytes).hexdigest().encode("utf-8")

    def fake_get(url: str, timeout: float, follow_redirects: bool) -> DummyResponse:
        if url.endswith(".sha256"):
            return DummyResponse(checksum)
        return DummyResponse(archive_bytes)

    monkeypatch.setattr("daysync_core.media.runtime.httpx.get", fake_get)

    status = ensure_ffmpeg_runtime(root_path=tmp_path)
    assert status.ready is True
    assert status.source == "downloaded"
    assert status.version == "8.1.1"
    assert Path(status.ffmpeg_path).exists()
    assert (tmp_path / "tools" / "ffmpeg" / "windows-x64" / "manifest.json").exists()


def test_ffmpeg_runtime_checksum_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("DAYSYNC_FFMPEG_BIN", raising=False)
    monkeypatch.delenv("DAYSYNC_FFPROBE_BIN", raising=False)
    monkeypatch.setattr("daysync_core.media.runtime.shutil.which", lambda _: None)
    archive_bytes = _build_ffmpeg_zip_bytes()

    def fake_get(url: str, timeout: float, follow_redirects: bool) -> DummyResponse:
        if url.endswith(".sha256"):
            return DummyResponse(b"deadbeef")
        return DummyResponse(archive_bytes)

    monkeypatch.setattr("daysync_core.media.runtime.httpx.get", fake_get)

    with pytest.raises(DaySyncError) as exc_info:
        ensure_ffmpeg_runtime(root_path=tmp_path)
    assert exc_info.value.code == "FFMPEG_NOT_FOUND"


def test_ffmpeg_runtime_download_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("DAYSYNC_FFMPEG_BIN", raising=False)
    monkeypatch.delenv("DAYSYNC_FFPROBE_BIN", raising=False)
    monkeypatch.setattr("daysync_core.media.runtime.shutil.which", lambda _: None)

    def fake_get(url: str, timeout: float, follow_redirects: bool) -> DummyResponse:
        raise httpx.ConnectError("network down", request=httpx.Request("GET", url))

    monkeypatch.setattr("daysync_core.media.runtime.httpx.get", fake_get)

    with pytest.raises(DaySyncError) as exc_info:
        ensure_ffmpeg_runtime(root_path=tmp_path)
    assert exc_info.value.code == "FFMPEG_NOT_FOUND"


def _build_ffmpeg_zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ffmpeg-8.1.1-essentials_build/bin/ffmpeg.exe", "fake ffmpeg")
        archive.writestr("ffmpeg-8.1.1-essentials_build/bin/ffprobe.exe", "fake ffprobe")
        archive.writestr("ffmpeg-8.1.1-essentials_build/LICENSE", "license")
    return buffer.getvalue()
