from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin import router as admin_router
from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.config import get_settings
from app.models import get_engine, upgrade_database


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Prepare writable storage and idempotently upgrade the database on startup."""
    settings = get_settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.report_dir.mkdir(parents=True, exist_ok=True)
    upgrade_database(get_engine())
    yield


settings = get_settings()
app = FastAPI(title="FinContract AI", version="0.1.0", lifespan=lifespan)
# Only the configured frontend may call the browser-facing API; admin access
# additionally requires X-Admin-Token at the endpoint boundary.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Idempotency-Key", "X-Admin-Token"],
)
app.include_router(admin_router)
app.include_router(health_router)
app.include_router(documents_router)
