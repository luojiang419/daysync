from __future__ import annotations

import unicodedata


def normalize_subtitle_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).lower().strip()
    buffer: list[str] = []
    for char in normalized:
        category = unicodedata.category(char)
        if char.isspace():
            continue
        if _is_cjk(char) or char.isalnum():
            buffer.append(char)
            continue
        if category.startswith("P") or category.startswith("S"):
            continue
    return "".join(buffer)


def _is_cjk(char: str) -> bool:
    codepoint = ord(char)
    return 0x4E00 <= codepoint <= 0x9FFF
