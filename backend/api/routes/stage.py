from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_
from sqlalchemy.orm import Session

from api.cache import cache_get_json, cache_set_json
from db.models import MarketStage
from db.session import get_db

router = APIRouter(prefix="/stage", tags=["stage"])


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
