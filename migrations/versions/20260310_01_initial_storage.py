"""Initial storage schema.

Revision ID: 20260310_01
Revises: 
Create Date: 2026-03-10 00:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

try:
    from sqlalchemy.dialects.postgresql import JSONB
except ImportError:  # pragma: no cover - fallback for non-Postgres SQLAlchemy builds
    JSONB = sa.JSON


revision = "20260310_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("run_id", sa.String(length=128), primary_key=True),
        sa.Column("pipeline_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="unknown"),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("repository_full_name", sa.String(length=256), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", JSONB, nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("inputs", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("override_state", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("timezone('utc', now())"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("timezone('utc', now())"),
        ),
    )
    op.create_index("ix_runs_pipeline_name", "runs", ["pipeline_name"])
    op.create_index("ix_runs_status", "runs", ["status"])
    op.create_index("ix_runs_tenant_id", "runs", ["tenant_id"])
    op.create_index("ix_runs_correlation_id", "runs", ["correlation_id"])
    op.create_index("ix_runs_idempotency_key", "runs", ["idempotency_key"])

    op.create_table(
        "step_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("step_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("timezone('utc', now())"),
        ),
        sa.ForeignKeyConstraint(["run_id"], ["runs.run_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("run_id", "tenant_id", "step_name"),
    )
    op.create_index("ix_step_logs_run_id", "step_logs", ["run_id"])
    op.create_index("ix_step_logs_status", "step_logs", ["status"])
    op.create_index("ix_step_logs_tenant_id", "step_logs", ["tenant_id"])

    op.create_table(
        "artifacts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("step_name", sa.String(length=128), nullable=False),
        sa.Column("artifact_type", sa.String(length=128), nullable=False),
        sa.Column("content", JSONB, nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("timezone('utc', now())"),
        ),
        sa.ForeignKeyConstraint(["run_id"], ["runs.run_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_artifacts_run_id", "artifacts", ["run_id"])
    op.create_index("ix_artifacts_artifact_type", "artifacts", ["artifact_type"])
    op.create_index("ix_artifacts_tenant_id", "artifacts", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_artifacts_tenant_id", table_name="artifacts")
    op.drop_index("ix_artifacts_artifact_type", table_name="artifacts")
    op.drop_index("ix_artifacts_run_id", table_name="artifacts")
    op.drop_table("artifacts")

    op.drop_index("ix_step_logs_tenant_id", table_name="step_logs")
    op.drop_index("ix_step_logs_status", table_name="step_logs")
    op.drop_index("ix_step_logs_run_id", table_name="step_logs")
    op.drop_table("step_logs")

    op.drop_index("ix_runs_idempotency_key", table_name="runs")
    op.drop_index("ix_runs_correlation_id", table_name="runs")
    op.drop_index("ix_runs_tenant_id", table_name="runs")
    op.drop_index("ix_runs_status", table_name="runs")
    op.drop_index("ix_runs_pipeline_name", table_name="runs")
    op.drop_table("runs")
