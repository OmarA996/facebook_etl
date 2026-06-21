from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import create_engine, inspect, text

from src.config import PostgresConfig, load_postgres_config
from src.schema.tables import TABLE_SCHEMAS
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _etl_tables(engine) -> list[str]:
    """Return ETL tables that actually exist in the public schema, sorted."""
    insp = inspect(engine)
    declared = set(TABLE_SCHEMAS.keys())
    actual = set(insp.get_table_names(schema="public"))
    return sorted(declared & actual)


def _timestamp_schema() -> str:
    return "backup_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def run_backup(
    schema_name: Optional[str] = None,
    db_config: Optional[PostgresConfig] = None,
    profile: Optional[str] = None,
) -> str:
    """
    Copy every ETL table into a new backup schema.
    Returns the schema name so callers can print it for the user.
    """
    cfg = db_config or load_postgres_config(profile)
    engine = create_engine(cfg.conn_string)
    schema = schema_name or _timestamp_schema()
    tables = _etl_tables(engine)

    if not tables:
        logger.warning("No ETL tables found in public schema, nothing to back up")
        return schema

    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))

    logger.info("Starting backup", table_count=len(tables), schema=schema)
    for table in tables:
        with engine.begin() as conn:
            conn.execute(text(
                f'CREATE TABLE "{schema}"."{table}" AS '
                f'SELECT * FROM public."{table}"'
            ))
        logger.info("Table copied", source=f"public.{table}", dest=f"{schema}.{table}")

    logger.info("Backup complete", schema=schema)
    return schema


def run_list_backups(
    db_config: Optional[PostgresConfig] = None,
    profile: Optional[str] = None,
) -> None:
    cfg = db_config or load_postgres_config(profile)
    engine = create_engine(cfg.conn_string)

    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name LIKE 'backup_%' ORDER BY schema_name DESC"
        )).fetchall()

    if not rows:
        logger.info("No backup schemas found")
        return

    logger.info("Backup schemas found", count=len(rows))
    for (schema,) in rows:
        with engine.connect() as conn:
            count = conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = :s"
            ), {"s": schema}).scalar()
        logger.info("Backup schema", schema=schema, tables=count)


def run_restore(
    schema_name: str,
    dry_run: bool = False,
    db_config: Optional[PostgresConfig] = None,
    profile: Optional[str] = None,
) -> None:
    """
    Restore public tables from a backup schema.
    All DROP + CREATE statements run inside a single transaction -- if anything
    fails, the entire restore is rolled back and the public schema is untouched.
    """
    cfg = db_config or load_postgres_config(profile)
    engine = create_engine(cfg.conn_string)

    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = :s ORDER BY table_name"
        ), {"s": schema_name}).fetchall()

    if not rows:
        logger.warning("Schema not found or empty", schema=schema_name)
        return

    tables = [r[0] for r in rows]
    logger.info("Starting restore", table_count=len(tables), schema=schema_name, dry_run=dry_run)

    if dry_run:
        for table in tables:
            logger.info(
                "DRY RUN: would restore table",
                table=table,
                source=f"{schema_name}.{table}",
                dest=f"public.{table}",
            )
        return

    with engine.begin() as conn:
        for table in tables:
            conn.execute(text(f'DROP TABLE IF EXISTS public."{table}" CASCADE'))
            conn.execute(text(
                f'CREATE TABLE public."{table}" AS '
                f'SELECT * FROM "{schema_name}"."{table}"'
            ))
            logger.info("Table restored", source=f"{schema_name}.{table}", dest=f"public.{table}")

    logger.info(
        "Restore complete",
        schema=schema_name,
        note="Unique indexes not restored; re-run any pipeline to re-apply them",
    )


def run_drop_backup(
    schema_name: str,
    db_config: Optional[PostgresConfig] = None,
    profile: Optional[str] = None,
) -> None:
    """Delete a backup schema to free space once you no longer need it."""
    cfg = db_config or load_postgres_config(profile)
    engine = create_engine(cfg.conn_string)
    with engine.begin() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
    logger.info("Dropped backup schema", schema=schema_name)
