from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    """Public document metadata returned without storage paths or extracted text."""
    id: str
    original_filename: str
    mime_type: str
    sha256: str
    status: str
    bank_name: str | None = None
    product_type: str | None = None
    uploaded_at: datetime
    expires_at: datetime
    deleted_at: datetime | None = None


class AnalysisRequest(BaseModel):
    """Select the reproducible experiment arm for a new analysis."""
    experiment_arm: Literal["A", "D"] = "D"


class AnalysisResponse(BaseModel):
    """Stable API envelope for synchronous and queued analysis states."""
    id: str
    document_id: str
    status: str
    disposition: str
    experiment_arm: str
    result: dict[str, Any] | None = None
    error_code: str | None = None
    retryable: bool | None = None
    progress: dict[str, Any] | None = None


class DeleteResponse(BaseModel):
    """Confirm that a document was tombstoned and its encrypted file removed."""
    id: str
    status: Literal["deleted"]


class BankComparisonItem(BaseModel):
    """One rule-level pro/con/neutral verdict against the peer bank corpus."""
    rule_id: str
    rule_name: str
    our_signal: bool
    peer_match_rate: float
    peer_bank_count: int
    explanation: str


class BankComparisonResponse(BaseModel):
    """Rule-based qualitative comparison against a verified peer bank corpus."""
    comparison_status: Literal["ready", "insufficient_peer_data"]
    product_type: str
    bank_name: str | None = None
    peer_bank_count: int
    corpus_version: str
    generated_note: str
    pros: list[BankComparisonItem] = []
    cons: list[BankComparisonItem] = []
    neutral: list[BankComparisonItem] = []


class AuditEventResponse(BaseModel):
    """PII-free administrative audit representation."""
    id: str
    event_type: str
    document_id: str | None
    analysis_id: str | None
    created_at: datetime
