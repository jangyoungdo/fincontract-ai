from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


SAMPLE = "제1조 은행은 필요하다고 인정하는 경우 서비스 내용을 일방적으로 변경할 수 있다."


def test_txt_upload_analysis_report_and_delete() -> None:
    with TestClient(app) as client:
        uploaded = client.post(
            "/api/v1/documents",
            files={"file": ("terms.txt", SAMPLE.encode(), "text/plain")},
        )
        assert uploaded.status_code == 201, uploaded.text
        document_id = uploaded.json()["id"]

        analyzed = client.post(
            f"/api/v1/documents/{document_id}/analyses", json={"experiment_arm": "D"}
        )
        assert analyzed.status_code == 201, analyzed.text
        body = analyzed.json()
        assert body["status"] == "completed"
        assert len(body["result"]["findings"]) == 1

        report = client.get(f"/api/v1/analyses/{body['id']}/report")
        assert report.status_code == 200
        assert "법률 판단이 아닌" in report.json()["disclaimer"]

        deleted = client.delete(f"/api/v1/documents/{document_id}")
        assert deleted.status_code == 200
        assert deleted.json()["status"] == "deleted"


def test_rejects_spoofed_pdf() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/documents",
            files={"file": ("fake.pdf", b"not a pdf", "application/pdf")},
        )
    assert response.status_code == 400
    assert "시그니처" in response.json()["detail"]
