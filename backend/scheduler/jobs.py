from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from apscheduler.schedulers.background import BackgroundScheduler

from compute.metrics import compute_metrics
from compute.scoring import compute_scores
from compute.stage import compute_market_stage
from config.settings import get_settings
from db.models import JobRun
from db.session import SessionLocal
from ingest.ingester import run_ingest_all
from normalize.normalizer import run_normalization
from seed.init_seed import seed_metric_catalog

logger = logging.getLogger(__name__)
settings = get_settings()

scheduler = BackgroundScheduler(timezone=settings.scheduler_timezone)


def _to_count(result: Any) -> int:
    if isinstance(result, int):
        return result
    if isinstance(result, dict):
        return int(sum(v for v in result.values() if isinstance(v, int)))
    return 0


def _run_with_log(job_name: str, fn: Callable[[Any], Any]) -> None:
    db = SessionLocal()
    run = JobRun(
        job_name=job_name,
        status="running",
        started_at=datetime.now(timezone.utc),
        finished_at=None,
        records_affected=0,
        errors={},
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        result = fn(db)
        db.commit()
        run.status = "success"
        run.records_affected = _to_count(result)
        run.errors = {}
        logger.info("job_done name=%s records=%s", job_name, run.records_affected)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        run.status = "failed"
        run.errors = {"error": str(exc)}
        logger.exception("job_failed name=%s", job_name)
    finally:
        run.finished_at = datetime.now(timezone.utc)
        db.add(run)
        db.commit()
        db.close()


def job_ingest() -> None:
    _run_with_log("ingest_all", lambda db: run_ingest_all(db=db))


def job_normalize() -> None:
    _run_with_log("normalize_all", lambda db: run_normalization(db=db))


def job_compute_metrics() -> None:
    _run_with_log("compute_metrics", lambda db: compute_metrics(db=db))


def job_compute_scores_stage() -> None:
    def _compute(db: Any) -> int:
        score_count = compute_scores(db=db)
        stage_count = compute_market_stage(db=db)
        return score_count + stage_count

    _run_with_log("compute_scores_stage", _compute)


def run_backfill(start: Optional[datetime] = None, end: Optional[datetime] = None) -> None:
    def _backfill(db: Any) -> int:
        seed_count = seed_metric_catalog(db)
        ingest_count = _to_count(run_ingest_all(db=db, start=start, end=end))
        norm_count = run_normalization(db=db, start=start, end=end)
        metric_count = compute_metrics(db=db, start=start, end=end)
        score_count = compute_scores(db=db, start=start, end=end)
        stage_count = compute_market_stage(db=db, start=start, end=end)
        return seed_count + ingest_count + norm_count + metric_count + score_count + stage_count

    _run_with_log("backfill", _backfill)


def bootstrap_phase1() -> None:
    def _bootstrap(db: Any) -> int:
        seed_count = seed_metric_catalog(db)
        ingest_count = _to_count(run_ingest_all(db=db))
        norm_count = run_normalization(db=db)
        metric_count = compute_metrics(db=db)
        score_count = compute_scores(db=db)
        stage_count = compute_market_stage(db=db)
        return seed_count + ingest_count + norm_count + metric_count + score_count + stage_count

    _run_with_log("bootstrap_phase1", _bootstrap)


def init_scheduler() -> None:
    if scheduler.running:
        return

    scheduler.add_job(job_ingest, "interval", minutes=30, id="ingest_all", replace_existing=True)
    scheduler.add_job(job_normalize, "interval", minutes=30, id="normalize_all", replace_existing=True)
    scheduler.add_job(
        job_compute_metrics,
        "interval",
        minutes=15,
        id="compute_metrics",
        replace_existing=True,
    )
    scheduler.add_job(
        job_compute_scores_stage,
        "interval",
        minutes=15,
        id="compute_scores_stage",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("scheduler_started")


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("scheduler_stopped")
