from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request) -> dict[str, object]:
    return {
        "status": "ok",
        "registered_projects": len(request.app.state.runtime.project_roots),
    }
