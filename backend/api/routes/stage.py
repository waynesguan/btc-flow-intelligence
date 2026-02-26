from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from statistics import mean, median
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_
from sqlalchemy.orm import Session

from api.cache import cache_get_json, cache_set_json
from db.models import MarketStage, Score
from db.session import get_db

router = APIRouter(prefix="/stage", tags=["stage"])


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = int((len(sorted_vals) - 1) * p)
    return sorted_vals[idx]


def _score_distribution(values: list[float]) -> dict:
    if not values:
        return {
            "count": 0,
            "mean": 0.0,
            "median": 0.0,
            "min": 0.0,
            "max": 0.0,
            "p25": 0.0,
            "p75": 0.0,
        }
    return {
        "count": len(values),
        "mean": mean(values),
        "median": median(values),
        "min": min(values),
        "max": max(values),
        "p25": _percentile(values, 0.25),
        "p75": _percentile(values, 0.75),
    }


@router.get("/latest")
def latest_stage(db: Session = Depends(get_db)) -> dict:
    cache_key = "stage:latest"
    cached = cache_get_json(cache_key)
    if cached:
        return cached

    row = db.query(MarketStage).order_by(MarketStage.ts.desc()).first()
    if row is None:
        raise HTTPException(status_code=404, detail="stage not found")
    payload = {
        "data": {
            "ts": row.ts,
            "stage_id": row.stage_id,
            "stage_name": row.stage_name,
            "confidence": row.confidence,
            "explanation_public": row.explanation_public,
            "explanation_pro": row.explanation_pro,
            "evidence": row.evidence,
        },
        "meta": {
            "source": "computed",
            "delay": "daily",
            "unit": None,
            "version": 1,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    cache_set_json(cache_key, payload, ttl_seconds=60)
    return payload


@router.get("")
def stage_history(
    start: Optional[datetime] = Query(default=None),
    end: Optional[datetime] = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    query = db.query(MarketStage)
    filters = []
    if start:
        filters.append(MarketStage.ts >= start)
    if end:
        filters.append(MarketStage.ts <= end)
    if filters:
        query = query.filter(and_(*filters))

    rows = query.order_by(MarketStage.ts.asc()).all()
    data = [
        {
            "ts": row.ts,
            "stage_id": row.stage_id,
            "stage_name": row.stage_name,
            "confidence": row.confidence,
        }
        for row in rows
    ]

    return {
        "data": data,
        "meta": {
            "source": "computed",
            "delay": "daily",
            "unit": None,
            "version": 1,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/explain")
def stage_explain(
    ts: datetime = Query(...),
    db: Session = Depends(get_db),
) -> dict:
    row = db.query(MarketStage).filter(MarketStage.ts == ts).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"stage not found for ts={ts.isoformat()}")

    return {
        "data": {
            "ts": row.ts,
            "stage_id": row.stage_id,
            "stage_name": row.stage_name,
            "confidence": row.confidence,
            "explanation_public": row.explanation_public,
            "explanation_pro": row.explanation_pro,
            "evidence": row.evidence,
        },
        "meta": {
            "source": "computed",
            "delay": "daily",
            "unit": None,
            "version": 1,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/stats")
def stage_stats(
    start: Optional[datetime] = Query(default=None),
    end: Optional[datetime] = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    cache_key = f"stage:stats:{start}:{end}"
    cached = cache_get_json(cache_key)
    if cached:
        return cached

    stage_query = db.query(MarketStage)
    score_query = db.query(Score)

    filters_stage = []
    filters_score = []
    if start:
        filters_stage.append(MarketStage.ts >= start)
        filters_score.append(Score.ts >= start)
    if end:
        filters_stage.append(MarketStage.ts <= end)
        filters_score.append(Score.ts <= end)

    if filters_stage:
        stage_query = stage_query.filter(and_(*filters_stage))
    if filters_score:
        score_query = score_query.filter(and_(*filters_score))

    stage_rows = stage_query.order_by(MarketStage.ts.asc()).all()
    if not stage_rows:
        raise HTTPException(status_code=404, detail="stage stats not available")

    score_rows = score_query.filter(Score.score_id.in_(["capital_inflow_score", "structure_risk_score"]))\
        .order_by(Score.ts.asc())\
        .all()

    stage_counter = Counter((row.stage_id, row.stage_name) for row in stage_rows)
    switches = 0
    for idx in range(1, len(stage_rows)):
        if stage_rows[idx].stage_id != stage_rows[idx - 1].stage_id:
            switches += 1

    cap_series = [float(row.value) for row in score_rows if row.score_id == "capital_inflow_score"]
    risk_series = [float(row.value) for row in score_rows if row.score_id == "structure_risk_score"]

    cap_points = [row for row in score_rows if row.score_id == "capital_inflow_score"]
    risk_map = {row.ts: float(row.value) for row in score_rows if row.score_id == "structure_risk_score"}
    stage_map = {row.ts: row.stage_id for row in stage_rows}

    overlays: list[dict] = []
    window = 90
    labels = ["current_cycle", "previous_cycle_1", "previous_cycle_2"]
    for idx, label in enumerate(labels):
        end_pos = len(cap_points) - 1 - idx * window
        if end_pos < 0:
            continue
        start_pos = max(0, end_pos - window + 1)
        segment = cap_points[start_pos : end_pos + 1]
        overlays.append(
            {
                "label": label,
                "start_ts": segment[0].ts,
                "end_ts": segment[-1].ts,
                "points": [
                    {
                        "step": step,
                        "capital": float(point.value),
                        "risk": risk_map.get(point.ts),
                        "stage_id": stage_map.get(point.ts),
                    }
                    for step, point in enumerate(segment, start=1)
                ],
            }
        )

    payload = {
        "data": {
            "stage_days": [
                {
                    "stage_id": stage_id,
                    "stage_name": stage_name,
                    "days": days,
                }
                for (stage_id, stage_name), days in sorted(stage_counter.items(), key=lambda x: x[0][0])
            ],
            "stage_switches": switches,
            "score_distribution": {
                "capital_inflow_score": _score_distribution(cap_series),
                "structure_risk_score": _score_distribution(risk_series),
            },
            "multi_cycle_overlay": overlays,
        },
        "meta": {
            "source": "computed",
            "delay": "daily",
            "unit": None,
            "version": 1,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    cache_set_json(cache_key, payload, ttl_seconds=300)
    return payload
