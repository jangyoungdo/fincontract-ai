from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Load runtime policy and infrastructure settings from environment variables."""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    frontend_origin: str = "http://localhost:3000"
    database_url: str = "sqlite:///./storage/fincontract.db"
    redis_url: str = "redis://127.0.0.1:6379/0"
    use_redis: bool = False
    worker_max_attempts: int = 3
    chroma_mode: str = "persistent"
    chroma_path: Path = Path("./storage/chroma")
    chroma_host: str = "127.0.0.1"
    chroma_port: int = 8001
    embedding_provider: str = "local_hashing"
    llm_provider: str = "fake"
    allow_external_llm: bool = False
    anthropic_api_key: str = Field(default="", repr=False)
    anthropic_fast_model: str = ""
    anthropic_balanced_model: str = ""
    anthropic_deep_model: str = ""
    anthropic_timeout_seconds: float = 20.0
    anthropic_sdk_max_retries: int = 0
    openai_api_key: str = Field(default="", repr=False)
    openai_fast_model: str = "gpt-5.6-luna"
    openai_balanced_model: str = "gpt-5.6-luna"
    openai_deep_model: str = "gpt-5.6-terra"
    openai_timeout_seconds: float = 30.0
    openai_context_review_enabled: bool = False
    openai_context_max_calls: int = 2
    openai_context_max_chars_per_call: int = 12_000
    openai_context_max_candidates_per_section: int = 3
    openai_summary_enabled: bool = True
    llm_max_calls_per_analysis: int = 8
    semantic_model_enabled: bool = True
    semantic_model_required: bool = False
    semantic_model_path: Path = Path("/opt/models/multilingual-e5-small")
    semantic_model_id: str = "intfloat/multilingual-e5-small"
    semantic_model_revision: str = "8d923955b027282ba975c0a4c825486c9ca4c490"
    # Calibrated on the public synthetic dev set; 0.72 remains the calibration fallback.
    semantic_candidate_threshold: float = 0.90
    semantic_candidate_margin: float = 0.04
    upload_dir: Path = Path("./storage/uploads")
    report_dir: Path = Path("./storage/reports")
    max_upload_bytes: int = 10_485_760
    pdf_max_pages: int = 50
    ocr_enabled: bool = False
    ocr_languages: str = "kor+eng"
    ocr_dpi: int = 200
    ocr_max_pixels_per_page: int = 8_000_000
    ocr_timeout_seconds: int = 15
    ocr_min_characters_per_page: int = 10
    ocr_min_alnum_ratio: float = 0.25
    document_ttl_hours: int = 24
    document_encryption_key: str = Field(default="", repr=False)
    admin_audit_token: str = Field(default="", repr=False)
    audit_retention_days: int = 365
    retention_interval_seconds: int = 300


@lru_cache
def get_settings() -> Settings:
    """Return one cached settings object so all services share the same policy."""
    return Settings()
