from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sources.base import SourceAdapter, SourceObservation

logger = logging.getLogger(__name__)


class CoinbaseAdapter(SourceAdapter):
    source_id = "coinbase"
    auth_type = "none"
    rate_limit = {"requests_per_minute": 60}
    max_history_depth = "1y"
    field_mapping = {
        "time": "ts",
        "close": "close",
        "volume": "volume",
    }
    ts_spec = "Candle timestamp in UTC"
    retry_policy = {"max_retries": 3, "backoff": "exponential"}

    @property
    def datasets(self) -> list[str]:
        return ["btc_usd_daily_candles"]

    def fetch(
        self,
        dataset: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> list[SourceObservation]:
        if dataset != "btc_usd_daily_candles":
            return []

        end_dt = end or datetime.now(timezone.utc)
        start_dt = start or (end_dt - timedelta(days=365))
        observations: list[SourceObservation] = []

        cursor = start_dt
        step_days = 299
        while cursor <= end_dt:
            window_end = min(cursor + timedelta(days=step_days), end_dt)
            params = {
                "granularity": 86400,
                "start": cursor.isoformat().replace("+00:00", "Z"),
                "end": window_end.isoformat().replace("+00:00", "Z"),
            }
            rows = self._fetch_candles(params)

            for entry in rows:
                ts, low, high, open_, close, volume = entry
                observations.append(
                    SourceObservation(
                        source_id=self.source_id,
                        dataset=dataset,
                        symbol="BTC-USD",
                        ts=self.to_utc(ts),
                        payload={
                            "open": float(open_),
                            "high": float(high),
                            "low": float(low),
                            "close": float(close),
                            "volume": float(volume),
                            "unit": "USD",
                        },
                    )
                )

            cursor = window_end + timedelta(days=1)

        return self.bounded(observations, start=start, end=end)

    def _fetch_candles(self, params: dict[str, str]) -> list[list[float]]:
        urls = [
            "https://api.exchange.coinbase.com/products/BTC-USD/candles",
            # fallback in case exchange subdomain changes or is phased out
            "https://api.pro.coinbase.com/products/BTC-USD/candles",
        ]
        last_error: Exception | None = None
        for url in urls:
            try:
                rows = self._request_json(
                    method="GET",
                    url=url,
                    params=params,
                    headers={"User-Agent": "btcObserver/1.0"},
                )
                if isinstance(rows, list):
                    return rows
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning("coinbase_endpoint_failed url=%s error=%s", url, exc)
        if last_error is not None:
            raise last_error
        return []
