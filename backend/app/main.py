from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.documents import router as documents_router
from app.config import get_settings
from app.models import get_engine, upgrade_database


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.report_dir.mkdir(parents=True, exist_ok=True)
    upgrade_database(get_engine())
    yield


settings = get_settings()
app = FastAPI(title="FinContract AI", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Idempotency-Key"],
)
app.include_router(health_router)
app.include_router(documents_router)
