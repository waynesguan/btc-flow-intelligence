from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from config.settings import get_settings
from sources.base import SourceAdapter, SourceObservation

settings = get_settings()
logger = logging.getLogger(__name__)


class GlassnodeAdapter(SourceAdapter):
    source_id = "glassnode"
    auth_type = "api_key"
    rate_limit = {"requests_per_minute": 30}
    max_history_depth = "all"
    field_mapping = {
        "t": "ts",
        "v": "value",
    }
    ts_spec = "Provider timestamp (seconds) normalized to UTC"
    retry_policy = {"max_retries": 3, "backoff": "exponential"}

    metric_paths = {
        "realized_cap": "market/marketcap_realized",
        "mvrv": "market/mvrv",
        "cost_basis": "market/price_realized_usd",
        "exchange_netflow": "transactions/transfers_volume_exchanges_net",
        "whale_balance": "distribution/balance_1k_plus",
        "lth_supply": "supply/lth_sum",
        "sth_supply": "supply/sth_sum",
        "realized_profit_loss": "indicators/sopr_adjusted",
        "exchange_stablecoin_balance": "supply/stablecoin_exchange_balance",
    }

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
        if not settings.glassnode_api_key:
            raise RuntimeError("GLASSNODE_API_KEY is required for glassnode ingestion")

        end_dt = end or datetime.now(timezone.utc)
        start_dt = start or (end_dt - timedelta(days=365 * 5))

        merged: dict[int, dict[str, Any]] = defaultdict(dict)

        for field, path in self.metric_paths.items():
            try:
                points = self._fetch_metric_points(path=path, start=start_dt, end=end_dt)
            except Exception as exc:  # noqa: BLE001
                logger.warning("glassnode_metric_failed metric=%s path=%s error=%s", field, path, exc)
                continue

            for point in points:
                ts = int(point["ts"])
                merged[ts][field] = point["value"]

        observations: list[SourceObservation] = []
        for ts, payload in sorted(merged.items()):
            observations.append(
                SourceObservation(
                    source_id=self.source_id,
                    dataset=dataset,
                    symbol="BTC",
                    ts=self.to_utc(ts),
                    payload={
                        **payload,
                        "provider": "glassnode",
                    },
                )
            )

        return self.bounded(observations, start=start_dt, end=end_dt)

    def _fetch_metric_points(self, path: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
        params = {
            "a": "BTC",
            "i": "24h",
            "s": int(start.timestamp()),
            "u": int(end.timestamp()),
            "api_key": settings.glassnode_api_key,
        }
        rows = self._request_json(
            method="GET",
            url=f"https://api.glassnode.com/v1/metrics/{path}",
            params=params,
        )

        points: list[dict[str, Any]] = []
        for row in rows:
            raw_ts = row.get("t")
            raw_value = row.get("v")
            value = self._as_float(raw_value)
            if raw_ts is None or value is None:
                continue
            points.append({"ts": int(raw_ts), "value": value})
        return points

    @staticmethod
    def _as_float(raw_value: Any) -> Optional[float]:
        if raw_value is None:
            return None
        if isinstance(raw_value, dict):
            for val in raw_value.values():
                if isinstance(val, (int, float)):
                    return float(val)
            return None
        if isinstance(raw_value, (int, float)):
            return float(raw_value)
        try:
            return float(raw_value)
        except Exception:  # noqa: BLE001
            return None
