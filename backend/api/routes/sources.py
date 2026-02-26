from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db.models import SourceStatus
from db.session import get_db
from sources.registry import get_active_sources, get_all_sources

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("/status")
def get_sources_status(db: Session = Depends(get_db)) -> dict:
    db_rows = {row.source_id: row for row in db.query(SourceStatus).all()}
    active_sources = {source.source_id for source in get_active_sources()}

    data = []
    for adapter in get_all_sources():
        row = db_rows.get(adapter.source_id)
        data.append(
            {
                "source_id": adapter.source_id,
                "auth_type": adapter.auth_type,
                "latest_success_at": row.latest_success_at if row else None,
                "latest_error_at": row.latest_error_at if row else None,
                "latest_error": row.latest_error if row else None,
                "max_history_depth": adapter.max_history_depth,
                "rate_limit": adapter.rate_limit,
                "enabled": adapter.source_id in active_sources,
            }
        )

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
