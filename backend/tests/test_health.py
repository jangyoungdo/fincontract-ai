from fastapi.testclient import TestClient

from app.main import app


def test_health_live() -> None:
    with TestClient(app) as client:
        response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_health_ready_creates_all_five_collections() -> None:
    with TestClient(app) as client:
        response = client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["checks"]["database"]["status"] == "ready"
    assert body["checks"]["chroma"] == {"status": "ready", "collections": "5"}
