from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db.models import SourceStatus
from db.session import get_db

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("/status")
def get_sources_status(db: Session = Depends(get_db)) -> dict:
    rows = db.query(SourceStatus).order_by(SourceStatus.source_id.asc()).all()
    data = [
        {
            "source_id": row.source_id,
            "auth_type": row.auth_type,
            "latest_success_at": row.latest_success_at,
            "latest_error_at": row.latest_error_at,
            "latest_error": row.latest_error,
            "max_history_depth": row.max_history_depth,
            "rate_limit": row.rate_limit,
        }
        for row in rows
    ]
    return {
        "data": data,
        "meta": {
            "source": "internal",
            "delay": "near-real-time",
            "unit": None,
            "version": 1,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
