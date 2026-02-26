from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.session import Base

lead_lag_enum = Enum("lead", "coincident", "lag", name="lead_lag_enum")
metric_tier_enum = Enum("must_have", "nice_to_have", name="metric_tier_enum")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RawObservation(Base):
    __tablename__ = "raw_observations"
    __table_args__ = (
        UniqueConstraint("source_id", "dataset", "symbol", "ts", name="uq_raw_observation"),
        Index("ix_raw_source_dataset_ts", "source_id", "dataset", "ts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class NormalizedSeries(Base):
    __tablename__ = "normalized_series"
    __table_args__ = (
        UniqueConstraint("series_id", "ts", name="uq_normalized_series"),
        Index("ix_normalized_series_ts", "series_id", "ts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    series_id: Mapped[str] = mapped_column(String(255), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    value: Mapped[float] = mapped_column(Numeric(24, 8), nullable=False)
    unit: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    quality_flags: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class MetricCatalog(Base):
    __tablename__ = "metric_catalog"

    metric_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    lead_lag: Mapped[str] = mapped_column(lead_lag_enum, nullable=False)
    definition_short: Mapped[str] = mapped_column(Text, nullable=False)
    definition_pro: Mapped[str] = mapped_column(Text, nullable=False)
    calc_spec: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source_priority: Mapped[dict] = mapped_column(JSONB, nullable=False)
    refresh_policy: Mapped[dict] = mapped_column(JSONB, nullable=False)
    failure_modes: Mapped[dict] = mapped_column(JSONB, nullable=False)
    chart_spec: Mapped[dict] = mapped_column(JSONB, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    tier: Mapped[str] = mapped_column(metric_tier_enum, nullable=False)
    available_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class MetricValue(Base):
    __tablename__ = "metric_values"
    __table_args__ = (
        UniqueConstraint("metric_id", "ts", name="uq_metric_values"),
        Index("ix_metric_values_ts", "metric_id", "ts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    metric_id: Mapped[str] = mapped_column(String(128), ForeignKey("metric_catalog.metric_id"), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    value: Mapped[float] = mapped_column(Numeric(24, 8), nullable=False)
    aux: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class Score(Base):
    __tablename__ = "scores"
    __table_args__ = (
        UniqueConstraint("score_id", "ts", name="uq_scores"),
        Index("ix_scores_ts", "score_id", "ts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    score_id: Mapped[str] = mapped_column(String(128), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    value: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    components: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class MarketStage(Base):
    __tablename__ = "market_stage"
    __table_args__ = (UniqueConstraint("ts", name="uq_market_stage_ts"), Index("ix_market_stage_ts", "ts"))

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stage_id: Mapped[int] = mapped_column(Integer, nullable=False)
    stage_name: Mapped[str] = mapped_column(String(128), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    explanation_public: Mapped[str] = mapped_column(Text, nullable=False)
    explanation_pro: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class SourceStatus(Base):
    __tablename__ = "source_status"

    source_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    auth_type: Mapped[str] = mapped_column(String(32), nullable=False)
    latest_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latest_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latest_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_history_depth: Mapped[str] = mapped_column(String(32), nullable=False)
    rate_limit: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class JobRun(Base):
    __tablename__ = "job_runs"
    __table_args__ = (Index("ix_job_runs_started_at", "job_name", "started_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    records_affected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
