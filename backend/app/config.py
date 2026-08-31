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
    upload_dir: Path = Path("./storage/uploads")
    report_dir: Path = Path("./storage/reports")
    max_upload_bytes: int = 10_485_760
    document_ttl_hours: int = 24
    document_encryption_key: str = Field(default="", repr=False)
    admin_audit_token: str = Field(default="", repr=False)
    audit_retention_days: int = 365
    retention_interval_seconds: int = 300


@lru_cache
def get_settings() -> Settings:
    """Return one cached settings object so all services share the same policy."""
    return Settings()
