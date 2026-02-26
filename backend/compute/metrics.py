from __future__ import annotations

import logging
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from db.models import MetricCatalog, MetricValue, NormalizedSeries, RawObservation

logger = logging.getLogger(__name__)


def _day_floor(ts: datetime) -> datetime:
    return datetime(ts.year, ts.month, ts.day, tzinfo=timezone.utc)


@dataclass
class SeriesBucket:
    dates: list[datetime]
    values: list[float]

    def latest_at(self, ts: datetime) -> Optional[float]:
        idx = bisect_right(self.dates, ts) - 1
        if idx < 0:
            return None
        return self.values[idx]

    def latest_before_days(self, ts: datetime, days: int) -> Optional[float]:
        target = ts - timedelta(days=days)
        idx = bisect_right(self.dates, target) - 1
        if idx < 0:
            return None
        return self.values[idx]

    def window_values(self, ts: datetime, days: int) -> list[float]:
        start = ts - timedelta(days=days)
        left = bisect_right(self.dates, start - timedelta(seconds=1))
        right = bisect_right(self.dates, ts)
        return self.values[left:right]


REQUIRED_SERIES = [
    "etf.us_spot.netflow_total",
    "market.spot.btcusd.price_close",
    "market.spot.btcusd.price_coingecko",
    "stablecoin.usdt.market_cap",
    "stablecoin.usdc.market_cap",
    "market.spot.btcusd.volume_coinbase",
    "market.derivatives.open_interest_btc",
    "market.derivatives.funding_rate",
    "macro.fed_balance_sheet.total_assets",
    "macro.dxy.broad",
    "macro.ust.2y_yield",
    "macro.ust.10y_yield",
]


def _load_series(
    db: Session,
    series_ids: list[str],
    start: Optional[datetime],
    end: Optional[datetime],
) -> dict[str, SeriesBucket]:
    stmt = select(NormalizedSeries).where(NormalizedSeries.series_id.in_(series_ids))
    filters = []
    if start:
        filters.append(NormalizedSeries.ts >= start)
    if end:
        filters.append(NormalizedSeries.ts <= end)
    if filters:
        stmt = stmt.where(and_(*filters))
    stmt = stmt.order_by(NormalizedSeries.series_id.asc(), NormalizedSeries.ts.asc())

    grouped: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    for row in db.execute(stmt).scalars():
        grouped[row.series_id].append((_day_floor(row.ts), float(row.value)))

    buckets: dict[str, SeriesBucket] = {}
    for series_id, points in grouped.items():
        dates = [p[0] for p in points]
        values = [p[1] for p in points]
        buckets[series_id] = SeriesBucket(dates=dates, values=values)
    return buckets


def _load_etf_by_fund(db: Session, start: Optional[datetime], end: Optional[datetime]) -> dict[datetime, dict]:
    stmt = select(RawObservation).where(
        and_(
            RawObservation.source_id == "farside",
            RawObservation.dataset == "us_spot_btc_etf_flows",
        )
    )
    filters = []
    if start:
        filters.append(RawObservation.ts >= start)
    if end:
        filters.append(RawObservation.ts <= end)
    if filters:
        stmt = stmt.where(and_(*filters))

    output: dict[datetime, dict] = {}
    for row in db.execute(stmt).scalars().all():
        ts = _day_floor(row.ts)
        output[ts] = row.payload.get("by_fund_usd_million", {})
    return output


def _safe_change(current: Optional[float], prev: Optional[float]) -> Optional[float]:
    if current is None or prev in (None, 0):
        return None
    return ((current - prev) / abs(prev)) * 100


def _safe_avg(values: list[float]) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)


def _clip(value: float, min_v: float, max_v: float) -> float:
    return max(min_v, min(max_v, value))


def _upsert_metric_values(db: Session, rows: list[dict]) -> int:
    if not rows:
        return 0

    stmt = insert(MetricValue).values(rows)
    upsert = stmt.on_conflict_do_update(
        index_elements=["metric_id", "ts"],
        set_={
            "value": stmt.excluded.value,
            "aux": stmt.excluded.aux,
        },
    )
    result = db.execute(upsert)
    return int(result.rowcount or 0)


def _update_available_since(db: Session, metric_ids: set[str]) -> None:
    for metric_id in metric_ids:
        min_ts_stmt = (
            select(MetricValue.ts)
            .where(MetricValue.metric_id == metric_id)
            .order_by(MetricValue.ts.asc())
            .limit(1)
        )
        min_ts = db.execute(min_ts_stmt).scalar_one_or_none()
        if not min_ts:
            continue
        db.query(MetricCatalog).filter(MetricCatalog.metric_id == metric_id).update(
            {
                MetricCatalog.available_since: min_ts,
                MetricCatalog.updated_at: datetime.now(timezone.utc),
            }
        )


def compute_metrics(
    db: Session,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> int:
    series = _load_series(db=db, series_ids=REQUIRED_SERIES, start=start, end=end)
    etf_by_fund = _load_etf_by_fund(db=db, start=start, end=end)

    timeline: set[datetime] = set()
    for bucket in series.values():
        timeline.update(bucket.dates)

    metric_rows: list[dict] = []
    touched_metric_ids: set[str] = set()

    for ts in sorted(timeline):
        etf_total = series.get("etf.us_spot.netflow_total", SeriesBucket([], [])).latest_at(ts)
        if etf_total is not None:
            metric_rows.append(
                {
                    "metric_id": "us_spot_etf_netflow_total",
                    "ts": ts,
                    "value": etf_total,
                    "aux": {"unit": "USD_million"},
                }
            )
            touched_metric_ids.add("us_spot_etf_netflow_total")

            metric_rows.append(
                {
                    "metric_id": "us_spot_etf_netflow_by_fund",
                    "ts": ts,
                    "value": etf_total,
                    "aux": {
                        "unit": "USD_million",
                        "by_fund": etf_by_fund.get(ts, {}),
                    },
                }
            )
            touched_metric_ids.add("us_spot_etf_netflow_by_fund")

        coinbase_price = series.get("market.spot.btcusd.price_close", SeriesBucket([], [])).latest_at(ts)
        cg_price = series.get("market.spot.btcusd.price_coingecko", SeriesBucket([], [])).latest_at(ts)
        if coinbase_price and cg_price:
            premium = ((coinbase_price - cg_price) / cg_price) * 100
            metric_rows.append(
                {
                    "metric_id": "coinbase_premium",
                    "ts": ts,
                    "value": premium,
                    "aux": {
                        "coinbase_price": coinbase_price,
                        "coingecko_price": cg_price,
                        "unit": "pct",
                    },
                }
            )
            touched_metric_ids.add("coinbase_premium")

            basis_spread = coinbase_price - cg_price
            metric_rows.append(
                {
                    "metric_id": "basis_spread",
                    "ts": ts,
                    "value": basis_spread,
                    "aux": {
                        "unit": "USD",
                        "price_diff_pct": premium,
                    },
                }
            )
            touched_metric_ids.add("basis_spread")

        usdt_cap_bucket = series.get("stablecoin.usdt.market_cap")
        usdc_cap_bucket = series.get("stablecoin.usdc.market_cap")
        if usdt_cap_bucket:
            curr = usdt_cap_bucket.latest_at(ts)
            prev = usdt_cap_bucket.latest_before_days(ts, 1)
            change = _safe_change(curr, prev)
            if change is not None:
                metric_rows.append(
                    {
                        "metric_id": "usdt_supply_change",
                        "ts": ts,
                        "value": change,
                        "aux": {"current": curr, "previous": prev, "unit": "pct"},
                    }
                )
                touched_metric_ids.add("usdt_supply_change")

        if usdc_cap_bucket:
            curr = usdc_cap_bucket.latest_at(ts)
            prev = usdc_cap_bucket.latest_before_days(ts, 1)
            change = _safe_change(curr, prev)
            if change is not None:
                metric_rows.append(
                    {
                        "metric_id": "usdc_supply_change",
                        "ts": ts,
                        "value": change,
                        "aux": {"current": curr, "previous": prev, "unit": "pct"},
                    }
                )
                touched_metric_ids.add("usdc_supply_change")

        volume_bucket = series.get("market.spot.btcusd.volume_coinbase")
        if volume_bucket:
            short_avg = _safe_avg(volume_bucket.window_values(ts, days=7))
            long_avg = _safe_avg(volume_bucket.window_values(ts, days=30))
            if short_avg is not None and long_avg not in (None, 0):
                trend = ((short_avg - long_avg) / long_avg) * 100
                metric_rows.append(
                    {
                        "metric_id": "spot_volume_trend",
                        "ts": ts,
                        "value": trend,
                        "aux": {
                            "avg_7d": short_avg,
                            "avg_30d": long_avg,
                            "unit": "pct",
                        },
                    }
                )
                touched_metric_ids.add("spot_volume_trend")

        oi_bucket = series.get("market.derivatives.open_interest_btc")
        fr_bucket = series.get("market.derivatives.funding_rate")
        oi = oi_bucket.latest_at(ts) if oi_bucket else None
        fr = fr_bucket.latest_at(ts) if fr_bucket else None

        if oi is not None:
            metric_rows.append(
                {
                    "metric_id": "futures_open_interest",
                    "ts": ts,
                    "value": oi,
                    "aux": {"unit": "BTC"},
                }
            )
            touched_metric_ids.add("futures_open_interest")

        if fr is not None:
            metric_rows.append(
                {
                    "metric_id": "funding_rate",
                    "ts": ts,
                    "value": fr,
                    "aux": {"unit": "ratio"},
                }
            )
            touched_metric_ids.add("funding_rate")

        basis_pct = 0.0
        basis_bucket = None
        if coinbase_price and cg_price and cg_price != 0:
            basis_pct = (coinbase_price - cg_price) / cg_price
        if oi is not None or fr is not None:
            leverage = (oi or 0.0) / 1000000.0 * 15 + abs(fr or 0.0) * 100000 + abs(basis_pct) * 400
            leverage = _clip(leverage, 0, 100)
            metric_rows.append(
                {
                    "metric_id": "leverage_risk_index",
                    "ts": ts,
                    "value": leverage,
                    "aux": {
                        "open_interest": oi,
                        "funding_rate": fr,
                        "basis_pct": basis_pct,
                    },
                }
            )
            touched_metric_ids.add("leverage_risk_index")

        walcl_bucket = series.get("macro.fed_balance_sheet.total_assets")
        dxy_bucket = series.get("macro.dxy.broad")
        dgs2_bucket = series.get("macro.ust.2y_yield")
        dgs10_bucket = series.get("macro.ust.10y_yield")

        walcl_now = walcl_bucket.latest_at(ts) if walcl_bucket else None
        walcl_prev_30 = walcl_bucket.latest_before_days(ts, 30) if walcl_bucket else None
        fed_change = _safe_change(walcl_now, walcl_prev_30)
        if fed_change is not None:
            metric_rows.append(
                {
                    "metric_id": "fed_balance_sheet_change",
                    "ts": ts,
                    "value": fed_change,
                    "aux": {
                        "current": walcl_now,
                        "previous_30d": walcl_prev_30,
                        "unit": "pct",
                    },
                }
            )
            touched_metric_ids.add("fed_balance_sheet_change")

        dxy_now = dxy_bucket.latest_at(ts) if dxy_bucket else None
        if dxy_now is not None:
            metric_rows.append(
                {
                    "metric_id": "dxy",
                    "ts": ts,
                    "value": dxy_now,
                    "aux": {"unit": "index"},
                }
            )
            touched_metric_ids.add("dxy")

        dgs2_now = dgs2_bucket.latest_at(ts) if dgs2_bucket else None
        if dgs2_now is not None:
            metric_rows.append(
                {
                    "metric_id": "ust_2y_yield",
                    "ts": ts,
                    "value": dgs2_now,
                    "aux": {"unit": "pct"},
                }
            )
            touched_metric_ids.add("ust_2y_yield")

        dgs10_now = dgs10_bucket.latest_at(ts) if dgs10_bucket else None
        if dgs10_now is not None:
            metric_rows.append(
                {
                    "metric_id": "ust_10y_yield",
                    "ts": ts,
                    "value": dgs10_now,
                    "aux": {"unit": "pct"},
                }
            )
            touched_metric_ids.add("ust_10y_yield")

        dxy_prev_30 = dxy_bucket.latest_before_days(ts, 30) if dxy_bucket else None
        dxy_change_30 = _safe_change(dxy_now, dxy_prev_30)
        if fed_change is not None or dxy_change_30 is not None:
            proxy = (fed_change or 0.0) - (dxy_change_30 or 0.0) * 1.5 - ((dgs10_now or 0.0) - (dgs2_now or 0.0))
            metric_rows.append(
                {
                    "metric_id": "global_liquidity_proxy",
                    "ts": ts,
                    "value": proxy,
                    "aux": {
                        "fed_change_30d_pct": fed_change,
                        "dxy_change_30d_pct": dxy_change_30,
                        "yield_curve_spread": (dgs10_now or 0.0) - (dgs2_now or 0.0),
                    },
                }
            )
            touched_metric_ids.add("global_liquidity_proxy")

    affected = _upsert_metric_values(db=db, rows=metric_rows)
    _update_available_since(db=db, metric_ids=touched_metric_ids)
    logger.info("compute_metrics_done affected=%s metrics=%s", affected, len(touched_metric_ids))
    return affected
