from fastapi.testclient import TestClient

from app.main import app


def test_audit_events_require_admin_token() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/admin/audit-events")
    assert response.status_code == 401


def test_admin_can_query_pii_free_audit_events() -> None:
    with TestClient(app) as client:
        uploaded = client.post(
            "/api/v1/documents",
            files={"file": ("contract.txt", b"loan contract", "text/plain")},
        )
        response = client.get(
            "/api/v1/admin/audit-events",
            params={"document_id": uploaded.json()["id"]},
            headers={"X-Admin-Token": "test-admin-token"},
        )
    assert response.status_code == 200
    assert response.json()[0]["event_type"] == "document_uploaded"
    assert "original_filename" not in response.json()[0]
