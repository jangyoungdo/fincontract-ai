from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse

from app.config import get_settings
from app.models import AnalysisRecord, DocumentRecord, get_session_factory
from app.models.schemas import AnalysisRequest, AnalysisResponse, DeleteResponse, DocumentResponse
from app.services.analysis_jobs import enqueue_analysis, get_progress, get_redis
from app.services.analysis_pipeline import DocumentAnalysisPipeline
from app.services.audit import add_audit_event
from app.services.encrypted_storage import read_encrypted, write_encrypted
from app.services.file_validation import validate_file
from app.services.pdf_report import build_pdf_report
from app.services.source_previews import (
    delete_preview_tree,
    generate_pdf_source_previews,
    preview_path,
)
from app.services.text_extraction import extract_document, extract_text

router = APIRouter(prefix="/api/v1", tags=["documents"])

RETRYABLE_ANALYSIS_ERRORS = {
    "ANALYSIS_FAILED",
    "ANALYSIS_RETRYING",
    "ANALYSIS_QUEUE_UNAVAILABLE",
    "LLM_RATE_LIMITED",
    "LLM_UNAVAILABLE",
    "OCR_TIMEOUT",
    "API_UNREACHABLE",
}


def _is_retryable_error(error_code: str | None) -> bool | None:
    """Expose a stable retry hint without returning exception text."""
    return error_code in RETRYABLE_ANALYSIS_ERRORS if error_code else None


def _document_response(document: DocumentRecord) -> DocumentResponse:
    return DocumentResponse.model_validate(document, from_attributes=True)


@router.post("/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(file: UploadFile = File(...)) -> DocumentResponse:
    """Validate and encrypt an uploaded document before persisting its metadata."""
    settings = get_settings()
    data = await file.read(settings.max_upload_bytes + 1)
    try:
        validated = validate_file(file.filename or "", file.content_type, data, settings.max_upload_bytes)
        extract_text(data, validated.extension)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    document_id = str(uuid.uuid4())
    storage_path = settings.upload_dir / f"{document_id}{validated.extension}.enc"
    write_encrypted(storage_path, data)
    now = datetime.now(timezone.utc)
    document = DocumentRecord(
        id=document_id,
        original_filename=Path(file.filename or "document").name,
        mime_type=validated.mime_type,
        sha256=hashlib.sha256(data).hexdigest(),
        status="ready",
        storage_path=str(storage_path),
        masked_text=None,
        uploaded_at=now,
        expires_at=now + timedelta(hours=settings.document_ttl_hours),
    )
    with get_session_factory()() as session:
        session.add(document)
        add_audit_event(session, "document_uploaded", document_id=document_id)
        session.commit()
    return _document_response(document)


@router.get("/documents/{document_id}", response_model=DocumentResponse)
def get_document(document_id: str) -> DocumentResponse:
    """Return non-content document metadata unless the record was deleted."""
    with get_session_factory()() as session:
        document = session.get(DocumentRecord, document_id)
        if not document or document.deleted_at:
            raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
        return _document_response(document)


@router.delete("/documents/{document_id}", response_model=DeleteResponse)
def delete_document(document_id: str) -> DeleteResponse:
    """Delete encrypted bytes and tombstone metadata for an explicit user request."""
    with get_session_factory()() as session:
        document = session.get(DocumentRecord, document_id)
        if not document or document.deleted_at:
            raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
        path = Path(document.storage_path)
        if path.exists():
            path.unlink()
        analysis_ids = [
            item.id
            for item in session.query(AnalysisRecord).filter(
                AnalysisRecord.document_id == document_id
            )
        ]
        for analysis_id in analysis_ids:
            delete_preview_tree(get_settings().report_dir, analysis_id)
        document.status = "deleted"
        document.masked_text = None
        document.deleted_at = datetime.now(timezone.utc)
        add_audit_event(session, "document_deleted", document_id=document_id)
        session.commit()
    return DeleteResponse(id=document_id, status="deleted")


@router.post("/documents/{document_id}/analyses", response_model=AnalysisResponse, status_code=201)
def create_analysis(document_id: str, request: AnalysisRequest, response: Response) -> AnalysisResponse:
    """Create an analysis and run it synchronously or enqueue only its opaque ID."""
    analysis_id = str(uuid.uuid4())
    settings = get_settings()
    with get_session_factory()() as session:
        document = session.get(DocumentRecord, document_id)
        if not document or document.deleted_at:
            raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
        data = read_encrypted(Path(document.storage_path))
        extension = Path(document.original_filename).suffix.lower()
        extracted = extract_document(data, extension)
        record = AnalysisRecord(
            id=analysis_id,
            document_id=document_id,
            status="queued" if settings.use_redis else "analyzing",
            disposition="pending",
            experiment_arm="full",
        )
        session.add(record)
        add_audit_event(
            session, "analysis_created", document_id=document_id, analysis_id=analysis_id
        )
        session.flush()
        if settings.use_redis:
            # Make the analysis visible before publishing its ID. Publishing
            # first lets an idle worker consume an uncommitted record and race
            # the request transaction.
            session.commit()
            try:
                enqueue_analysis(get_redis(), analysis_id)
            except Exception as exc:
                record = session.get(AnalysisRecord, analysis_id)
                if record:
                    record.status = "failed"
                    record.disposition = "needs_review"
                    record.error_code = "ANALYSIS_QUEUE_UNAVAILABLE"
                    add_audit_event(
                        session,
                        "analysis_failed",
                        document_id=document_id,
                        analysis_id=analysis_id,
                    )
                    session.commit()
                raise HTTPException(status_code=503, detail="분석 큐를 사용할 수 없습니다.") from exc
            response.status_code = status.HTTP_202_ACCEPTED
            return AnalysisResponse(
                id=record.id,
                document_id=record.document_id,
                status=record.status,
                disposition=record.disposition,
                experiment_arm=record.experiment_arm,
                progress={"state": "queued", "percent": 0},
            )
        try:
            result = DocumentAnalysisPipeline().run(
                extracted.text,
                request.experiment_arm,
                pages=extracted.pages,
                source_extension=extension,
            )
            if extension == ".pdf":
                result = generate_pdf_source_previews(
                    data, analysis_id, result, settings.report_dir, settings, extracted.pages
                )
            record.status = "completed"
            record.disposition = result["disposition"]
            record.result_json = json.dumps(result, ensure_ascii=False)
            record.completed_at = datetime.now(timezone.utc)
            add_audit_event(
                session, "analysis_completed", document_id=document_id, analysis_id=analysis_id
            )
        except Exception as exc:
            record.status = "failed"
            record.disposition = "needs_review"
            record.error_code = getattr(exc, "code", "ANALYSIS_FAILED")
            add_audit_event(
                session, "analysis_failed", document_id=document_id, analysis_id=analysis_id
            )
        session.commit()
        return AnalysisResponse(
            id=record.id,
            document_id=record.document_id,
            status=record.status,
            disposition=record.disposition,
            experiment_arm=record.experiment_arm,
            result=json.loads(record.result_json) if record.result_json else None,
            error_code=record.error_code,
            retryable=_is_retryable_error(record.error_code),
        )


@router.get("/analyses/{analysis_id}", response_model=AnalysisResponse)
def get_analysis(analysis_id: str) -> AnalysisResponse:
    """Return persisted results plus short-lived Redis progress when enabled."""
    with get_session_factory()() as session:
        record = session.get(AnalysisRecord, analysis_id)
        if not record:
            raise HTTPException(status_code=404, detail="분석을 찾을 수 없습니다.")
        progress = None
        if get_settings().use_redis:
            try:
                progress = get_progress(get_redis(), analysis_id)
            except Exception:
                progress = {"state": "unavailable", "percent": 0}
        return AnalysisResponse(
            id=record.id,
            document_id=record.document_id,
            status=record.status,
            disposition=record.disposition,
            experiment_arm=record.experiment_arm,
            result=_public_result(json.loads(record.result_json)) if record.result_json else None,
            error_code=record.error_code,
            retryable=_is_retryable_error(record.error_code),
            progress=progress,
        )


def _public_result(result: dict) -> dict:
    """Strip legacy full-document text before any persisted result leaves the API."""
    document = result.get("document")
    if isinstance(document, dict):
        document.pop("masked_text", None)
    return result


@router.get("/analyses/{analysis_id}/source-previews/{preview_id}.png")
def get_source_preview(analysis_id: str, preview_id: str) -> FileResponse:
    """Serve only a generated masked PNG belonging to a live analysis document."""
    with get_session_factory()() as session:
        record = session.get(AnalysisRecord, analysis_id)
        if not record:
            raise HTTPException(status_code=404, detail="분석을 찾을 수 없습니다.")
        document = session.get(DocumentRecord, record.document_id)
        if not document or document.deleted_at:
            raise HTTPException(status_code=404, detail="원문 조각을 찾을 수 없습니다.")
        result = json.loads(record.result_json) if record.result_json else {}
        allowed = {
            value
            for item in [*result.get("findings", []), *result.get("candidate_findings", [])]
            for value in item.get("source", {}).get("preview_ids", [])
        }
        if preview_id not in allowed:
            raise HTTPException(status_code=404, detail="원문 조각을 찾을 수 없습니다.")
        try:
            path = preview_path(get_settings().report_dir, analysis_id, preview_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="원문 조각을 찾을 수 없습니다.") from exc
        if not path.is_file():
            raise HTTPException(status_code=404, detail="원문 조각을 찾을 수 없습니다.")
        return FileResponse(
            path,
            media_type="image/png",
            headers={"Cache-Control": "no-store"},
        )


@router.get("/analyses/{analysis_id}/report")
def get_report(analysis_id: str) -> dict:
    """Expose the machine-readable review result with its legal-use disclaimer."""
    response = get_analysis(analysis_id)
    return {
        "analysis_id": response.id,
        "disclaimer": "법률 판단이 아닌 검토 보조 자료입니다.",
        "result": response.result,
    }


@router.get("/analyses/{analysis_id}/report.pdf")
def get_pdf_report(analysis_id: str) -> StreamingResponse:
    """Render a completed analysis as an audited, downloadable PDF report."""
    response = get_analysis(analysis_id)
    if response.status != "completed":
        raise HTTPException(status_code=409, detail="완료된 분석만 PDF 리포트를 생성할 수 있습니다.")
    payload = build_pdf_report(response.id, response.result)
    with get_session_factory()() as session:
        add_audit_event(
            session,
            "report_generated",
            document_id=response.document_id,
            analysis_id=response.id,
        )
        session.commit()
    return StreamingResponse(
        BytesIO(payload),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="fincontract-{analysis_id}.pdf"'},
    )


@router.get("/bank-comparisons")
def get_bank_comparisons() -> dict:
    """Fail closed until a licensed, versioned comparison dataset is available."""
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="검증된 공개·허가 은행 비교 데이터가 아직 없어 비교 결과를 제공하지 않습니다.",
    )
