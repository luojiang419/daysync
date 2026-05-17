from __future__ import annotations

import os
import threading

from fastapi import APIRouter

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/shutdown")
def shutdown_service() -> dict[str, str]:
    threading.Timer(0.2, lambda: os._exit(0)).start()
    return {"status": "shutting_down"}
