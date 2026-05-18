from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_bridge_worker_uses_utf8_pipe_io_for_chinese_workspace_path() -> None:
    workspace_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["DAYSYNC_WORKSPACE_ROOT"] = str(workspace_root)
    pythonpath_parts = [
        str(workspace_root),
        str(workspace_root / "packages" / "daysync_core" / "src"),
    ]
    existing_pythonpath = env.get("PYTHONPATH")
    if existing_pythonpath:
        pythonpath_parts.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)

    process = subprocess.Popen(
        [sys.executable, "-m", "daysync_core.bridge.worker"],
        cwd=workspace_root,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        assert process.stdin is not None
        assert process.stdout is not None
        process.stdin.write(b'{"id":1,"method":"health.check","payload":{}}\n')
        process.stdin.flush()

        line = process.stdout.readline()
        assert line, "worker did not return a health.check response"

        response = json.loads(line.decode("utf-8"))
        assert response["ok"] is True
        assert "自动合板软件" in response["result"]["ffmpeg"]["root_path"]
    finally:
        process.kill()
        process.wait(timeout=5)
