from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup

from sources.base import SourceAdapter, SourceObservation

logger = logging.getLogger(__name__)


class FarsideAdapter(SourceAdapter):
    source_id = "farside"
    auth_type = "none"
    rate_limit = {"requests_per_minute": 30}
    max_history_depth = "all"
    field_mapping = {
        "Date": "ts",
        "Total": "total_netflow",
    }
    ts_spec = "Daily ETF flow date normalized to UTC midnight"
    retry_policy = {"max_retries": 3, "backoff": "exponential"}

    @property
    def datasets(self) -> list[str]:
        return ["us_spot_btc_etf_flows"]

    def fetch(
        self,
        dataset: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> list[SourceObservation]:
        if dataset != "us_spot_btc_etf_flows":
            return []

        html = self._request_text(
            method="GET",
            url="https://farside.co.uk/bitcoin-etf-flow-all-data/",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"},
        )
        soup = BeautifulSoup(html, "html.parser")

        # Find the ETF flow table: look for a table containing 'IBIT' or 'FBTC' in any cell
        table = None
        for candidate in soup.find_all("table"):
            text = candidate.get_text()
            if "IBIT" in text or "FBTC" in text:
                table = candidate
                break
        if table is None:
            logger.warning("farside_table_not_found")
            return []

        # Extract headers from the row containing fund tickers (e.g. IBIT, FBTC)
        # The first column (empty) is Date, the last column is Total
        headers: list[str] = []
        rows = table.find_all("tr")
        for row in rows:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if any(c in ("IBIT", "FBTC", "BITB", "ARKB") for c in cells):
                headers = ["Date" if c == "" else ("Total" if i == len(cells) - 1 and c == "" else c)
                           for i, c in enumerate(cells)]
                break

        if not headers:
            logger.warning("farside_header_row_not_found")
            return []

        observations: list[SourceObservation] = []
        seen_ts: set[datetime] = set()

        for row in rows:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if not cells:
                continue
            # Use first cell as date regardless of row length
            date_raw = cells[0]
            if not date_raw:
                continue
            # Skip rows where first cell is not a parseable date
            ts = self._try_parse_date(date_raw)
            if ts is None:
                continue
            # Skip duplicate dates (e.g. weekly summary rows)
            if ts in seen_ts:
                continue
            seen_ts.add(ts)
            # Build row_map: zip up to min of headers/cells length
            row_map = dict(zip(headers, cells))
            by_fund = {}
            total = 0.0
            for key, value in row_map.items():
                key_lower = key.lower()
                if key_lower in {"date", "total"}:
                    continue
                amount = self._parse_amount(value)
                by_fund[key] = amount
                total += amount

            total_cell = row_map.get("Total")
            if total_cell:
                parsed_total = self._parse_amount(total_cell)
                if parsed_total != 0:
                    total = parsed_total

            observations.append(
                SourceObservation(
                    source_id=self.source_id,
                    dataset=dataset,
                    symbol="US_BTC_SPOT_ETF",
                    ts=ts,
                    payload={
                        "total_netflow_usd_million": total,
                        "by_fund_usd_million": by_fund,
                        "unit": "USD_million",
                    },
                )
            )

        return self.bounded(observations, start=start, end=end)

    def _try_parse_date(self, value: str) -> Optional[datetime]:
        for fmt in ("%d %b %Y", "%Y-%m-%d", "%d/%m/%Y", "%d %B %Y"):
            try:
                return datetime.strptime(value, fmt).replace(tzinfo=self.utc_now().tzinfo)
            except ValueError:
                continue
        return None

    def _parse_date(self, value: str) -> datetime:
        result = self._try_parse_date(value)
        return result if result is not None else self.utc_now()

    @staticmethod
    def _parse_amount(value: str) -> float:
        cleaned = value.replace(",", "").replace("$", "").replace("(", "-").replace(")", "")
        cleaned = cleaned.replace("+", "").strip()
        if cleaned in {"", "-", "--", "n/a", "N/A"}:
            return 0.0
        try:
            return float(cleaned)
        except ValueError:
            return 0.0
