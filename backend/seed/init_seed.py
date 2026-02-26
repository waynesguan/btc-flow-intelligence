from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from db.models import MetricCatalog
from db.session import session_scope


def seed_metric_catalog(db: Session) -> int:
    seed_path = Path(__file__).resolve().parent / "metric_catalog.json"
    with seed_path.open("r", encoding="utf-8") as file:
        rows = json.load(file)

    values = []
    for row in rows:
        values.append(
            {
                "metric_id": row["metric_id"],
                "name": row["name"],
                "dimension": row["dimension"],
                "lead_lag": row["lead_lag"],
                "definition_short": row["definition_short"],
                "definition_pro": row["definition_pro"],
                "calc_spec": row["calc_spec"],
                "source_priority": row["source_priority"],
                "refresh_policy": row["refresh_policy"],
                "failure_modes": row["failure_modes"],
                "chart_spec": row["chart_spec"],
                "version": row.get("version", 1),
                "is_active": row.get("is_active", True),
                "tier": row["tier"],
                "updated_at": datetime.now(timezone.utc),
            }
        )

    stmt = insert(MetricCatalog).values(values)
    upsert = stmt.on_conflict_do_update(
        index_elements=["metric_id"],
        set_={
            "name": stmt.excluded.name,
            "dimension": stmt.excluded.dimension,
            "lead_lag": stmt.excluded.lead_lag,
            "definition_short": stmt.excluded.definition_short,
            "definition_pro": stmt.excluded.definition_pro,
            "calc_spec": stmt.excluded.calc_spec,
            "source_priority": stmt.excluded.source_priority,
            "refresh_policy": stmt.excluded.refresh_policy,
            "failure_modes": stmt.excluded.failure_modes,
            "chart_spec": stmt.excluded.chart_spec,
            "version": stmt.excluded.version,
            "is_active": stmt.excluded.is_active,
            "tier": stmt.excluded.tier,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    result = db.execute(upsert)
    return int(result.rowcount or 0)


def run_seed() -> int:
    with session_scope() as db:
        return seed_metric_catalog(db)


if __name__ == "__main__":
    affected = run_seed()
    print(f"seed_metric_catalog affected={affected}")
