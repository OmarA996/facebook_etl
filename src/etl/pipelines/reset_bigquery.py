from __future__ import annotations

from typing import Optional

from src.config import PostgresConfig
from src.etl.load.bigquery_loader import delete_table, list_tables as list_bq_tables
from src.etl.pipelines.materialize_combined import COMBINED_TABLE, run_materialize_combined
from src.etl.pipelines.sync_to_bigquery import run_sync_to_bigquery
from src.utils.logger import get_logger

logger = get_logger(__name__)


def run_reset_bigquery(
    *,
    db_config: PostgresConfig,
    profile: Optional[str] = None,
) -> None:
    # 1. Drop every table and view in the BigQuery dataset
    existing = list_bq_tables(profile=profile)
    if existing:
        logger.info("Dropping all BigQuery tables", count=len(existing), tables=existing)
        for table_name in existing:
            delete_table(table_name, profile=profile)
    else:
        logger.info("BigQuery dataset is already empty")

    # 2. Sync all individual Postgres ETL tables to BigQuery
    logger.info("Syncing all Postgres tables to BigQuery")
    run_sync_to_bigquery(
        table_names=["all"],
        db_config=db_config,
        profile=profile,
        mode="truncate",
        create_if_missing=True,
    )

    # 3. Materialize and sync the combined table
    logger.info("Materializing and syncing combined table", table=COMBINED_TABLE)
    run_materialize_combined(
        db_config=db_config,
        to_bigquery=True,
        profile=profile,
    )

    logger.info("BigQuery reset complete", combined_table=COMBINED_TABLE)
