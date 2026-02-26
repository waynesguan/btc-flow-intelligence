"""initial schema

Revision ID: 20260226_0001
Revises:
Create Date: 2026-02-26 12:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260226_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum types via raw SQL to avoid SQLAlchemy DDL event conflicts
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE lead_lag_enum AS ENUM ('lead', 'coincident', 'lag');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE metric_tier_enum AS ENUM ('must_have', 'nice_to_have');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    op.create_table(
        "raw_observations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("dataset", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_id", "dataset", "symbol", "ts", name="uq_raw_observation"),
    )
    op.create_index("ix_raw_source_dataset_ts", "raw_observations", ["source_id", "dataset", "ts"])

    op.create_table(
        "normalized_series",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("series_id", sa.String(length=255), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Numeric(24, 8), nullable=False),
        sa.Column("unit", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("quality_flags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.UniqueConstraint("series_id", "ts", name="uq_normalized_series"),
    )
    op.create_index("ix_normalized_series_ts", "normalized_series", ["series_id", "ts"])

    op.create_table(
        "metric_catalog",
        sa.Column("metric_id", sa.String(length=128), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("dimension", sa.Integer(), nullable=False),
        sa.Column("lead_lag", postgresql.ENUM("lead", "coincident", "lag", name="lead_lag_enum", create_type=False), nullable=False),
        sa.Column("definition_short", sa.Text(), nullable=False),
        sa.Column("definition_pro", sa.Text(), nullable=False),
        sa.Column("calc_spec", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_priority", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("refresh_policy", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("failure_modes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("chart_spec", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("tier", postgresql.ENUM("must_have", "nice_to_have", name="metric_tier_enum", create_type=False), nullable=False),
        sa.Column("available_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "metric_values",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("metric_id", sa.String(length=128), sa.ForeignKey("metric_catalog.metric_id"), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Numeric(24, 8), nullable=False),
        sa.Column("aux", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.UniqueConstraint("metric_id", "ts", name="uq_metric_values"),
    )
    op.create_index("ix_metric_values_ts", "metric_values", ["metric_id", "ts"])

    op.create_table(
        "scores",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("score_id", sa.String(length=128), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Numeric(10, 4), nullable=False),
        sa.Column("components", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.UniqueConstraint("score_id", "ts", name="uq_scores"),
    )
    op.create_index("ix_scores_ts", "scores", ["score_id", "ts"])

    op.create_table(
        "market_stage",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stage_id", sa.Integer(), nullable=False),
        sa.Column("stage_name", sa.String(length=128), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("explanation_public", sa.Text(), nullable=False),
        sa.Column("explanation_pro", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.UniqueConstraint("ts", name="uq_market_stage_ts"),
    )
    op.create_index("ix_market_stage_ts", "market_stage", ["ts"])

    op.create_table(
        "source_status",
        sa.Column("source_id", sa.String(length=64), primary_key=True),
        sa.Column("auth_type", sa.String(length=32), nullable=False),
        sa.Column("latest_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latest_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latest_error", sa.Text(), nullable=True),
        sa.Column("max_history_depth", sa.String(length=32), nullable=False),
        sa.Column("rate_limit", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )

    op.create_table(
        "job_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("records_affected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    op.create_index("ix_job_runs_started_at", "job_runs", ["job_name", "started_at"])


def downgrade() -> None:
    op.drop_index("ix_job_runs_started_at", table_name="job_runs")
    op.drop_table("job_runs")

    op.drop_table("source_status")

    op.drop_index("ix_market_stage_ts", table_name="market_stage")
    op.drop_table("market_stage")

    op.drop_index("ix_scores_ts", table_name="scores")
    op.drop_table("scores")

    op.drop_index("ix_metric_values_ts", table_name="metric_values")
    op.drop_table("metric_values")

    op.drop_table("metric_catalog")

    op.drop_index("ix_normalized_series_ts", table_name="normalized_series")
    op.drop_table("normalized_series")

    op.drop_index("ix_raw_source_dataset_ts", table_name="raw_observations")
    op.drop_table("raw_observations")

    op.execute("DROP TYPE IF EXISTS metric_tier_enum")
    op.execute("DROP TYPE IF EXISTS lead_lag_enum")
