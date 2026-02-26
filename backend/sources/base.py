from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

import httpx

from config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class SourceObservation:
    source_id: str
    dataset: str
    symbol: Optional[str]
    ts: datetime
    payload: dict[str, Any]


class SourceAdapter(ABC):
    source_id: str
    auth_type: str
    rate_limit: dict[str, int]
    max_history_depth: str
    field_mapping: dict[str, str]
    ts_spec: str
    retry_policy: dict[str, Any]

    @property
    @abstractmethod
    def datasets(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def fetch(
        self,
        dataset: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> list[SourceObservation]:
        raise NotImplementedError

    def backfill(self) -> list[SourceObservation]:
        return [
            item
            for dataset in self.datasets
            for item in self.fetch(dataset=dataset, start=None, end=None)
        ]

    def _request_json(
        self,
        method: str,
        url: str,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> Any:
        attempts = int(self.retry_policy.get("max_retries", 3)) + 1
        backoff = 1.0
        timeout = settings.request_timeout_seconds
        for attempt in range(1, attempts + 1):
            try:
                with httpx.Client(timeout=timeout) as client:
                    response = client.request(method=method, url=url, params=params, headers=headers)
                    response.raise_for_status()
                    return response.json()
            except Exception as exc:  # noqa: BLE001
                if attempt >= attempts:
                    raise
                logger.warning(
                    "source_request_retry source=%s url=%s attempt=%s error=%s",
                    self.source_id,
                    url,
                    attempt,
                    exc,
                )
                time.sleep(backoff)
                backoff *= 2
        return None

    def _request_text(
        self,
        method: str,
        url: str,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> str:
        attempts = int(self.retry_policy.get("max_retries", 3)) + 1
        backoff = 1.0
        timeout = settings.request_timeout_seconds
        for attempt in range(1, attempts + 1):
            try:
                with httpx.Client(timeout=timeout) as client:
                    response = client.request(method=method, url=url, params=params, headers=headers)
                    response.raise_for_status()
                    return response.text
            except Exception as exc:  # noqa: BLE001
                if attempt >= attempts:
                    raise
                logger.warning(
                    "source_request_retry source=%s url=%s attempt=%s error=%s",
                    self.source_id,
                    url,
                    attempt,
                    exc,
                )
                time.sleep(backoff)
                backoff *= 2
        return ""

    @staticmethod
    def utc_now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def parse_iso_date(date_str: str) -> datetime:
        # FRED 等日频序列常给 YYYY-MM-DD，这里统一补成 UTC 0 点
        return datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)

    @staticmethod
    def to_utc(ts: int | float | str | datetime) -> datetime:
        if isinstance(ts, datetime):
            return ts.astimezone(timezone.utc)
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)

    @staticmethod
    def bounded(
        items: Iterable[SourceObservation],
        start: Optional[datetime],
        end: Optional[datetime],
    ) -> list[SourceObservation]:
        result: list[SourceObservation] = []
        for item in items:
            if start and item.ts < start:
                continue
            if end and item.ts > end:
                continue
            result.append(item)
        return result
