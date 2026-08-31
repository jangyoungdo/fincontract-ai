from __future__ import annotations

from fastapi import APIRouter, Response, status
from redis import Redis
from sqlalchemy import text

from app.config import get_settings
from app.models import get_engine
from app.vectorstore.client import ensure_collections


router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/ready")
def ready(response: Response) -> dict:
    settings = get_settings()
    checks: dict[str, dict[str, str]] = {}

    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["database"] = {"status": "ready"}
    except Exception:
        checks["database"] = {"status": "unavailable"}

    try:
        collections = ensure_collections()
        checks["chroma"] = {"status": "ready", "collections": str(len(collections))}
    except Exception:
        checks["chroma"] = {"status": "unavailable"}

    if settings.use_redis:
        try:
            Redis.from_url(settings.redis_url, socket_timeout=1).ping()
            checks["redis"] = {"status": "ready"}
        except Exception:
            checks["redis"] = {"status": "unavailable"}
    else:
        checks["redis"] = {"status": "disabled"}

    is_ready = all(item["status"] in {"ready", "disabled"} for item in checks.values())
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if is_ready else "degraded", "checks": checks}
