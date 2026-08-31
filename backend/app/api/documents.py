from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlalchemy import select

from app.config import get_settings
from app.models import AnalysisRecord, DocumentRecord, get_session_factory
from app.models.schemas import AnalysisRequest, AnalysisResponse, DeleteResponse, DocumentResponse
from app.services.analysis_pipeline import DocumentAnalysisPipeline
from app.services.file_validation import validate_file
from app.services.text_extraction import extract_text


router = APIRouter(prefix="/api/v1", tags=["documents"])


def _document_response(document: DocumentRecord) -> DocumentResponse:
    return DocumentResponse.model_validate(document, from_attributes=True)


@router.post("/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(file: UploadFile = File(...)) -> DocumentResponse:
    settings = get_settings()
    data = await file.read(settings.max_upload_bytes + 1)
    try:
        validated = validate_file(file.filename or "", file.content_type, data, settings.max_upload_bytes)
        text = extract_text(data, validated.extension)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    document_id = str(uuid.uuid4())
    storage_path = settings.upload_dir / f"{document_id}{validated.extension}"
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    storage_path.write_bytes(data)
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
        session.commit()
    return _document_response(document)


@router.get("/documents/{document_id}", response_model=DocumentResponse)
def get_document(document_id: str) -> DocumentResponse:
    with get_session_factory()() as session:
        document = session.get(DocumentRecord, document_id)
        if not document or document.deleted_at:
            raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
        return _document_response(document)


@router.delete("/documents/{document_id}", response_model=DeleteResponse)
def delete_document(document_id: str) -> DeleteResponse:
    with get_session_factory()() as session:
        document = session.get(DocumentRecord, document_id)
        if not document or document.deleted_at:
            raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
        path = Path(document.storage_path)
        if path.exists():
            path.unlink()
        document.status = "deleted"
        document.masked_text = None
        document.deleted_at = datetime.now(timezone.utc)
        session.commit()
    return DeleteResponse(id=document_id, status="deleted")


@router.post("/documents/{document_id}/analyses", response_model=AnalysisResponse, status_code=201)
def create_analysis(document_id: str, request: AnalysisRequest) -> AnalysisResponse:
    analysis_id = str(uuid.uuid4())
    with get_session_factory()() as session:
        document = session.get(DocumentRecord, document_id)
        if not document or document.deleted_at:
            raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
        data = Path(document.storage_path).read_bytes()
        extension = Path(document.storage_path).suffix
        text = extract_text(data, extension)
        record = AnalysisRecord(
            id=analysis_id,
            document_id=document_id,
            status="analyzing",
            disposition="pending",
            experiment_arm=request.experiment_arm,
        )
        session.add(record)
        session.flush()
        try:
            result = DocumentAnalysisPipeline().run(text, request.experiment_arm)
            record.status = "completed"
            record.disposition = result["disposition"]
            record.result_json = json.dumps(result, ensure_ascii=False)
            record.completed_at = datetime.now(timezone.utc)
        except Exception:
            record.status = "failed"
            record.disposition = "needs_review"
            record.error_code = "ANALYSIS_FAILED"
        session.commit()
        return AnalysisResponse(
            id=record.id,
            document_id=record.document_id,
            status=record.status,
            disposition=record.disposition,
            experiment_arm=record.experiment_arm,
            result=json.loads(record.result_json) if record.result_json else None,
            error_code=record.error_code,
        )


@router.get("/analyses/{analysis_id}", response_model=AnalysisResponse)
def get_analysis(analysis_id: str) -> AnalysisResponse:
    with get_session_factory()() as session:
        record = session.get(AnalysisRecord, analysis_id)
        if not record:
            raise HTTPException(status_code=404, detail="분석을 찾을 수 없습니다.")
        return AnalysisResponse(
            id=record.id,
            document_id=record.document_id,
            status=record.status,
            disposition=record.disposition,
            experiment_arm=record.experiment_arm,
            result=json.loads(record.result_json) if record.result_json else None,
            error_code=record.error_code,
        )


@router.get("/analyses/{analysis_id}/report")
def get_report(analysis_id: str) -> dict:
    response = get_analysis(analysis_id)
    return {
        "analysis_id": response.id,
        "disclaimer": "법률 판단이 아닌 검토 보조 자료입니다.",
        "result": response.result,
    }
