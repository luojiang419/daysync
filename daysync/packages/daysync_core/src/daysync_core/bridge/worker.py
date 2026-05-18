from __future__ import annotations

import json
import sys

from .dispatcher import RuntimeDispatcher, RuntimeState, dispatch_message


def main() -> int:
    dispatcher = RuntimeDispatcher(RuntimeState())

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            response = {
                "id": None,
                "ok": False,
                "error": {
                    "code": "INVALID_MESSAGE",
                    "message": "request must be valid JSON",
                    "details": {"reason": str(exc)},
                },
            }
        else:
            response = dispatch_message(dispatcher, message)

        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
