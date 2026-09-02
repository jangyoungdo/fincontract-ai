from fastapi.testclient import TestClient

from app.main import app
from app.vectorstore.client import COLLECTION_NAMES


def test_health_live() -> None:
    with TestClient(app) as client:
        response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_health_ready_creates_all_known_collections() -> None:
    with TestClient(app) as client:
        response = client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["checks"]["database"]["status"] == "ready"
    assert body["checks"]["chroma"] == {"status": "ready", "collections": str(len(COLLECTION_NAMES))}


def test_worker_status_is_explicit_when_redis_is_disabled() -> None:
    with TestClient(app) as client:
        response = client.get("/health/worker")
    assert response.status_code == 200
    assert response.json() == {"status": "disabled", "queue_depth": 0, "dead_letter_depth": 0}
