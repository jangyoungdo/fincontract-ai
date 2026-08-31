from io import BytesIO
from pathlib import Path

from docx import Document
from fastapi.testclient import TestClient

from app.main import app
from app.models import AuditEvent, DocumentRecord, get_session_factory

SAMPLE = "제1조 은행은 필요하다고 인정하는 경우 서비스 내용을 일방적으로 변경할 수 있다."


def test_txt_upload_analysis_report_and_delete() -> None:
    with TestClient(app) as client:
        uploaded = client.post(
            "/api/v1/documents",
            files={"file": ("terms.txt", SAMPLE.encode(), "text/plain")},
        )
        assert uploaded.status_code == 201, uploaded.text
        document_id = uploaded.json()["id"]
        with get_session_factory()() as session:
            stored = session.get(DocumentRecord, document_id)
            assert stored is not None
            encrypted = Path(stored.storage_path).read_bytes()
            assert SAMPLE.encode() not in encrypted
            assert stored.storage_path.endswith(".txt.enc")

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
        with get_session_factory()() as session:
            event_types = {
                event.event_type
                for event in session.query(AuditEvent).filter(AuditEvent.document_id == document_id)
            }
        assert {"document_uploaded", "analysis_created", "analysis_completed", "document_deleted"}.issubset(event_types)


def test_rejects_spoofed_pdf() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/documents",
            files={"file": ("fake.pdf", b"not a pdf", "application/pdf")},
        )
    assert response.status_code == 400
    assert "시그니처" in response.json()["detail"]


def test_real_docx_upload_extracts_and_analyzes_text() -> None:
    stream = BytesIO()
    document = Document()
    document.add_paragraph(SAMPLE)
    document.save(stream)
    with TestClient(app) as client:
        uploaded = client.post(
            "/api/v1/documents",
            files={"file": ("terms.docx", stream.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        assert uploaded.status_code == 201, uploaded.text
        analyzed = client.post(f"/api/v1/documents/{uploaded.json()['id']}/analyses", json={"experiment_arm": "A"})
    assert analyzed.status_code == 201, analyzed.text
    assert len(analyzed.json()["result"]["findings"]) == 1


def test_real_pdf_upload_extracts_and_analyzes_text() -> None:
    # A compact, valid one-page PDF fixture with a literal text stream.
    pdf = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Resources<</Font<</F1 4 0 R>>>>/Contents 5 0 R>>endobj
4 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
5 0 obj<</Length 95>>stream
BT /F1 12 Tf 72 720 Td (Bank may unilaterally change service terms when necessary.) Tj ET
endstream endobj
xref
0 6
0000000000 65535 f\x20
0000000009 00000 n\x20
0000000058 00000 n\x20
0000000115 00000 n\x20
0000000251 00000 n\x20
0000000321 00000 n\x20
trailer<</Size 6/Root 1 0 R>>
startxref
468
%%EOF"""
    with TestClient(app) as client:
        uploaded = client.post("/api/v1/documents", files={"file": ("terms.pdf", pdf, "application/pdf")})
        assert uploaded.status_code == 201, uploaded.text
        # This English fixture confirms actual PDF extraction; it need not trigger Korean rules.
        analyzed = client.post(f"/api/v1/documents/{uploaded.json()['id']}/analyses", json={"experiment_arm": "A"})
    assert analyzed.status_code == 201, analyzed.text
    assert analyzed.json()["result"]["clause_count"] == 1


def test_bank_comparison_fails_closed_without_a_verified_dataset() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/bank-comparisons")
    assert response.status_code == 503
    assert "비교 데이터" in response.json()["detail"]
