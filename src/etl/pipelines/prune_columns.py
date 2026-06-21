# src/etl/pipelines/prune_columns.py
#
# Drop columns from Postgres (and optionally BigQuery) that are marked
# 'excluded' in api_field_rename_template.csv.
#
# Workflow
# --------
# 1. Open data/api_field_rename_template.csv
# 2. For any column you no longer want, set its status → excluded
# 3. Run:  python main.py prune-columns [--dry-run] [--also-bigquery]
#
# The command will ALTER TABLE … DROP COLUMN IF EXISTS for every excluded entry.
# It never touches 'approved' or 'pending' rows.

import csv
import os
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import create_engine, inspect, text

from src.config import load_postgres_config, PostgresConfig
from src.utils.logger import get_logger

logger = get_logger(__name__)

_TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "data",
    "api_field_rename_template.csv",
)


def _get_excluded_db_columns() -> Dict[str, List[str]]:
    """
    Read the CSV and return {table_name: [db_col, ...]} for every excluded row.
    The actual DB column name is rename_to if set, else current_database_column.
    """
    table_cols: Dict[str, List[str]] = defaultdict(list)

    if not os.path.exists(_TEMPLATE_PATH):
        return table_cols

    with open(_TEMPLATE_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            status = (row.get("status") or "").strip().lower()
            if status != "excluded":
                continue
            table = (row.get("current_database_table") or "").strip()
            db_col = (row.get("current_database_column") or "").strip()
            rename_to = (row.get("rename_to") or "").strip()
            if not table or not db_col:
                continue
            col = rename_to if rename_to else db_col
            table_cols[table].append(col)

    # Deduplicate within each table
    return {t: list(dict.fromkeys(cols)) for t, cols in table_cols.items()}


def _get_actual_columns(table_name: str, conn_string: str) -> Set[str]:
    """Return the set of column names actually present in the Postgres table."""
    engine = create_engine(conn_string)
    insp = inspect(engine)
    if not insp.has_table(table_name):
        return set()
    return {col["name"] for col in insp.get_columns(table_name)}


def run_prune_columns(
    dry_run: bool = False,
    also_bigquery: bool = False,
    db_config: Optional[PostgresConfig] = None,
    profile: Optional[str] = None,
) -> None:
    """
    Drop all excluded columns from Postgres (and BigQuery if requested).

    Args:
        dry_run:       Print what would be dropped without executing anything.
        also_bigquery: Also drop columns from BigQuery tables.
        db_config:     Postgres config; loaded from env if None.
        profile:       BigQuery profile selector.
    """
    excluded = _get_excluded_db_columns()

    if not excluded:
        logger.info("No excluded columns found in api_field_rename_template.csv")
        return

    total_excluded = sum(len(cols) for cols in excluded.values())
    logger.info(
        "Found excluded columns",
        column_count=total_excluded,
        table_count=len(excluded),
        dry_run=dry_run,
    )

    # --- Postgres ---
    conn_string: Optional[str] = None
    try:
        cfg = db_config or load_postgres_config()
        conn_string = cfg.conn_string
    except Exception as e:
        logger.error("Could not load Postgres config", error=str(e))

    pg_dropped: List[Tuple[str, str]] = []
    pg_not_found: List[Tuple[str, str]] = []

    if conn_string:
        engine = create_engine(conn_string)

        if not dry_run:
            from src.schema.views import VIEW_NAME
            with engine.begin() as conn:
                conn.execute(text(f'DROP VIEW IF EXISTS "{VIEW_NAME}"'))
            logger.info("Dropped view (will be recreated after column drops)", view=VIEW_NAME)

        for table_name, cols in excluded.items():
            actual_cols = _get_actual_columns(table_name, conn_string)
            if not actual_cols:
                logger.warning("Postgres table not found, skipping", table=table_name)
                continue

            for col in cols:
                if col not in actual_cols:
                    pg_not_found.append((table_name, col))
                    continue
                stmt = f'ALTER TABLE "{table_name}" DROP COLUMN IF EXISTS "{col}"'
                if dry_run:
                    logger.info("DRY RUN: would drop column", table=table_name, column=col)
                else:
                    with engine.begin() as conn:
                        conn.execute(text(stmt))
                    logger.info("Dropped column", target="postgres", table=table_name, column=col)
                pg_dropped.append((table_name, col))
    else:
        logger.warning("Skipping Postgres (no connection string available)")

    # --- BigQuery ---
    if also_bigquery:
        try:
            from src.etl.load.bigquery_loader import _build_client
            from src.config import load_bigquery_config

            bq_cfg = load_bigquery_config(profile=profile)
            client = _build_client(
                    bq_cfg.project_id,
                    bq_cfg.credentials_path,
                    bq_cfg.impersonate_service_account,
                )
            dataset = bq_cfg.dataset_id
            project = bq_cfg.project_id

            for table_name, cols in excluded.items():
                table_ref = f"{project}.{dataset}.{table_name}"
                for col in cols:
                    stmt = f"ALTER TABLE `{table_ref}` DROP COLUMN IF EXISTS `{col}`"
                    if dry_run:
                        logger.info("DRY RUN: BigQuery would drop column", table=table_name, column=col)
                    else:
                        try:
                            client.query(stmt).result()
                            logger.info("Dropped column", target="bigquery", table=table_name, column=col)
                        except Exception as e:
                            logger.warning("Could not drop column", target="bigquery", table=table_name, column=col, error=str(e))
        except Exception as e:
            logger.error("BigQuery prune skipped", error=str(e))

    # --- Refresh Postgres view ---
    if conn_string and not dry_run and pg_dropped:
        try:
            from src.etl.load.schema_manager import ensure_views
            ensure_views(create_engine(conn_string))
        except Exception as exc:
            logger.warning("Could not refresh view after prune", error=str(exc))

    # --- Summary ---
    if not dry_run:
        if pg_dropped:
            logger.info("Postgres: columns dropped", count=len(pg_dropped))
        if pg_not_found:
            logger.info(
                "Postgres: columns already absent (no action needed)",
                count=len(pg_not_found),
                columns=[f"{t}.{c}" for t, c in pg_not_found],
            )
    else:
        if pg_dropped:
            logger.info("DRY RUN: would drop columns from Postgres", count=len(pg_dropped))
