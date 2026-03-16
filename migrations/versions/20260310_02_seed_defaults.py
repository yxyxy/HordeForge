"""Seed default pipelines and rules packs.

Revision ID: 20260310_02
Revises: 20260310_01
Create Date: 2026-03-10 00:10:00
"""

from __future__ import annotations

import json
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "20260310_02"
down_revision = "20260310_01"
branch_labels = None
depends_on = None


def _load_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _seed_artifact(
    connection: sa.Connection,
    *,
    run_id: str,
    step_name: str,
    artifact_type: str,
    content: dict,
    tenant_id: str = "default",
) -> None:
    payload = json.dumps(content, ensure_ascii=False)
    size_bytes = len(payload.encode("utf-8"))
    connection.execute(
        sa.text(
            """
            INSERT INTO artifacts (run_id, step_name, artifact_type, content, size_bytes, tenant_id)
            VALUES (:run_id, :step_name, :artifact_type, CAST(:content AS jsonb), :size_bytes, :tenant_id)
            ON CONFLICT DO NOTHING
            """
        ),
        {
            "run_id": run_id,
            "step_name": step_name,
            "artifact_type": artifact_type,
            "content": payload,
            "size_bytes": size_bytes,
            "tenant_id": tenant_id,
        },
    )


def upgrade() -> None:
    connection = op.get_bind()
    base_dir = Path(__file__).resolve().parents[2]
    pipelines_dir = base_dir / "pipelines"
    rules_dir = base_dir / "rules"

    run_id = "seed:default"
    connection.execute(
        sa.text(
            """
            INSERT INTO runs (
                run_id,
                pipeline_name,
                status,
                source,
                correlation_id,
                started_at,
                tenant_id,
                inputs
            ) VALUES (
                :run_id,
                'seed',
                'COMPLETED',
                'migration',
                'seed-default',
                timezone('utc', now()),
                'default',
                '{}'::jsonb
            )
            ON CONFLICT DO NOTHING
            """
        ),
        {"run_id": run_id},
    )

    if pipelines_dir.exists():
        for pipeline_path in pipelines_dir.glob("*.yaml"):
            payload = {
                "name": pipeline_path.stem,
                "path": str(pipeline_path),
                "raw": pipeline_path.read_text(encoding="utf-8"),
            }
            _seed_artifact(
                connection,
                run_id=run_id,
                step_name="seed",
                artifact_type="pipeline_definition",
                content=payload,
            )

    if rules_dir.exists():
        for rule_path in rules_dir.glob("*.md"):
            payload = {
                "name": rule_path.stem,
                "path": str(rule_path),
                "raw": rule_path.read_text(encoding="utf-8"),
            }
            _seed_artifact(
                connection,
                run_id=run_id,
                step_name="seed",
                artifact_type="rules_pack",
                content=payload,
            )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text("DELETE FROM artifacts WHERE run_id = 'seed:default' AND step_name = 'seed'")
    )
    connection.execute(sa.text("DELETE FROM runs WHERE run_id = 'seed:default'"))
