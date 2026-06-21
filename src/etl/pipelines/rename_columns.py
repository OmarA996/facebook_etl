from __future__ import annotations

import csv
import os
import re
from collections import defaultdict
from typing import Optional

_VALID_IDENTIFIER = re.compile(r'^[a-z_][a-z0-9_]*$', re.IGNORECASE)

from sqlalchemy import create_engine, inspect, text

from src.config import PostgresConfig, load_postgres_config
from src.etl.pipelines.backup_restore import run_backup
from src.utils.logger import get_logger

logger = get_logger(__name__)

_TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "data",
    "api_field_rename_template.csv",
)


def _get_rename_plan() -> dict[str, list[tuple[str, str]]]:
    """
    Read CSV and return {table: [(old_col, new_col), ...]} for every approved
    row where rename_to is set and differs from current_database_column.
    """
    plan: dict[str, list[tuple[str, str]]] = defaultdict(list)

    if not os.path.exists(_TEMPLATE_PATH):
        logger.warning("api_field_rename_template.csv not found")
        return plan

    seen: set[tuple[str, str, str]] = set()
    with open(_TEMPLATE_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            status   = (row.get("status")                  or "").strip().lower()
            if status != "approved":
                continue
            table    = (row.get("current_database_table")  or "").strip()
            old_col  = (row.get("current_database_column") or "").strip()
            new_col  = (row.get("rename_to")               or "").strip()

            if not table or not old_col or not new_col:
                continue
            if old_col == new_col:
                continue
            if not _VALID_IDENTIFIER.match(new_col):
                logger.warning(
                    "Skipping rename: rename_to looks like a note, not a column name",
                    table=table,
                    column=old_col,
                    rename_to=new_col[:60],
                )
                continue

            key = (table, old_col, new_col)
            if key in seen:
                continue
            seen.add(key)
            plan[table].append((old_col, new_col))

    return dict(plan)


def run_migrate_renames(
    dry_run: bool = False,
    also_bigquery: bool = False,
    backup: bool = False,
    db_config: Optional[PostgresConfig] = None,
    profile: Optional[str] = None,
) -> None:
    plan = _get_rename_plan()

    if not plan:
        logger.info("Nothing to rename, no approved rename_to entries found")
        return

    total = sum(len(pairs) for pairs in plan.values())
    logger.info("Renames planned", total=total, tables=len(plan), dry_run=dry_run)

    if backup and not dry_run:
        schema = run_backup(db_config=db_config, profile=profile)
        logger.info("Backup created before rename", schema=schema)

    # ── Postgres ──────────────────────────────────────────────────────────────
    try:
        cfg = db_config or load_postgres_config(profile)
        conn_string = cfg.conn_string
    except Exception as exc:
        logger.error("Could not load Postgres config", error=str(exc))
        conn_string = None

    pg_renamed: list[str] = []
    pg_skipped: list[str] = []
    pg_missing: list[str] = []

    if conn_string:
        engine = create_engine(conn_string)

        if not dry_run:
            from src.schema.views import VIEW_NAME
            with engine.begin() as conn:
                conn.execute(text(f'DROP VIEW IF EXISTS "{VIEW_NAME}"'))
            logger.info("Dropped view (will be recreated after renames)", view=VIEW_NAME)

        insp = inspect(engine)

        for table, pairs in plan.items():
            if not insp.has_table(table):
                logger.warning("Postgres table not found, skipping", table=table)
                continue

            actual = {col["name"] for col in insp.get_columns(table)}

            for old_col, new_col in pairs:
                label = f"{table}.{old_col} -> {new_col}"

                if new_col in actual and old_col not in actual:
                    pg_skipped.append(label)
                    continue

                if old_col not in actual and new_col not in actual:
                    pg_missing.append(label)
                    continue

                stmt = f'ALTER TABLE "{table}" RENAME COLUMN "{old_col}" TO "{new_col}"'
                if dry_run:
                    logger.info("DRY RUN: would rename column", table=table, old=old_col, new=new_col)
                else:
                    with engine.begin() as conn:
                        conn.execute(text(stmt))
                    logger.info("Renamed column", target="postgres", table=table, old=old_col, new=new_col)
                pg_renamed.append(label)
    else:
        logger.warning("Skipping Postgres (no connection available)")

    # ── BigQuery ──────────────────────────────────────────────────────────────
    bq_renamed: list[str] = []
    bq_skipped: list[str] = []
    bq_missing: list[str] = []

    if also_bigquery:
        try:
            from src.config import load_bigquery_config
            from src.etl.load.bigquery_loader import _build_client
            from google.api_core.exceptions import NotFound

            bq_cfg = load_bigquery_config(profile=profile)
            client = _build_client(
                bq_cfg.project_id,
                bq_cfg.credentials_path,
                bq_cfg.impersonate_service_account,
            )
            project = bq_cfg.project_id
            dataset = bq_cfg.dataset_id

            for table, pairs in plan.items():
                table_id = f"{project}.{dataset}.{table}"
                try:
                    bq_table = client.get_table(table_id)
                except NotFound:
                    logger.warning("BigQuery table not found, skipping", table_id=table_id)
                    continue

                actual = {field.name for field in bq_table.schema}

                for old_col, new_col in pairs:
                    label = f"{table}.{old_col} -> {new_col}"

                    if new_col in actual and old_col not in actual:
                        bq_skipped.append(label)
                        continue

                    if old_col not in actual and new_col not in actual:
                        bq_missing.append(label)
                        continue

                    stmt = (
                        f"ALTER TABLE `{table_id}` "
                        f"RENAME COLUMN `{old_col}` TO `{new_col}`"
                    )
                    if dry_run:
                        logger.info("DRY RUN: BigQuery would rename column", table=table, old=old_col, new=new_col)
                    else:
                        try:
                            client.query(stmt).result()
                            logger.info("Renamed column", target="bigquery", table=table, old=old_col, new=new_col)
                        except Exception as exc:
                            logger.error("Failed to rename column", target="bigquery", table=table, old=old_col, new=new_col, error=str(exc))
                            continue
                    bq_renamed.append(label)

        except Exception as exc:
            logger.error("BigQuery step skipped", error=str(exc))

    # ── Refresh Postgres view ─────────────────────────────────────────────────
    if conn_string and not dry_run and pg_renamed:
        try:
            from src.etl.load.schema_manager import ensure_views
            ensure_views(create_engine(conn_string))
        except Exception as exc:
            logger.warning("Could not refresh view after rename", error=str(exc))

    # ── Summary ───────────────────────────────────────────────────────────────
    action = "would rename" if dry_run else "renamed"

    if pg_renamed:
        logger.info(f"Postgres: {action} columns", count=len(pg_renamed))
    if pg_skipped:
        logger.info("Postgres: columns already renamed (skipped)", count=len(pg_skipped), columns=pg_skipped)
    if pg_missing:
        logger.info("Postgres: columns not found in DB (never loaded?)", count=len(pg_missing), columns=pg_missing)
    if also_bigquery:
        if bq_renamed:
            logger.info(f"BigQuery: {action} columns", count=len(bq_renamed))
        if bq_skipped:
            logger.info("BigQuery: columns already renamed (skipped)", count=len(bq_skipped), columns=bq_skipped)
        if bq_missing:
            logger.info("BigQuery: columns not found (never loaded?)", count=len(bq_missing), columns=bq_missing)
