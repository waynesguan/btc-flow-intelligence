from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from db.models import RawObservation, SourceStatus
from sources.base import SourceAdapter, SourceObservation
from sources.registry import get_active_sources, get_all_sources

logger = logging.getLogger(__name__)


def _upsert_source_status(db: Session, source: SourceAdapter, error: Optional[str] = None) -> None:
    now = datetime.now(timezone.utc)
    values = {
        "source_id": source.source_id,
        "auth_type": source.auth_type,
        "max_history_depth": source.max_history_depth,
        "rate_limit": source.rate_limit,
        "latest_success_at": None if error else now,
        "latest_error_at": now if error else None,
        "latest_error": error,
    }

    stmt = insert(SourceStatus).values(values)
    update_fields = {
        "auth_type": source.auth_type,
        "max_history_depth": source.max_history_depth,
        "rate_limit": source.rate_limit,
    }
    if error:
        update_fields["latest_error_at"] = now
        update_fields["latest_error"] = error
    else:
        update_fields["latest_success_at"] = now
        update_fields["latest_error"] = None

    db.execute(stmt.on_conflict_do_update(index_elements=["source_id"], set_=update_fields))


def upsert_raw_observations(db: Session, rows: list[SourceObservation]) -> int:
    if not rows:
        return 0

    values = [
        {
            "source_id": item.source_id,
            "dataset": item.dataset,
            "symbol": item.symbol,
            "ts": item.ts,
            "payload": item.payload,
            "ingested_at": datetime.now(timezone.utc),
        }
        for item in rows
    ]

    stmt = insert(RawObservation).values(values)
    upsert = stmt.on_conflict_do_update(
        index_elements=["source_id", "dataset", "symbol", "ts"],
        set_={
            "payload": stmt.excluded.payload,
            "ingested_at": datetime.now(timezone.utc),
        },
    )
    result = db.execute(upsert)
    return int(result.rowcount or 0)


def run_ingest_for_source(
    db: Session,
    source: SourceAdapter,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> int:
    affected = 0
    for dataset in source.datasets:
        rows = source.fetch(dataset=dataset, start=start, end=end)
        affected += upsert_raw_observations(db=db, rows=rows)
    _upsert_source_status(db=db, source=source)
    return affected


def _ensure_source_status_rows(db: Session) -> None:
    for source in get_all_sources():
        db.execute(
            insert(SourceStatus)
            .values(
                {
                    "source_id": source.source_id,
                    "auth_type": source.auth_type,
                    "max_history_depth": source.max_history_depth,
                    "rate_limit": source.rate_limit,
                    "latest_success_at": None,
                    "latest_error_at": None,
                    "latest_error": None,
                }
            )
            .on_conflict_do_nothing(index_elements=["source_id"])
        )


def run_ingest_all(
    db: Session,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> dict[str, int]:
    _ensure_source_status_rows(db)

    results: dict[str, int] = {}
    for source in get_active_sources():
        try:
            count = run_ingest_for_source(db=db, source=source, start=start, end=end)
            results[source.source_id] = count
        except Exception as exc:  # noqa: BLE001
            logger.exception("ingest_failed source=%s", source.source_id)
            _upsert_source_status(db=db, source=source, error=str(exc))
            results[source.source_id] = 0
    return results
