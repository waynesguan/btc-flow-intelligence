from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from config.settings import get_settings
from sources.base import SourceAdapter, SourceObservation

settings = get_settings()


class CoinGeckoAdapter(SourceAdapter):
    source_id = "coingecko"
    auth_type = "none" if not settings.coingecko_api_key else "api_key"
    rate_limit = {"requests_per_minute": 40}
    max_history_depth = "365d"
    field_mapping = {
        "prices": "price",
        "total_volumes": "volume",
        "market_caps": "market_cap",
    }
    ts_spec = "Millisecond timestamps in UTC"
    retry_policy = {"max_retries": 3, "backoff": "exponential"}

    @property
    def datasets(self) -> list[str]:
        return [
            "btc_market_chart",
            "stablecoin_market_caps",
            "derivatives_overview",
        ]

    def fetch(
        self,
        dataset: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> list[SourceObservation]:
        headers: dict[str, str] = {"accept": "application/json"}
        if settings.coingecko_api_key:
            headers["x-cg-demo-api-key"] = settings.coingecko_api_key

        if dataset == "btc_market_chart":
            return self._fetch_btc_market_chart(start=start, end=end, headers=headers)
        if dataset == "stablecoin_market_caps":
            return self._fetch_stablecoin_caps(start=start, end=end, headers=headers)
        if dataset == "derivatives_overview":
            return self._fetch_derivatives(start=start, end=end, headers=headers)
        return []

    def _fetch_btc_market_chart(
        self,
        start: Optional[datetime],
        end: Optional[datetime],
        headers: dict[str, str],
    ) -> list[SourceObservation]:
        days = "365"
        if start and (datetime.now(timezone.utc) - start).days > 365:
            days = "max"

        data = self._request_json(
            method="GET",
            url="https://api.coingecko.com/api/v3/coins/bitcoin/market_chart",
            params={"vs_currency": "usd", "days": days, "interval": "daily"},
            headers=headers,
        )

        prices = {int(ts): float(v) for ts, v in data.get("prices", [])}
        volumes = {int(ts): float(v) for ts, v in data.get("total_volumes", [])}
        market_caps = {int(ts): float(v) for ts, v in data.get("market_caps", [])}

        observations: list[SourceObservation] = []
        for ts in sorted(prices.keys()):
            observations.append(
                SourceObservation(
                    source_id=self.source_id,
                    dataset="btc_market_chart",
                    symbol="BTC",
                    ts=self.to_utc(ts / 1000),
                    payload={
                        "price_usd": prices.get(ts),
                        "volume_usd": volumes.get(ts),
                        "market_cap_usd": market_caps.get(ts),
                        "unit": "USD",
                    },
                )
            )

        return self.bounded(observations, start=start, end=end)

    def _fetch_stablecoin_caps(
        self,
        start: Optional[datetime],
        end: Optional[datetime],
        headers: dict[str, str],
    ) -> list[SourceObservation]:
        observations: list[SourceObservation] = []
        for coin_id, symbol in (("tether", "USDT"), ("usd-coin", "USDC")):
            data = self._request_json(
                method="GET",
                url=f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart",
                params={"vs_currency": "usd", "days": "365", "interval": "daily"},
                headers=headers,
            )
            for ts, market_cap in data.get("market_caps", []):
                observations.append(
                    SourceObservation(
                        source_id=self.source_id,
                        dataset="stablecoin_market_caps",
                        symbol=symbol,
                        ts=self.to_utc(ts / 1000),
                        payload={
                            "market_cap_usd": float(market_cap),
                            "unit": "USD",
                        },
                    )
                )
        return self.bounded(observations, start=start, end=end)

    def _fetch_derivatives(
        self,
        start: Optional[datetime],
        end: Optional[datetime],
        headers: dict[str, str],
    ) -> list[SourceObservation]:
        rows = self._request_json(
            method="GET",
            url="https://api.coingecko.com/api/v3/derivatives/exchanges",
            headers=headers,
        )
        ts = datetime.now(timezone.utc)
        total_open_interest = 0.0

        for row in rows:
            oi = row.get("open_interest_btc")
            if oi is not None:
                total_open_interest += float(oi)

        # CoinGecko 免费 derivatives/exchanges 不提供统一 funding rate 字段。
        # Phase 1 以 0 占位，并通过 quality_flags 明确不可用，避免伪造数值。
        avg_funding_proxy = 0.0
        obs = SourceObservation(
            source_id=self.source_id,
            dataset="derivatives_overview",
            symbol="BTC",
            ts=ts,
            payload={
                "open_interest_btc": total_open_interest,
                "funding_rate_proxy": avg_funding_proxy,
                "unit": "BTC",
                "quality_flags": {
                    "funding_rate": "unavailable",
                    "unavailable": True,
                },
            },
        )

        return self.bounded([obs], start=start, end=end)
