from __future__ import annotations

from datetime import datetime, timezone

import redis
from fastapi import APIRouter, Response, status
from sqlalchemy import text

from config.settings import get_settings
from db.session import SessionLocal

router = APIRouter(tags=["health"])
settings = get_settings()


def _check_db() -> tuple[bool, str | None]:
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return True, None
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    finally:
        db.close()


def _check_redis() -> tuple[bool, str | None]:
    if not settings.redis_enabled:
        return True, None
    try:
        client = redis.Redis.from_url(settings.redis_url)
        client.ping()
        return True, None
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


@router.get("/health")
def health(response: Response) -> dict:
    db_ok, db_error = _check_db()
    redis_ok, redis_error = _check_redis()

    ok = db_ok and redis_ok
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "data": {
            "status": "ok" if ok else "degraded",
            "checks": {
                "database": {"ok": db_ok, "error": db_error},
                "redis": {"ok": redis_ok, "error": redis_error},
            },
        },
        "meta": {
            "source": "system",
            "delay": "0",
            "unit": None,
            "version": 1,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
