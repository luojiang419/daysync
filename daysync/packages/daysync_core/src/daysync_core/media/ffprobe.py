from __future__ import annotations

import json
import subprocess
from fractions import Fraction
from pathlib import Path

from daysync_core.errors import DaySyncError
from daysync_core.utils import new_uuid
from .runtime import resolve_ffprobe_binary


def run_ffprobe(path: str | Path) -> dict[str, object]:
    media_path = Path(path)
    if not media_path.exists():
        raise DaySyncError(
            "MEDIA_FILE_NOT_FOUND",
            f"Media file not found: {media_path}",
            {"path": str(media_path)},
        )

    binary = resolve_ffprobe_binary()
    completed = subprocess.run(
        [
            binary,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(media_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(completed.stdout)


def probe_media(path: str | Path) -> dict[str, object]:
    media_path = Path(path)
    payload = run_ffprobe(media_path)
    return parse_ffprobe_payload(media_path, payload)


def parse_ffprobe_payload(path: str | Path, payload: dict[str, object]) -> dict[str, object]:
    media_path = Path(path)
    format_payload = payload.get("format") or {}
    streams = payload.get("streams") or []
    if not isinstance(streams, list):
        raise DaySyncError("MEDIA_DURATION_INVALID", f"Invalid ffprobe payload for {media_path}")

    has_video = any(stream.get("codec_type") == "video" for stream in streams)
    has_audio = any(stream.get("codec_type") == "audio" for stream in streams)
    media_type = "video" if has_video else "audio" if has_audio else None
    if media_type is None:
        raise DaySyncError(
            "MEDIA_TYPE_MISMATCH",
            f"Unsupported media type for {media_path}",
            {"path": str(media_path)},
        )

    duration_ms = _parse_duration_ms(format_payload, streams)
    if duration_ms <= 0:
        raise DaySyncError(
            "MEDIA_DURATION_INVALID",
            f"Media duration is invalid for {media_path}",
            {"path": str(media_path)},
        )

    return {
        "media_type": media_type,
        "duration_ms": duration_ms,
        "container": format_payload.get("format_name"),
        "has_video": has_video,
        "has_audio": has_audio,
        "streams": [_parse_stream(stream) for stream in streams],
    }


def _parse_duration_ms(format_payload: dict[str, object], streams: list[dict[str, object]]) -> int:
    raw_duration = format_payload.get("duration")
    if raw_duration not in (None, ""):
        return int(round(float(raw_duration) * 1000))
    for stream in streams:
        stream_duration = stream.get("duration")
        if stream_duration not in (None, ""):
            return int(round(float(stream_duration) * 1000))
    return 0


def _parse_stream(stream: dict[str, object]) -> dict[str, object]:
    frame_rate_num = None
    frame_rate_den = None
    rate_value = stream.get("avg_frame_rate") or stream.get("r_frame_rate")
    if isinstance(rate_value, str) and rate_value not in {"0/0", "N/A"}:
        fraction = Fraction(rate_value)
        frame_rate_num = fraction.numerator
        frame_rate_den = fraction.denominator

    stream_type = stream.get("codec_type") or "other"
    if stream_type not in {"video", "audio", "subtitle", "other"}:
        stream_type = "other"

    duration_ms = None
    if stream.get("duration") not in (None, ""):
        duration_ms = int(round(float(stream["duration"]) * 1000))

    return {
        "id": new_uuid(),
        "stream_index": int(stream.get("index", 0)),
        "stream_type": stream_type,
        "codec": stream.get("codec_name"),
        "sample_rate": _maybe_int(stream.get("sample_rate")),
        "channels": _maybe_int(stream.get("channels")),
        "width": _maybe_int(stream.get("width")),
        "height": _maybe_int(stream.get("height")),
        "frame_rate_num": frame_rate_num,
        "frame_rate_den": frame_rate_den,
        "duration_ms": duration_ms,
        "raw_json": json.dumps(stream, ensure_ascii=False),
    }


def _maybe_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    return int(value)
