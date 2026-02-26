from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from config.settings import get_settings
from sources.base import SourceAdapter, SourceObservation

settings = get_settings()
logger = logging.getLogger(__name__)


class FredAdapter(SourceAdapter):
    source_id = "fred"
    auth_type = "api_key"
    rate_limit = {"requests_per_minute": 120}
    max_history_depth = "all"
    field_mapping = {
        "date": "ts",
        "value": "value",
    }
    ts_spec = "Daily close in UTC"
    retry_policy = {"max_retries": 3, "backoff": "exponential"}

    series_map = {
        "WALCL": {"series_id": "macro.fed_balance_sheet.total_assets", "unit": "USD_million"},
        "DTWEXBGS": {"series_id": "macro.dxy.broad", "unit": "index"},
        "DGS2": {"series_id": "macro.ust.2y_yield", "unit": "pct"},
        "DGS10": {"series_id": "macro.ust.10y_yield", "unit": "pct"},
    }

    @property
    def datasets(self) -> list[str]:
        return ["macro_core"]

    def fetch(
        self,
        dataset: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> list[SourceObservation]:
        if not settings.fred_api_key or settings.fred_api_key == "__REQUIRED__":
            logger.warning("fred_api_key_missing source=fred dataset=%s", dataset)
            raise RuntimeError("FRED_API_KEY is required for FRED ingestion")
        if dataset != "macro_core":
            return []

        observations: list[SourceObservation] = []
        for fred_series, meta in self.series_map.items():
            params: dict[str, str] = {
                "series_id": fred_series,
                "file_type": "json",
                "observation_start": (start.date().isoformat() if start else "2005-01-01"),
            }
            if end:
                params["observation_end"] = end.date().isoformat()
            params["api_key"] = settings.fred_api_key

            data = self._request_json(
                method="GET",
                url="https://api.stlouisfed.org/fred/series/observations",
                params=params,
            )

            for row in data.get("observations", []):
                value = row.get("value")
                if value in (".", None, ""):
                    continue
                ts = self.parse_iso_date(row["date"])
                observations.append(
                    SourceObservation(
                        source_id=self.source_id,
                        dataset=dataset,
                        symbol=fred_series,
                        ts=ts,
                        payload={
                            "value": float(value),
                            "series_id": meta["series_id"],
                            "unit": meta["unit"],
                            "raw_series": fred_series,
                        },
                    )
                )

        return self.bounded(observations, start=start, end=end)
