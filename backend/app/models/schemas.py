from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class DocumentResponse(BaseModel):
    id: str
    original_filename: str
    mime_type: str
    sha256: str
    status: str
    uploaded_at: datetime
    expires_at: datetime
    deleted_at: datetime | None = None


class AnalysisRequest(BaseModel):
    experiment_arm: Literal["A", "D"] = "D"


class AnalysisResponse(BaseModel):
    id: str
    document_id: str
    status: str
    disposition: str
    experiment_arm: str
    result: dict[str, Any] | None = None
    error_code: str | None = None
    progress: dict[str, Any] | None = None


class DeleteResponse(BaseModel):
    id: str
    status: Literal["deleted"]
