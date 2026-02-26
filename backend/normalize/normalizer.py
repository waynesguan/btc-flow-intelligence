from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import Select, and_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from db.models import NormalizedSeries, RawObservation

logger = logging.getLogger(__name__)


@dataclass
class NormalizedPoint:
    series_id: str
    ts: datetime
    value: float
    unit: str
    source_id: str
    quality_flags: dict


def _normalize_fred(raw: RawObservation) -> list[NormalizedPoint]:
    payload = raw.payload
    series_id = payload.get("series_id")
    if not series_id:
        return []
    return [
        NormalizedPoint(
            series_id=series_id,
            ts=raw.ts,
            value=float(payload.get("value", 0.0)),
            unit=payload.get("unit", "unknown"),
            source_id=raw.source_id,
            quality_flags={},
        )
    ]


def _normalize_coinbase(raw: RawObservation) -> list[NormalizedPoint]:
    payload = raw.payload
    return [
        NormalizedPoint(
            series_id="market.spot.btcusd.price_close",
            ts=raw.ts,
            value=float(payload.get("close", 0.0)),
            unit="USD",
            source_id=raw.source_id,
            quality_flags={},
        ),
        NormalizedPoint(
            series_id="market.spot.btcusd.volume_coinbase",
            ts=raw.ts,
            value=float(payload.get("volume", 0.0)),
            unit="BTC",
            source_id=raw.source_id,
            quality_flags={},
        ),
    ]


def _normalize_spot_exchange(raw: RawObservation, exchange: str) -> list[NormalizedPoint]:
    payload = raw.payload
    return [
        NormalizedPoint(
            series_id=f"market.spot.btcusd.price_{exchange}",
            ts=raw.ts,
            value=float(payload.get("close", 0.0)),
            unit="USD",
            source_id=raw.source_id,
            quality_flags={},
        ),
        NormalizedPoint(
            series_id=f"market.spot.btcusd.volume_{exchange}",
            ts=raw.ts,
            value=float(payload.get("volume", 0.0)),
            unit="BTC",
            source_id=raw.source_id,
            quality_flags={},
        ),
    ]


def _normalize_farside(raw: RawObservation) -> list[NormalizedPoint]:
    payload = raw.payload
    points = [
        NormalizedPoint(
            series_id="etf.us_spot.netflow_total",
            ts=raw.ts,
            value=float(payload.get("total_netflow_usd_million", 0.0)),
            unit="USD_million",
            source_id=raw.source_id,
            quality_flags={},
        )
    ]
    by_fund = payload.get("by_fund_usd_million", {})
    for fund, value in by_fund.items():
        fund_key = fund.strip().lower().replace(" ", "_")
        points.append(
            NormalizedPoint(
                series_id=f"etf.us_spot.netflow_fund.{fund_key}",
                ts=raw.ts,
                value=float(value),
                unit="USD_million",
                source_id=raw.source_id,
                quality_flags={},
            )
        )
    return points


def _normalize_coingecko(raw: RawObservation) -> list[NormalizedPoint]:
    payload = raw.payload
    if raw.dataset == "btc_market_chart":
        return [
            NormalizedPoint(
                series_id="market.spot.btcusd.price_coingecko",
                ts=raw.ts,
                value=float(payload.get("price_usd", 0.0)),
                unit="USD",
                source_id=raw.source_id,
                quality_flags={},
            ),
            NormalizedPoint(
                series_id="market.spot.btcusd.volume_total",
                ts=raw.ts,
                value=float(payload.get("volume_usd", 0.0)),
                unit="USD",
                source_id=raw.source_id,
                quality_flags={},
            ),
            NormalizedPoint(
                series_id="market.spot.btcusd.market_cap",
                ts=raw.ts,
                value=float(payload.get("market_cap_usd", 0.0)),
                unit="USD",
                source_id=raw.source_id,
                quality_flags={},
            ),
        ]

    if raw.dataset == "stablecoin_market_caps":
        symbol = (raw.symbol or "").lower()
        return [
            NormalizedPoint(
                series_id=f"stablecoin.{symbol}.market_cap",
                ts=raw.ts,
                value=float(payload.get("market_cap_usd", 0.0)),
                unit="USD",
                source_id=raw.source_id,
                quality_flags={},
            )
        ]

    if raw.dataset == "derivatives_overview":
        quality_flags = payload.get("quality_flags", {})
        return [
            NormalizedPoint(
                series_id="market.derivatives.open_interest_coingecko",
                ts=raw.ts,
                value=float(payload.get("open_interest_btc", 0.0)),
                unit="BTC",
                source_id=raw.source_id,
                quality_flags=quality_flags,
            ),
            NormalizedPoint(
                series_id="market.derivatives.funding_rate_coingecko",
                ts=raw.ts,
                value=float(payload.get("funding_rate_proxy", 0.0)),
                unit="ratio",
                source_id=raw.source_id,
                quality_flags=quality_flags,
            ),
        ]

    return []


def _normalize_deribit(raw: RawObservation) -> list[NormalizedPoint]:
    payload = raw.payload
    return [
        NormalizedPoint(
            series_id="market.derivatives.open_interest_deribit",
            ts=raw.ts,
            value=float(payload.get("open_interest_btc", 0.0)),
            unit="BTC",
            source_id=raw.source_id,
            quality_flags={},
        ),
        NormalizedPoint(
            series_id="market.derivatives.funding_rate_deribit",
            ts=raw.ts,
            value=float(payload.get("funding_rate", 0.0)),
            unit="ratio",
            source_id=raw.source_id,
            quality_flags={},
        ),
        NormalizedPoint(
            series_id="market.derivatives.basis_spread_deribit",
            ts=raw.ts,
            value=float(payload.get("basis_spread", 0.0)),
            unit="USD",
            source_id=raw.source_id,
            quality_flags={},
        ),
        NormalizedPoint(
            series_id="market.derivatives.liquidation_volume_deribit",
            ts=raw.ts,
            value=float(payload.get("liquidation_volume_usd", 0.0)),
            unit="USD",
            source_id=raw.source_id,
            quality_flags={},
        ),
    ]


def _normalize_onchain(raw: RawObservation) -> list[NormalizedPoint]:
    payload = raw.payload
    fields = {
        "realized_cap": ("onchain.realized_cap", "USD"),
        "mvrv": ("onchain.mvrv", "ratio"),
        "realized_profit_loss": ("onchain.realized_profit_loss", "USD"),
        "cost_basis": ("onchain.cost_basis", "USD"),
        "lth_supply": ("onchain.lth_supply", "BTC"),
        "sth_supply": ("onchain.sth_supply", "BTC"),
        "whale_balance": ("onchain.whale_balance", "BTC"),
        "exchange_netflow": ("onchain.exchange_netflow", "BTC"),
        "exchange_stablecoin_balance": ("onchain.exchange_stablecoin_balance", "USD"),
        "stablecoin_btc_volume_share": ("onchain.stablecoin_btc_volume_share", "pct"),
    }

    points: list[NormalizedPoint] = []
    for key, (series_id, unit) in fields.items():
        raw_val = payload.get(key)
        if raw_val in (None, ""):
            continue
        try:
            value = float(raw_val)
        except Exception:  # noqa: BLE001
            continue

        points.append(
            NormalizedPoint(
                series_id=series_id,
                ts=raw.ts,
                value=value,
                unit=unit,
                source_id=raw.source_id,
                quality_flags={"provider": payload.get("provider", raw.source_id)},
            )
        )

    return points


def normalize_raw_record(raw: RawObservation) -> list[NormalizedPoint]:
    if raw.source_id == "fred":
        return _normalize_fred(raw)
    if raw.source_id == "coinbase":
        return _normalize_coinbase(raw)
    if raw.source_id == "farside":
        return _normalize_farside(raw)
    if raw.source_id == "coingecko":
        return _normalize_coingecko(raw)
    if raw.source_id == "kraken":
        return _normalize_spot_exchange(raw, "kraken")
    if raw.source_id == "bitstamp":
        return _normalize_spot_exchange(raw, "bitstamp")
    if raw.source_id == "deribit":
        return _normalize_deribit(raw)
    if raw.source_id in {"glassnode", "coin_metrics"}:
        return _normalize_onchain(raw)
    return []


def _build_raw_query(start: Optional[datetime], end: Optional[datetime]) -> Select[tuple[RawObservation]]:
    stmt = select(RawObservation)
    filters = []
    if start:
        filters.append(RawObservation.ts >= start)
    if end:
        filters.append(RawObservation.ts <= end)
    if filters:
        stmt = stmt.where(and_(*filters))
    return stmt.order_by(RawObservation.ts.asc())


def upsert_normalized_series(db: Session, points: list[NormalizedPoint]) -> int:
    if not points:
        return 0

    values = [
        {
            "series_id": point.series_id,
            "ts": point.ts,
            "value": point.value,
            "unit": point.unit,
            "source_id": point.source_id,
            "quality_flags": point.quality_flags,
        }
        for point in points
    ]

    stmt = insert(NormalizedSeries).values(values)
    upsert = stmt.on_conflict_do_update(
        index_elements=["series_id", "ts"],
        set_={
            "value": stmt.excluded.value,
            "unit": stmt.excluded.unit,
            "source_id": stmt.excluded.source_id,
            "quality_flags": stmt.excluded.quality_flags,
        },
    )
    result = db.execute(upsert)
    return int(result.rowcount or 0)


def run_normalization(
    db: Session,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> int:
    affected = 0
    stmt = _build_raw_query(start=start, end=end)
    rows = db.execute(stmt).scalars().all()
    for raw in rows:
        points = normalize_raw_record(raw)
        affected += upsert_normalized_series(db=db, points=points)

    logger.info("normalization_complete records=%s", affected)
    return affected
