from __future__ import annotations

from fastapi.testclient import TestClient

from services.api.main import app


def test_local_dev_origin_receives_cors_headers() -> None:
    client = TestClient(app)

    response = client.get("/", headers={"Origin": "http://127.0.0.1:1420"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:1420"
    assert response.headers["access-control-allow-credentials"] == "true"
