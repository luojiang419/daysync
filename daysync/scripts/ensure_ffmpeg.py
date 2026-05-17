from __future__ import annotations

import json

from daysync_core.media import ensure_ffmpeg_runtime


def main() -> None:
    status = ensure_ffmpeg_runtime()
    print(json.dumps(status.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
