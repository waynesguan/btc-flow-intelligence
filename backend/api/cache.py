from __future__ import annotations

import json
import logging
from typing import Any, Optional

import redis

from config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_redis_client: Optional[redis.Redis] = None


def _get_client() -> Optional[redis.Redis]:
    global _redis_client
    if not settings.redis_enabled:
        return None
    if _redis_client is not None:
        return _redis_client
    try:
        _redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        _redis_client.ping()
    except Exception as exc:  # noqa: BLE001
        logger.warning("redis_unavailable error=%s", exc)
        _redis_client = None
    return _redis_client


def cache_get_json(key: str) -> Optional[Any]:
    client = _get_client()
    if client is None:
        return None
    try:
        raw = client.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        logger.warning("redis_get_failed key=%s error=%s", key, exc)
        return None


def cache_set_json(key: str, value: Any, ttl_seconds: int = 60) -> None:
    client = _get_client()
    if client is None:
        return
    try:
        client.set(name=key, value=json.dumps(value, ensure_ascii=False, default=str), ex=ttl_seconds)
    except Exception as exc:  # noqa: BLE001
        logger.warning("redis_set_failed key=%s error=%s", key, exc)
