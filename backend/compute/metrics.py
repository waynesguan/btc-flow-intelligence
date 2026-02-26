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


SERIES_IDS = [
    "etf.us_spot.netflow_total",
    "market.spot.btcusd.price_close",
    "market.spot.btcusd.price_coingecko",
    "market.spot.btcusd.price_kraken",
    "market.spot.btcusd.price_bitstamp",
    "market.spot.btcusd.volume_coinbase",
    "market.spot.btcusd.volume_kraken",
    "market.spot.btcusd.volume_bitstamp",
    "market.spot.btcusd.volume_total",
    "market.spot.btcusd.market_cap",
    "stablecoin.usdt.market_cap",
    "stablecoin.usdc.market_cap",
    "market.derivatives.open_interest_coingecko",
    "market.derivatives.open_interest_deribit",
    "market.derivatives.funding_rate_coingecko",
    "market.derivatives.funding_rate_deribit",
    "market.derivatives.basis_spread_deribit",
    "market.derivatives.liquidation_volume_deribit",
    "macro.fed_balance_sheet.total_assets",
    "macro.dxy.broad",
    "macro.ust.2y_yield",
    "macro.ust.10y_yield",
    "onchain.realized_cap",
    "onchain.mvrv",
    "onchain.realized_profit_loss",
    "onchain.cost_basis",
    "onchain.lth_supply",
    "onchain.sth_supply",
    "onchain.whale_balance",
    "onchain.exchange_netflow",
    "onchain.exchange_stablecoin_balance",
    "onchain.stablecoin_btc_volume_share",
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


def _latest_avg(ts: datetime, buckets: list[SeriesBucket]) -> Optional[float]:
    vals = [bucket.latest_at(ts) for bucket in buckets]
    valid = [v for v in vals if v is not None]
    if not valid:
        return None
    return sum(valid) / len(valid)


def _latest_sum(ts: datetime, buckets: list[SeriesBucket]) -> Optional[float]:
    vals = [bucket.latest_at(ts) for bucket in buckets]
    valid = [v for v in vals if v is not None]
    if not valid:
        return None
    return sum(valid)


def _first_non_null(values: list[Optional[float]]) -> Optional[float]:
    for value in values:
        if value is not None:
            return value
    return None


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


def _append_metric(
    rows: list[dict],
    touched: set[str],
    metric_id: str,
    ts: datetime,
    value: Optional[float],
    aux: dict,
) -> None:
    if value is None:
        return
    rows.append(
        {
            "metric_id": metric_id,
            "ts": ts,
            "value": value,
            "aux": aux,
        }
    )
    touched.add(metric_id)


def compute_metrics(
    db: Session,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> int:
    series = _load_series(db=db, series_ids=SERIES_IDS, start=start, end=end)
    etf_by_fund = _load_etf_by_fund(db=db, start=start, end=end)

    timeline: set[datetime] = set()
    for bucket in series.values():
        timeline.update(bucket.dates)

    metric_rows: list[dict] = []
    touched_metric_ids: set[str] = set()

    synthetic_volume = SeriesBucket([], [])
    synthetic_realized_cap = SeriesBucket([], [])

    for ts in sorted(timeline):
        # Dimension 2: ETF and institutional
        etf_total = series.get("etf.us_spot.netflow_total", SeriesBucket([], [])).latest_at(ts)
        by_fund = etf_by_fund.get(ts, {})

        _append_metric(
            metric_rows,
            touched_metric_ids,
            "us_spot_etf_netflow_total",
            ts,
            etf_total,
            {"unit": "USD_million"},
        )
        _append_metric(
            metric_rows,
            touched_metric_ids,
            "us_spot_etf_netflow_by_fund",
            ts,
            etf_total,
            {"unit": "USD_million", "by_fund": by_fund},
        )

        grayscale_flow = None
        for key, value in by_fund.items():
            key_norm = key.lower()
            if "grayscale" in key_norm or "gbtc" in key_norm:
                grayscale_flow = float(value)
                break
        _append_metric(
            metric_rows,
            touched_metric_ids,
            "grayscale_holdings_change",
            ts,
            grayscale_flow,
            {"unit": "USD_million", "source": "farside", "proxy": True},
        )

        coinbase_price = series.get("market.spot.btcusd.price_close", SeriesBucket([], [])).latest_at(ts)
        ref_price = _latest_avg(
            ts,
            [
                series.get("market.spot.btcusd.price_coingecko", SeriesBucket([], [])),
                series.get("market.spot.btcusd.price_kraken", SeriesBucket([], [])),
                series.get("market.spot.btcusd.price_bitstamp", SeriesBucket([], [])),
            ],
        )
        if coinbase_price is not None and ref_price not in (None, 0):
            premium = ((coinbase_price - ref_price) / ref_price) * 100
            _append_metric(
                metric_rows,
                touched_metric_ids,
                "coinbase_premium",
                ts,
                premium,
                {
                    "coinbase_price": coinbase_price,
                    "reference_price": ref_price,
                    "unit": "pct",
                },
            )
        else:
            premium = None

        # Dimension 3: stablecoin
        usdt_cap_bucket = series.get("stablecoin.usdt.market_cap")
        usdc_cap_bucket = series.get("stablecoin.usdc.market_cap")
        usdt_curr = usdt_cap_bucket.latest_at(ts) if usdt_cap_bucket else None
        usdt_prev = usdt_cap_bucket.latest_before_days(ts, 1) if usdt_cap_bucket else None
        usdc_curr = usdc_cap_bucket.latest_at(ts) if usdc_cap_bucket else None
        usdc_prev = usdc_cap_bucket.latest_before_days(ts, 1) if usdc_cap_bucket else None

        usdt_change = _safe_change(usdt_curr, usdt_prev)
        usdc_change = _safe_change(usdc_curr, usdc_prev)

        _append_metric(
            metric_rows,
            touched_metric_ids,
            "usdt_supply_change",
            ts,
            usdt_change,
            {"current": usdt_curr, "previous": usdt_prev, "unit": "pct"},
        )
        _append_metric(
            metric_rows,
            touched_metric_ids,
            "usdc_supply_change",
            ts,
            usdc_change,
            {"current": usdc_curr, "previous": usdc_prev, "unit": "pct"},
        )

        stable_net = None
        if usdt_change is not None or usdc_change is not None:
            stable_net = (usdt_change or 0.0) + (usdc_change or 0.0)
        _append_metric(
            metric_rows,
            touched_metric_ids,
            "stablecoin_net_mint_burn",
            ts,
            stable_net,
            {"unit": "pct", "proxy": True},
        )

        # Dimension 4: spot + derivatives
        spot_volume = _latest_sum(
            ts,
            [
                series.get("market.spot.btcusd.volume_coinbase", SeriesBucket([], [])),
                series.get("market.spot.btcusd.volume_kraken", SeriesBucket([], [])),
                series.get("market.spot.btcusd.volume_bitstamp", SeriesBucket([], [])),
            ],
        )
        if spot_volume is None:
            spot_volume = series.get("market.spot.btcusd.volume_total", SeriesBucket([], [])).latest_at(ts)

        if spot_volume is not None:
            if synthetic_volume.dates and synthetic_volume.dates[-1] == ts:
                synthetic_volume.values[-1] = spot_volume
            else:
                synthetic_volume.dates.append(ts)
                synthetic_volume.values.append(spot_volume)

        short_avg = _safe_avg(synthetic_volume.window_values(ts, days=7))
        long_avg = _safe_avg(synthetic_volume.window_values(ts, days=30))
        spot_volume_trend = None
        if short_avg is not None and long_avg not in (None, 0):
            spot_volume_trend = ((short_avg - long_avg) / long_avg) * 100

        _append_metric(
            metric_rows,
            touched_metric_ids,
            "spot_volume_trend",
            ts,
            spot_volume_trend,
            {
                "avg_7d": short_avg,
                "avg_30d": long_avg,
                "unit": "pct",
            },
        )

        oi = _latest_sum(
            ts,
            [
                series.get("market.derivatives.open_interest_coingecko", SeriesBucket([], [])),
                series.get("market.derivatives.open_interest_deribit", SeriesBucket([], [])),
            ],
        )
        fr = _first_non_null(
            [
                series.get("market.derivatives.funding_rate_deribit", SeriesBucket([], [])).latest_at(ts),
                series.get("market.derivatives.funding_rate_coingecko", SeriesBucket([], [])).latest_at(ts),
            ]
        )

        _append_metric(
            metric_rows,
            touched_metric_ids,
            "futures_open_interest",
            ts,
            oi,
            {"unit": "BTC"},
        )
        _append_metric(
            metric_rows,
            touched_metric_ids,
            "funding_rate",
            ts,
            fr,
            {"unit": "ratio"},
        )

        basis_spread = _first_non_null(
            [
                series.get("market.derivatives.basis_spread_deribit", SeriesBucket([], [])).latest_at(ts),
                ((coinbase_price - ref_price) if coinbase_price is not None and ref_price is not None else None),
            ]
        )
        _append_metric(
            metric_rows,
            touched_metric_ids,
            "basis_spread",
            ts,
            basis_spread,
            {"unit": "USD"},
        )

        liquidation = series.get("market.derivatives.liquidation_volume_deribit", SeriesBucket([], [])).latest_at(ts)
        if liquidation is None and oi is not None and fr is not None:
            liquidation = abs(oi * fr * 1000)
            liquidation_proxy = True
        else:
            liquidation_proxy = False

        _append_metric(
            metric_rows,
            touched_metric_ids,
            "liquidation_volume",
            ts,
            liquidation,
            {"unit": "USD", "proxy": liquidation_proxy},
        )

        basis_pct = 0.0
        if basis_spread is not None and ref_price not in (None, 0):
            basis_pct = basis_spread / ref_price

        leverage = None
        if oi is not None or fr is not None:
            leverage = (oi or 0.0) / 1_000_000 * 15 + abs(fr or 0.0) * 100000 + abs(basis_pct) * 400
            leverage = _clip(leverage, 0, 100)

        _append_metric(
            metric_rows,
            touched_metric_ids,
            "leverage_risk_index",
            ts,
            leverage,
            {
                "open_interest": oi,
                "funding_rate": fr,
                "basis_pct": basis_pct,
            },
        )

        # Dimension 5: macro
        walcl_bucket = series.get("macro.fed_balance_sheet.total_assets")
        dxy_bucket = series.get("macro.dxy.broad")
        dgs2_bucket = series.get("macro.ust.2y_yield")
        dgs10_bucket = series.get("macro.ust.10y_yield")

        walcl_now = walcl_bucket.latest_at(ts) if walcl_bucket else None
        walcl_prev_30 = walcl_bucket.latest_before_days(ts, 30) if walcl_bucket else None
        fed_change = _safe_change(walcl_now, walcl_prev_30)
        _append_metric(
            metric_rows,
            touched_metric_ids,
            "fed_balance_sheet_change",
            ts,
            fed_change,
            {
                "current": walcl_now,
                "previous_30d": walcl_prev_30,
                "unit": "pct",
            },
        )

        dxy_now = dxy_bucket.latest_at(ts) if dxy_bucket else None
        _append_metric(metric_rows, touched_metric_ids, "dxy", ts, dxy_now, {"unit": "index"})

        dgs2_now = dgs2_bucket.latest_at(ts) if dgs2_bucket else None
        _append_metric(metric_rows, touched_metric_ids, "ust_2y_yield", ts, dgs2_now, {"unit": "pct"})

        dgs10_now = dgs10_bucket.latest_at(ts) if dgs10_bucket else None
        _append_metric(metric_rows, touched_metric_ids, "ust_10y_yield", ts, dgs10_now, {"unit": "pct"})

        dxy_prev_30 = dxy_bucket.latest_before_days(ts, 30) if dxy_bucket else None
        dxy_change_30 = _safe_change(dxy_now, dxy_prev_30)
        if fed_change is not None or dxy_change_30 is not None:
            proxy = (fed_change or 0.0) - (dxy_change_30 or 0.0) * 1.5 - ((dgs10_now or 0.0) - (dgs2_now or 0.0))
        else:
            proxy = None
        _append_metric(
            metric_rows,
            touched_metric_ids,
            "global_liquidity_proxy",
            ts,
            proxy,
            {
                "fed_change_30d_pct": fed_change,
                "dxy_change_30d_pct": dxy_change_30,
                "yield_curve_spread": (dgs10_now or 0.0) - (dgs2_now or 0.0),
            },
        )

        # Dimension 1: on-chain capital (Phase 3 + proxy fallbacks)
        market_cap = series.get("market.spot.btcusd.market_cap", SeriesBucket([], [])).latest_at(ts)
        realized_cap = _first_non_null(
            [
                series.get("onchain.realized_cap", SeriesBucket([], [])).latest_at(ts),
                (market_cap * 0.65 if market_cap is not None else None),
            ]
        )
        realized_cap_proxy = series.get("onchain.realized_cap", SeriesBucket([], [])).latest_at(ts) is None

        _append_metric(
            metric_rows,
            touched_metric_ids,
            "realized_cap",
            ts,
            realized_cap,
            {"unit": "USD", "proxy": realized_cap_proxy},
        )

        if realized_cap is not None:
            if synthetic_realized_cap.dates and synthetic_realized_cap.dates[-1] == ts:
                synthetic_realized_cap.values[-1] = realized_cap
            else:
                synthetic_realized_cap.dates.append(ts)
                synthetic_realized_cap.values.append(realized_cap)

        realized_cap_prev = synthetic_realized_cap.latest_before_days(ts, 1)
        realized_cap_change = _safe_change(realized_cap, realized_cap_prev)
        _append_metric(
            metric_rows,
            touched_metric_ids,
            "realized_cap_change",
            ts,
            realized_cap_change,
            {"unit": "pct", "proxy": realized_cap_proxy},
        )

        market_cap_prev = series.get("market.spot.btcusd.market_cap", SeriesBucket([], [])).latest_before_days(ts, 1)
        realized_profit_loss = _first_non_null(
            [
                series.get("onchain.realized_profit_loss", SeriesBucket([], [])).latest_at(ts),
                ((market_cap - market_cap_prev) if market_cap is not None and market_cap_prev is not None else None),
            ]
        )
        _append_metric(
            metric_rows,
            touched_metric_ids,
            "realized_profit_loss",
            ts,
            realized_profit_loss,
            {
                "unit": "USD",
                "proxy": series.get("onchain.realized_profit_loss", SeriesBucket([], [])).latest_at(ts) is None,
            },
        )

        mvrv = _first_non_null(
            [
                series.get("onchain.mvrv", SeriesBucket([], [])).latest_at(ts),
                (market_cap / realized_cap if market_cap is not None and realized_cap not in (None, 0) else None),
            ]
        )
        _append_metric(
            metric_rows,
            touched_metric_ids,
            "mvrv",
            ts,
            mvrv,
            {"unit": "ratio", "proxy": series.get("onchain.mvrv", SeriesBucket([], [])).latest_at(ts) is None},
        )

        cost_basis = _first_non_null(
            [
                series.get("onchain.cost_basis", SeriesBucket([], [])).latest_at(ts),
                (realized_cap / (market_cap / ref_price) if market_cap not in (None, 0) and ref_price else None),
            ]
        )
        _append_metric(
            metric_rows,
            touched_metric_ids,
            "cost_basis_distribution",
            ts,
            cost_basis,
            {
                "unit": "USD",
                "proxy": series.get("onchain.cost_basis", SeriesBucket([], [])).latest_at(ts) is None,
                "distribution_bins": [],
            },
        )

        lth_supply = series.get("onchain.lth_supply", SeriesBucket([], [])).latest_at(ts)
        sth_supply = series.get("onchain.sth_supply", SeriesBucket([], [])).latest_at(ts)
        lth_sth = None
        if lth_supply is not None and sth_supply not in (None, 0):
            lth_sth = lth_supply / sth_supply
            proxy_lth = False
        elif realized_cap_change is not None:
            lth_sth = 1 + realized_cap_change / 100
            proxy_lth = True
        else:
            proxy_lth = True

        _append_metric(
            metric_rows,
            touched_metric_ids,
            "lth_sth_behavior",
            ts,
            lth_sth,
            {"unit": "ratio", "proxy": proxy_lth},
        )

        whale_balance_bucket = series.get("onchain.whale_balance")
        whale_now = whale_balance_bucket.latest_at(ts) if whale_balance_bucket else None
        whale_prev = whale_balance_bucket.latest_before_days(ts, 1) if whale_balance_bucket else None
        whale_accum = _safe_change(whale_now, whale_prev)
        if whale_accum is None and etf_total is not None:
            whale_accum = etf_total / 1000
            whale_proxy = True
        else:
            whale_proxy = whale_now is None
        _append_metric(
            metric_rows,
            touched_metric_ids,
            "whale_accumulation",
            ts,
            whale_accum,
            {"unit": "pct", "proxy": whale_proxy},
        )

        exchange_netflow = series.get("onchain.exchange_netflow", SeriesBucket([], [])).latest_at(ts)
        if exchange_netflow is None and spot_volume_trend is not None:
            exchange_netflow = -spot_volume_trend
            exchange_proxy = True
        else:
            exchange_proxy = False
        _append_metric(
            metric_rows,
            touched_metric_ids,
            "exchange_netflow",
            ts,
            exchange_netflow,
            {"unit": "BTC", "proxy": exchange_proxy},
        )

        inst_proxy = None
        if etf_total is not None or premium is not None or oi is not None:
            inst_proxy = 50 + (etf_total or 0) * 0.08 + (premium or 0) * 5 + (oi or 0) / 2_000_000
            inst_proxy = _clip(inst_proxy, 0, 100)
        _append_metric(
            metric_rows,
            touched_metric_ids,
            "institution_position_proxy",
            ts,
            inst_proxy,
            {"unit": "index", "proxy": True},
        )

        exch_stable = series.get("onchain.exchange_stablecoin_balance", SeriesBucket([], [])).latest_at(ts)
        exch_stable_prev = series.get("onchain.exchange_stablecoin_balance", SeriesBucket([], [])).latest_before_days(ts, 1)
        exch_stable_change = _safe_change(exch_stable, exch_stable_prev)
        if exch_stable_change is None and stable_net is not None:
            exch_stable_change = stable_net * 0.6
            exch_stable_proxy = True
        else:
            exch_stable_proxy = False
        _append_metric(
            metric_rows,
            touched_metric_ids,
            "exchange_stablecoin_balance_change",
            ts,
            exch_stable_change,
            {"unit": "pct", "proxy": exch_stable_proxy},
        )

        stablecoin_share = series.get("onchain.stablecoin_btc_volume_share", SeriesBucket([], [])).latest_at(ts)
        if stablecoin_share is None and market_cap not in (None, 0):
            stablecoin_share = ((usdt_curr or 0.0) + (usdc_curr or 0.0)) / market_cap * 100
            stablecoin_share_proxy = True
        else:
            stablecoin_share_proxy = False
        _append_metric(
            metric_rows,
            touched_metric_ids,
            "stablecoin_btc_volume_share",
            ts,
            stablecoin_share,
            {"unit": "pct", "proxy": stablecoin_share_proxy},
        )

    affected = _upsert_metric_values(db=db, rows=metric_rows)
    _update_available_since(db=db, metric_ids=touched_metric_ids)
    logger.info("compute_metrics_done affected=%s metrics=%s", affected, len(touched_metric_ids))
    return affected
