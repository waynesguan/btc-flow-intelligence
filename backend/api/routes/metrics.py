from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_
from sqlalchemy.orm import Session

from api.cache import cache_get_json, cache_set_json
from db.models import MetricCatalog, MetricValue
from db.session import get_db

router = APIRouter(prefix="/metrics", tags=["metrics"])


def _period_key(ts: datetime, granularity: str) -> tuple:
    if granularity == "daily":
        return (ts.year, ts.month, ts.day)
    if granularity == "weekly":
        iso = ts.isocalendar()
        return (iso.year, iso.week)
    if granularity == "monthly":
        return (ts.year, ts.month)
    raise HTTPException(status_code=400, detail=f"unsupported granularity: {granularity}")


def _aggregate_metric_rows(rows: list[MetricValue], granularity: str) -> list[dict]:
    if granularity == "daily":
        return [
            {
                "ts": row.ts,
                "value": float(row.value),
                "aux": row.aux,
            }
            for row in rows
        ]

    buckets: dict[tuple, list[MetricValue]] = defaultdict(list)
    for row in rows:
        buckets[_period_key(row.ts, granularity)].append(row)

    data: list[dict] = []
    for key in sorted(buckets.keys()):
        bucket = sorted(buckets[key], key=lambda r: r.ts)
        avg_value = sum(float(item.value) for item in bucket) / len(bucket)
        last = bucket[-1]
        data.append(
            {
                "ts": last.ts,
                "value": avg_value,
                "aux": {
                    "aggregation": "mean",
                    "points": len(bucket),
                    "last_aux": last.aux,
                },
            }
        )
    return data


@router.get("/catalog")
def metric_catalog(
    tier: Optional[str] = Query(default=None),
    lead_lag: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    cache_key = f"metrics:catalog:{tier}:{lead_lag}"
    cached = cache_get_json(cache_key)
    if cached:
        return cached

    query = db.query(MetricCatalog)
    if tier:
        query = query.filter(MetricCatalog.tier == tier)
    if lead_lag:
        query = query.filter(MetricCatalog.lead_lag == lead_lag)

    rows = query.order_by(MetricCatalog.dimension.asc(), MetricCatalog.metric_id.asc()).all()
    data = [
        {
            "metric_id": row.metric_id,
            "name": row.name,
            "dimension": row.dimension,
            "lead_lag": row.lead_lag,
            "definition_short": row.definition_short,
            "definition_pro": row.definition_pro,
            "calc_spec": row.calc_spec,
            "source_priority": row.source_priority,
            "refresh_policy": row.refresh_policy,
            "failure_modes": row.failure_modes,
            "chart_spec": row.chart_spec,
            "version": row.version,
            "tier": row.tier,
            "is_active": row.is_active,
            "available_since": row.available_since,
        }
        for row in rows
    ]

    payload = {
        "data": data,
        "meta": {
            "source": "metric_catalog",
            "delay": "n/a",
            "unit": None,
            "version": 1,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    cache_set_json(cache_key, payload, ttl_seconds=300)
    return payload


@router.get("/{metric_id}")
def metric_values(
    metric_id: str,
    start: Optional[datetime] = Query(default=None),
    end: Optional[datetime] = Query(default=None),
    granularity: str = Query(default="daily"),
    db: Session = Depends(get_db),
) -> dict:
    metric = db.query(MetricCatalog).filter(MetricCatalog.metric_id == metric_id).one_or_none()
    if metric is None:
        raise HTTPException(status_code=404, detail=f"metric_id not found: {metric_id}")

    query = db.query(MetricValue).filter(MetricValue.metric_id == metric_id)
    filters = []
    if start:
        filters.append(MetricValue.ts >= start)
    if end:
        filters.append(MetricValue.ts <= end)
    if filters:
        query = query.filter(and_(*filters))

    rows = query.order_by(MetricValue.ts.asc()).all()
    data = _aggregate_metric_rows(rows, granularity)

    return {
        "data": {
            "metric": {
                "metric_id": metric.metric_id,
                "name": metric.name,
                "unit": metric.chart_spec.get("unit"),
                "available_since": metric.available_since,
                "tier": metric.tier,
                "lead_lag": metric.lead_lag,
                "version": metric.version,
            },
            "series": data,
        },
        "meta": {
            "source": ",".join(metric.source_priority.get("sources", [])),
            "delay": metric.refresh_policy.get("delay", "unknown"),
            "unit": metric.chart_spec.get("unit"),
            "version": metric.version,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
