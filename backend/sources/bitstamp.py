from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sources.base import SourceAdapter, SourceObservation


class BitstampAdapter(SourceAdapter):
    source_id = "bitstamp"
    auth_type = "none"
    rate_limit = {"requests_per_minute": 60}
    max_history_depth = "3y"
    field_mapping = {
        "close": "close",
        "volume": "volume",
    }
    ts_spec = "OHLC daily timestamp in UTC"
    retry_policy = {"max_retries": 3, "backoff": "exponential"}

    @property
    def datasets(self) -> list[str]:
        return ["btc_usd_spot"]

    def fetch(
        self,
        dataset: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> list[SourceObservation]:
        if dataset != "btc_usd_spot":
            return []

        end_dt = end or datetime.now(timezone.utc)
        start_dt = start or (end_dt - timedelta(days=365 * 3))

        params = {
            "step": 86400,
            "limit": 1000,
            "start": int(start_dt.timestamp()),
            "end": int(end_dt.timestamp()),
        }

        data = self._request_json(
            method="GET",
            url="https://www.bitstamp.net/api/v2/ohlc/btcusd/",
            params=params,
        )
        rows = data.get("data", {}).get("ohlc", [])

        observations: list[SourceObservation] = []
        for row in rows:
            ts = self.to_utc(int(row.get("timestamp", 0)))
            observations.append(
                SourceObservation(
                    source_id=self.source_id,
                    dataset=dataset,
                    symbol="BTC-USD",
                    ts=ts,
                    payload={
                        "open": float(row.get("open", 0.0)),
                        "high": float(row.get("high", 0.0)),
                        "low": float(row.get("low", 0.0)),
                        "close": float(row.get("close", 0.0)),
                        "volume": float(row.get("volume", 0.0)),
                        "unit": "USD",
                    },
                )
            )

        return self.bounded(observations, start=start_dt, end=end_dt)
