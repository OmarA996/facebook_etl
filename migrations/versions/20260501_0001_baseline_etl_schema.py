"""Baseline ETL schema.

Materializes every table declared in src.schema.tables.TABLE_SCHEMAS plus the
unique indexes from src.schema.unique_keys.UNIQUE_KEYS, and creates the
operational tables introduced by the production hardening work
(etl_run_log, etl_insights_checkpoint).

This migration is idempotent: tables and indexes are created only when they
do not already exist, so it is safe to run against an existing database that
was bootstrapped by schema_manager.py.

Revision ID: 20260501_0001
Revises:
Create Date: 2026-05-01
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

from src.schema.tables import TABLE_SCHEMAS
from src.schema.unique_keys import UNIQUE_KEYS
from src.utils.names import shorten_from_left


revision = "20260501_0001"
down_revision = None
branch_labels = None
depends_on = None


_OPERATIONAL_TABLES = {
    "etl_run_log": {
        "run_id": "TEXT PRIMARY KEY",
        "command": "TEXT NOT NULL",
        "profile": "TEXT",
        "status": "TEXT NOT NULL",
        "started_at": "TIMESTAMPTZ NOT NULL",
        "ended_at": "TIMESTAMPTZ",
        "duration_seconds": "NUMERIC",
        "rows_loaded": "BIGINT",
        "error_message": "TEXT",
        "host": "TEXT",
    },
    "etl_insights_checkpoint": {
        "profile": "TEXT NOT NULL",
        "level": "TEXT NOT NULL",
        "breakdowns_key": "TEXT NOT NULL",
        "since": "DATE NOT NULL",
        "until": "DATE NOT NULL",
        "rows_loaded": "BIGINT",
        "completed_at": "TIMESTAMPTZ NOT NULL",
    },
}

_OPERATIONAL_UNIQUE_KEYS = {
    "etl_insights_checkpoint": ["profile", "level", "breakdowns_key", "since", "until"],
}


def _create_table_if_missing(table_name: str, schema: dict) -> None:
    cols = ", ".join(f"{col} {ctype}" for col, ctype in schema.items())
    op.execute(text(f"CREATE TABLE IF NOT EXISTS {table_name} ({cols})"))


def _create_unique_index(table_name: str, key_cols: list[str]) -> None:
    if not key_cols:
        return
    idx_name = shorten_from_left(f"uq_{table_name}_{'_'.join(key_cols)}")
    cols_clause = ", ".join(key_cols)
    op.execute(
        text(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {idx_name} "
            f"ON {table_name} ({cols_clause})"
        )
    )


def upgrade() -> None:
    for table_name, schema in TABLE_SCHEMAS.items():
        _create_table_if_missing(table_name, schema)

    for table_name, key_cols in UNIQUE_KEYS.items():
        _create_unique_index(table_name, key_cols)

    for table_name, schema in _OPERATIONAL_TABLES.items():
        _create_table_if_missing(table_name, schema)

    for table_name, key_cols in _OPERATIONAL_UNIQUE_KEYS.items():
        _create_unique_index(table_name, key_cols)

    op.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_etl_run_log_started_at "
            "ON etl_run_log (started_at DESC)"
        )
    )
    op.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_etl_run_log_command_status "
            "ON etl_run_log (command, status)"
        )
    )


def downgrade() -> None:
    # Intentional no-op. Dropping the ETL schema would destroy production
    # data; use clean-db / drop-backup commands for targeted teardown.
    pass
