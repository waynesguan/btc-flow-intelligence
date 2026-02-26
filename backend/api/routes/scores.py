from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_
from sqlalchemy.orm import Session

from api.cache import cache_get_json, cache_set_json
from db.models import Score
from db.session import get_db

router = APIRouter(prefix="/scores", tags=["scores"])


def _period_key(ts: datetime, granularity: str) -> tuple:
    if granularity == "daily":
        return (ts.year, ts.month, ts.day)
    if granularity == "weekly":
        iso = ts.isocalendar()
        return (iso.year, iso.week)
    if granularity == "monthly":
        return (ts.year, ts.month)
    raise HTTPException(status_code=400, detail=f"unsupported granularity: {granularity}")


def _aggregate_score_rows(rows: list[Score], granularity: str) -> list[dict]:
    if granularity == "daily":
        return [
            {
                "ts": row.ts,
                "value": float(row.value),
                "components": row.components,
            }
            for row in rows
        ]

    buckets: dict[tuple, list[Score]] = defaultdict(list)
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
                "components": {
                    **(last.components or {}),
                    "aggregation": "mean",
                    "points": len(bucket),
                },
            }
        )
    return data


def _latest_score_payload(score_id: str, db: Session) -> dict:
    row = db.query(Score).filter(Score.score_id == score_id).order_by(Score.ts.desc()).first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"{score_id} not found")

    components = row.components or {}
    return {
        "data": {
            "score_id": row.score_id,
            "ts": row.ts,
            "value": float(row.value),
            "grade": components.get("grade"),
            "band": components.get("band"),
            "components": components,
        },
        "meta": {
            "source": "computed",
            "delay": "daily",
            "unit": "0-100",
            "version": 1,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/capital_inflow/latest")
def capital_inflow_latest(db: Session = Depends(get_db)) -> dict:
    cache_key = "scores:capital_inflow:latest"
    cached = cache_get_json(cache_key)
    if cached:
        return cached

    payload = _latest_score_payload(score_id="capital_inflow_score", db=db)
    cache_set_json(cache_key, payload, ttl_seconds=60)
    return payload


@router.get("/structure_risk/latest")
def structure_risk_latest(db: Session = Depends(get_db)) -> dict:
    cache_key = "scores:structure_risk:latest"
    cached = cache_get_json(cache_key)
    if cached:
        return cached

    payload = _latest_score_payload(score_id="structure_risk_score", db=db)
    cache_set_json(cache_key, payload, ttl_seconds=60)
    return payload


@router.get("/capital_inflow")
def capital_inflow_range(
    start: Optional[datetime] = Query(default=None),
    end: Optional[datetime] = Query(default=None),
    granularity: str = Query(default="daily"),
    db: Session = Depends(get_db),
) -> dict:
    return score_range(score_id="capital_inflow_score", start=start, end=end, granularity=granularity, db=db)


@router.get("/{score_id}")
def score_range(
    score_id: str,
    start: Optional[datetime] = Query(default=None),
    end: Optional[datetime] = Query(default=None),
    granularity: str = Query(default="daily"),
    db: Session = Depends(get_db),
) -> dict:
    cache_key = f"scores:{score_id}:{start}:{end}:{granularity}"
    cached = cache_get_json(cache_key)
    if cached:
        return cached

    query = db.query(Score).filter(Score.score_id == score_id)
    filters = []
    if start:
        filters.append(Score.ts >= start)
    if end:
        filters.append(Score.ts <= end)
    if filters:
        query = query.filter(and_(*filters))

    rows = query.order_by(Score.ts.asc()).all()
    if not rows:
        raise HTTPException(status_code=404, detail=f"score_id not found: {score_id}")

    data = _aggregate_score_rows(rows, granularity)

    payload = {
        "data": {
            "score_id": score_id,
            "series": data,
        },
        "meta": {
            "source": "computed",
            "delay": "daily",
            "unit": "0-100",
            "version": 1,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    cache_set_json(cache_key, payload, ttl_seconds=90)
    return payload
