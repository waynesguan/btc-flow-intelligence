from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sources.base import SourceAdapter, SourceObservation


class DeribitAdapter(SourceAdapter):
    source_id = "deribit"
    auth_type = "none"
    rate_limit = {"requests_per_minute": 60}
    max_history_depth = "1y"
    field_mapping = {
        "open_interest": "open_interest_btc",
        "funding_8h": "funding_rate",
        "mark_price": "futures_price",
        "underlying_price": "spot_index_price",
    }
    ts_spec = "Snapshot timestamp in UTC"
    retry_policy = {"max_retries": 3, "backoff": "exponential"}

    @property
    def datasets(self) -> list[str]:
        return ["derivatives"]

    def fetch(
        self,
        dataset: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> list[SourceObservation]:
        if dataset != "derivatives":
            return []

        summary = self._request_json(
            method="GET",
            url="https://www.deribit.com/api/v2/public/get_book_summary_by_currency",
            params={"currency": "BTC", "kind": "future"},
        )
        books = summary.get("result", [])

        total_open_interest = 0.0
        weighted_funding = 0.0
        funding_weight = 0.0
        basis_values: list[float] = []

        for book in books:
            oi = float(book.get("open_interest", 0.0) or 0.0)
            total_open_interest += oi

            funding = book.get("funding_8h")
            if funding is not None:
                fv = float(funding)
                weighted_funding += fv * max(oi, 1.0)
                funding_weight += max(oi, 1.0)

            mark_price = book.get("mark_price")
            index_price = book.get("underlying_price") or book.get("estimated_delivery_price")
            if mark_price is not None and index_price not in (None, 0):
                basis_values.append(float(mark_price) - float(index_price))

        funding_rate = weighted_funding / funding_weight if funding_weight else 0.0
        basis_spread = sum(basis_values) / len(basis_values) if basis_values else 0.0

        trades = self._request_json(
            method="GET",
            url="https://www.deribit.com/api/v2/public/get_last_trades_by_currency",
            params={"currency": "BTC", "kind": "future", "count": 1000},
        )
        trades_rows = trades.get("result", {}).get("trades", [])
        liquidation_volume = 0.0
        for trade in trades_rows:
            if trade.get("liquidation"):
                amount = float(trade.get("amount", 0.0) or 0.0)
                price = float(trade.get("price", 0.0) or 0.0)
                liquidation_volume += abs(amount * price)

        ts_us = summary.get("usOut") or int(datetime.now(timezone.utc).timestamp() * 1_000_000)
        ts = self.to_utc(int(ts_us) / 1_000_000)

        observation = SourceObservation(
            source_id=self.source_id,
            dataset=dataset,
            symbol="BTC",
            ts=ts,
            payload={
                "open_interest_btc": total_open_interest,
                "funding_rate": funding_rate,
                "basis_spread": basis_spread,
                "liquidation_volume_usd": liquidation_volume,
                "instrument_count": len(books),
                "unit": "BTC",
            },
        )

        return self.bounded([observation], start=start, end=end)
