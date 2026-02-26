from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from config.settings import get_settings
from sources.base import SourceAdapter, SourceObservation

settings = get_settings()


class CoinMetricsAdapter(SourceAdapter):
    source_id = "coin_metrics"
    auth_type = "api_key"
    rate_limit = {"requests_per_minute": 30}
    max_history_depth = "all"
    field_mapping = {
        "time": "ts",
        "CapRealUSD": "realized_cap",
        "CapMVRVCur": "mvrv",
        "PriceUSD": "price_usd",
    }
    ts_spec = "Provider ISO timestamp normalized to UTC"
    retry_policy = {"max_retries": 3, "backoff": "exponential"}

    @property
    def datasets(self) -> list[str]:
        return ["onchain_core"]

    def fetch(
        self,
        dataset: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> list[SourceObservation]:
        if dataset != "onchain_core":
            return []
        if not settings.coin_metrics_api_key:
            raise RuntimeError("COIN_METRICS_API_KEY is required for coin_metrics ingestion")

        end_dt = end or datetime.now(timezone.utc)
        start_dt = start or (end_dt - timedelta(days=365 * 5))

        rows = self._request_json(
            method="GET",
            url="https://api.coinmetrics.io/v4/timeseries/asset-metrics",
            params={
                "assets": "btc",
                "metrics": "CapRealUSD,CapMVRVCur,PriceUSD,CapMrktCurUSD",
                "start_time": start_dt.isoformat().replace("+00:00", "Z"),
                "end_time": end_dt.isoformat().replace("+00:00", "Z"),
                "frequency": "1d",
                "page_size": 10000,
                "api_key": settings.coin_metrics_api_key,
            },
        )

        observations: list[SourceObservation] = []
        for row in rows.get("data", []):
            ts = self.to_utc(row.get("time"))
            realized_cap = self._to_float(row.get("CapRealUSD"))
            mvrv = self._to_float(row.get("CapMVRVCur"))
            market_cap = self._to_float(row.get("CapMrktCurUSD"))
            price = self._to_float(row.get("PriceUSD"))

            payload = {
                "realized_cap": realized_cap,
                "mvrv": mvrv,
                "market_cap": market_cap,
                "price_usd": price,
                "provider": "coin_metrics",
            }
            if realized_cap is not None and market_cap is not None:
                payload["realized_profit_loss"] = market_cap - realized_cap

            observations.append(
                SourceObservation(
                    source_id=self.source_id,
                    dataset=dataset,
                    symbol="BTC",
                    ts=ts,
                    payload=payload,
                )
            )

        return self.bounded(observations, start=start_dt, end=end_dt)

    @staticmethod
    def _to_float(value: object) -> Optional[float]:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except Exception:  # noqa: BLE001
            return None
