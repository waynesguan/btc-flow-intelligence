from __future__ import annotations

from datetime import datetime
from typing import Optional

from sources.base import SourceAdapter, SourceObservation


class KrakenAdapter(SourceAdapter):
    source_id = "kraken"
    auth_type = "none"
    rate_limit = {"requests_per_minute": 60}
    max_history_depth = "1y"
    field_mapping = {}
    ts_spec = "Exchange-defined"
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
        # TODO(Phase 2): implement Kraken public REST ingestion.
        return []
