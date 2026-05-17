from __future__ import annotations

import re
from dataclasses import dataclass

from daysync_core.errors import DaySyncError

SRT_TIME_PATTERN = re.compile(
    r"^(?P<start>\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(?P<end>\d{2}:\d{2}:\d{2},\d{3})$"
)


@dataclass(slots=True)
class ParsedSubtitle:
    subtitle_index: int
    flat_start_ms: int
    flat_end_ms: int
    raw_text: str


def parse_srt(content: str) -> list[ParsedSubtitle]:
    lines = content.replace("\ufeff", "").splitlines()
    subtitles: list[ParsedSubtitle] = []
    block: list[tuple[int, str]] = []

    def flush(current_block: list[tuple[int, str]]) -> None:
        if not current_block:
            return
        if len(current_block) < 3:
            raise DaySyncError(
                "SUBTITLE_PARSE_FAILED",
                f"Failed to parse SRT file at line {current_block[0][0]}",
                {"line": current_block[0][0]},
            )
        index_line_no, index_text = current_block[0]
        time_line_no, time_text = current_block[1]
        try:
            subtitle_index = int(index_text.strip())
        except ValueError as exc:
            raise DaySyncError(
                "SUBTITLE_PARSE_FAILED",
                f"Failed to parse SRT file at line {index_line_no}",
                {"line": index_line_no},
            ) from exc
        match = SRT_TIME_PATTERN.match(time_text.strip())
        if match is None:
            raise DaySyncError(
                "SUBTITLE_PARSE_FAILED",
                f"Failed to parse SRT file at line {time_line_no}",
                {"line": time_line_no},
            )
        raw_text = "\n".join(text for _, text in current_block[2:]).strip()
        subtitles.append(
            ParsedSubtitle(
                subtitle_index=subtitle_index,
                flat_start_ms=_parse_timestamp(match.group("start")),
                flat_end_ms=_parse_timestamp(match.group("end")),
                raw_text=raw_text,
            )
        )

    for line_number, line in enumerate(lines, start=1):
        if line.strip():
            block.append((line_number, line))
            continue
        flush(block)
        block = []

    flush(block)
    return subtitles


def _parse_timestamp(value: str) -> int:
    hours, minutes, seconds_millis = value.split(":")
    seconds, millis = seconds_millis.split(",")
    return (
        int(hours) * 3600000
        + int(minutes) * 60000
        + int(seconds) * 1000
        + int(millis)
    )
