from __future__ import annotations

from datetime import datetime
from typing import Optional

from sources.base import SourceAdapter, SourceObservation


class CoinMetricsAdapter(SourceAdapter):
    source_id = "coin_metrics"
    auth_type = "api_key"
    rate_limit = {"requests_per_minute": 30}
    max_history_depth = "all"
    field_mapping = {}
    ts_spec = "Provider-defined"
    retry_policy = {"max_retries": 3, "backoff": "exponential"}

    @property
    def datasets(self) -> list[str]:
        return ["onchain_premium"]

    def fetch(
        self,
        dataset: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> list[SourceObservation]:
        # TODO(Phase 3): implement paid source ingestion once API key is provided.
        return []
