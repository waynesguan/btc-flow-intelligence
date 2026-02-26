from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Optional

import yaml
from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from db.models import MetricValue, Score


def _load_weights() -> dict:
    current = Path(__file__).resolve()
    candidates = [
        current.parents[2] / "config" / "scoring_weights.yaml",  # repo-root config
        current.parents[1] / "config" / "scoring_weights.yaml",  # container /app/config fallback
    ]

    for config_path in candidates:
        if config_path.exists():
            with config_path.open("r", encoding="utf-8") as file:
                return yaml.safe_load(file)

    raise FileNotFoundError("config/scoring_weights.yaml not found")


def _clip(value: float, min_v: float, max_v: float) -> float:
    return max(min_v, min(max_v, value))


def _zscore_to_0100(value: float, avg: float, sd: float) -> float:
    if sd == 0:
        return 50.0
    z = (value - avg) / sd
    return _clip(50 + 15 * z, 0, 100)


def _query_metric_series(
    db: Session,
    metric_ids: list[str],
    start: Optional[datetime],
    end: Optional[datetime],
) -> dict[str, dict[datetime, float]]:
    stmt = select(MetricValue).where(MetricValue.metric_id.in_(metric_ids))
    filters = []
    if start:
        filters.append(MetricValue.ts >= start)
    if end:
        filters.append(MetricValue.ts <= end)
    if filters:
        stmt = stmt.where(and_(*filters))

    series: dict[str, dict[datetime, float]] = defaultdict(dict)
    for row in db.execute(stmt).scalars().all():
        series[row.metric_id][row.ts] = float(row.value)
    return series


def _normalize_component(raw_component: dict[datetime, float]) -> dict[datetime, float]:
    if not raw_component:
        return {}
    vals = list(raw_component.values())
    avg = mean(vals)
    sd = pstdev(vals)
    return {ts: _zscore_to_0100(value=v, avg=avg, sd=sd) for ts, v in raw_component.items()}


def _weighted_score(
    ts: datetime,
    component_scores: dict[str, dict[datetime, float]],
    weights: dict[str, float],
) -> tuple[Optional[float], dict]:
    numerator = 0.0
    denominator = 0.0
    resolved: dict[str, float] = {}

    for component, weight in weights.items():
        v = component_scores.get(component, {}).get(ts)
        if v is None:
            continue
        numerator += v * weight
        denominator += weight
        resolved[component] = v

    if denominator == 0:
        return None, {"components": resolved, "renormalized": False, "available_components": 0}

    return (
        numerator / denominator,
        {
            "components": resolved,
            "renormalized": denominator != 1.0,
            "available_components": len(resolved),
        },
    )


def _capital_grade(
    index: int,
    points: list[tuple[datetime, float]],
    thresholds: dict,
) -> tuple[str, bool]:
    strong_inflow = float(thresholds.get("strong_inflow", 70))
    sustained_days = int(thresholds.get("strong_inflow_sustained_days", 7))
    sustained_min = float(thresholds.get("strong_inflow_min_during_sustained", 60))
    weak_min = float(thresholds.get("weak_inflow_min", 40))

    _, current = points[index]
    if current >= strong_inflow:
        start_idx = index - sustained_days + 1
        if start_idx >= 0:
            window = points[start_idx : index + 1]
            is_consecutive = all(
                (window[i][0].date() - window[i - 1][0].date()).days == 1 for i in range(1, len(window))
            )
            meets_floor = all(v >= sustained_min for _, v in window)
            if is_consecutive and meets_floor:
                return "强回流", True

    if current >= weak_min:
        return "弱回流", False

    return "无回流", False


def _risk_band(score: float, thresholds: dict) -> str:
    high = float(thresholds.get("high_risk", 70))
    moderate = float(thresholds.get("moderate_risk", 40))
    if score >= high:
        return "高风险"
    if score >= moderate:
        return "中风险"
    return "低风险"


def _upsert_scores(db: Session, rows: list[dict]) -> int:
    if not rows:
        return 0
    stmt = insert(Score).values(rows)
    upsert = stmt.on_conflict_do_update(
        index_elements=["score_id", "ts"],
        set_={
            "value": stmt.excluded.value,
            "components": stmt.excluded.components,
        },
    )
    result = db.execute(upsert)
    return int(result.rowcount or 0)


def _as_risk_liquidation(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return math.log1p(abs(value))


def compute_scores(
    db: Session,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> int:
    cfg = _load_weights()
    capital_weights = cfg["capital_inflow_score"]["weights"]
    capital_thresholds = cfg["capital_inflow_score"].get("thresholds", {})
    risk_weights = cfg["structure_risk_score"]["weights"]
    risk_thresholds = cfg["structure_risk_score"].get("thresholds", {})

    metric_ids = [
        "us_spot_etf_netflow_total",
        "stablecoin_net_mint_burn",
        "usdt_supply_change",
        "usdc_supply_change",
        "spot_volume_trend",
        "futures_open_interest",
        "funding_rate",
        "basis_spread",
        "leverage_risk_index",
        "liquidation_volume",
        "fed_balance_sheet_change",
        "dxy",
        "realized_cap_change",
        "whale_accumulation",
        "exchange_netflow",
    ]
    metric_series = _query_metric_series(db=db, metric_ids=metric_ids, start=start, end=end)

    all_ts = sorted({ts for metric_map in metric_series.values() for ts in metric_map.keys()})

    raw_capital_components: dict[str, dict[datetime, float]] = defaultdict(dict)
    raw_risk_components: dict[str, dict[datetime, float]] = defaultdict(dict)

    for ts in all_ts:
        etf = metric_series.get("us_spot_etf_netflow_total", {}).get(ts)
        if etf is not None:
            raw_capital_components["etf_institutional"][ts] = etf

        stable_net = metric_series.get("stablecoin_net_mint_burn", {}).get(ts)
        if stable_net is None:
            stable_parts = []
            usdt = metric_series.get("usdt_supply_change", {}).get(ts)
            usdc = metric_series.get("usdc_supply_change", {}).get(ts)
            if usdt is not None:
                stable_parts.append(usdt)
            if usdc is not None:
                stable_parts.append(usdc)
            if stable_parts:
                stable_net = sum(stable_parts) / len(stable_parts)
        if stable_net is not None:
            raw_capital_components["stablecoin"][ts] = stable_net

        trend = metric_series.get("spot_volume_trend", {}).get(ts)
        funding = metric_series.get("funding_rate", {}).get(ts)
        basis = metric_series.get("basis_spread", {}).get(ts)
        oi = metric_series.get("futures_open_interest", {}).get(ts)
        deriv_parts = []
        if trend is not None:
            deriv_parts.append(trend)
        if funding is not None:
            deriv_parts.append(-abs(funding) * 10000)
        if basis is not None:
            deriv_parts.append(-abs(basis) / 100)
        if oi is not None:
            deriv_parts.append(-(oi / 1_000_000))
        if deriv_parts:
            raw_capital_components["spot_derivatives"][ts] = sum(deriv_parts) / len(deriv_parts)

        realized_change = metric_series.get("realized_cap_change", {}).get(ts)
        whale = metric_series.get("whale_accumulation", {}).get(ts)
        exchange_netflow = metric_series.get("exchange_netflow", {}).get(ts)
        onchain_parts = []
        if realized_change is not None:
            onchain_parts.append(realized_change)
        if whale is not None:
            onchain_parts.append(whale)
        if exchange_netflow is not None:
            onchain_parts.append(-exchange_netflow)
        if onchain_parts:
            raw_capital_components["onchain_capital"][ts] = sum(onchain_parts) / len(onchain_parts)

        fed = metric_series.get("fed_balance_sheet_change", {}).get(ts)
        dxy = metric_series.get("dxy", {}).get(ts)
        macro_parts = []
        if fed is not None:
            macro_parts.append(fed)
        if dxy is not None:
            macro_parts.append(-dxy / 10)
        if macro_parts:
            raw_capital_components["macro"][ts] = sum(macro_parts) / len(macro_parts)

        leverage = metric_series.get("leverage_risk_index", {}).get(ts)
        if leverage is not None:
            raw_risk_components["leverage"][ts] = leverage

        liquidation = _as_risk_liquidation(metric_series.get("liquidation_volume", {}).get(ts))
        if liquidation is None and funding is not None:
            liquidation = abs(funding) * 10000
        if liquidation is not None:
            raw_risk_components["liquidation"][ts] = liquidation

        if basis is not None:
            raw_risk_components["basis"][ts] = abs(basis)

        if trend is not None:
            raw_risk_components["trend"][ts] = -trend

    norm_capital = {
        name: _normalize_component(raw_values)
        for name, raw_values in raw_capital_components.items()
    }
    norm_risk = {
        name: _normalize_component(raw_values)
        for name, raw_values in raw_risk_components.items()
    }

    capital_temp: dict[datetime, tuple[float, dict]] = {}
    risk_temp: dict[datetime, tuple[float, dict]] = {}

    for ts in all_ts:
        cap_score, cap_components = _weighted_score(ts=ts, component_scores=norm_capital, weights=capital_weights)
        if cap_score is not None:
            capital_temp[ts] = (_clip(cap_score, 0, 100), cap_components)

        risk_score, risk_components = _weighted_score(ts=ts, component_scores=norm_risk, weights=risk_weights)
        if risk_score is not None:
            clipped = _clip(risk_score, 0, 100)
            risk_components["band"] = _risk_band(clipped, risk_thresholds)
            risk_temp[ts] = (clipped, risk_components)

    score_rows: list[dict] = []

    capital_points = sorted(capital_temp.items(), key=lambda x: x[0])
    capital_value_points = [(ts, score_components[0]) for ts, score_components in capital_points]
    capital_values = [v for _, v in capital_value_points]

    for idx, (ts, (score, components)) in enumerate(capital_points):
        grade, sustained = _capital_grade(idx, capital_value_points, capital_thresholds)
        row_components = {
            **components,
            "grade": grade,
            "is_strong_sustained": sustained,
            "distribution": {
                "mean": mean(capital_values) if capital_values else 0,
                "median": median(capital_values) if capital_values else 0,
            },
        }
        score_rows.append(
            {
                "score_id": "capital_inflow_score",
                "ts": ts,
                "value": score,
                "components": row_components,
            }
        )

    for ts, (score, components) in sorted(risk_temp.items(), key=lambda x: x[0]):
        score_rows.append(
            {
                "score_id": "structure_risk_score",
                "ts": ts,
                "value": score,
                "components": components,
            }
        )

    return _upsert_scores(db=db, rows=score_rows)
