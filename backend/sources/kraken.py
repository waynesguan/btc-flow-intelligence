from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sources.base import SourceAdapter, SourceObservation

logger = logging.getLogger(__name__)


class KrakenAdapter(SourceAdapter):
    source_id = "kraken"
    auth_type = "none"
    rate_limit = {"requests_per_minute": 60}
    max_history_depth = "1y"
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
        start_dt = start or (end_dt - timedelta(days=365))

        observations: list[SourceObservation] = []
        cursor = int(start_dt.timestamp())
        end_ts = int(end_dt.timestamp())

        while cursor <= end_ts:
            data = self._request_json(
                method="GET",
                url="https://api.kraken.com/0/public/OHLC",
                params={
                    "pair": "XBTUSD",
                    "interval": 1440,
                    "since": cursor,
                },
            )

            if data.get("error"):
                raise RuntimeError(f"kraken_error: {data['error']}")

            result = data.get("result", {})
            pair_key = next((key for key in result.keys() if key != "last"), None)
            if not pair_key:
                break

            rows = result.get(pair_key, [])
            if not rows:
                break

            max_seen = cursor
            for row in rows:
                ts = self.to_utc(int(float(row[0])))
                max_seen = max(max_seen, int(float(row[0])))
                observations.append(
                    SourceObservation(
                        source_id=self.source_id,
                        dataset=dataset,
                        symbol="BTC-USD",
                        ts=ts,
                        payload={
                            "open": float(row[1]),
                            "high": float(row[2]),
                            "low": float(row[3]),
                            "close": float(row[4]),
                            "vwap": float(row[5]),
                            "volume": float(row[6]),
                            "trade_count": int(row[7]),
                            "unit": "USD",
                        },
                    )
                )

            next_cursor = max_seen + 86400
            if next_cursor <= cursor:
                logger.warning("kraken_cursor_stalled cursor=%s", cursor)
                break
            cursor = next_cursor

        return self.bounded(observations, start=start_dt, end=end_dt)
