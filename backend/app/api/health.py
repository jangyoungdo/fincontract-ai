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
    """Report that the API process is alive without probing dependencies."""
    return {"status": "alive"}


@router.get("/ready")
def ready(response: Response) -> dict:
    """Probe database, retrieval storage, and the optional queue for readiness."""
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


@router.get("/worker")
def worker_status(response: Response) -> dict:
    """Expose queue depth only; messages contain opaque analysis IDs."""
    settings = get_settings()
    if not settings.use_redis:
        return {"status": "disabled", "queue_depth": 0, "dead_letter_depth": 0}
    try:
        redis_client = Redis.from_url(settings.redis_url, socket_timeout=1)
        return {
            "status": "ready",
            "queue_depth": redis_client.llen("fincontract:analysis:queue"),
            "dead_letter_depth": redis_client.llen("fincontract:analysis:dead-letter"),
        }
    except Exception:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable", "queue_depth": 0, "dead_letter_depth": 0}
