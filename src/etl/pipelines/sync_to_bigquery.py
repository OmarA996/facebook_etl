from __future__ import annotations

from typing import Optional

from src.config import PostgresConfig
from src.etl.load.bigquery_loader import (
    bigquery_table_exists,
    ensure_bigquery_views,
    list_tables as list_bigquery_tables,
    save_df_to_bigquery,
    truncate_table,
)
from src.etl.load.postgres_loader import iterate_table_chunks, list_tables as list_postgres_tables, relation_exists, table_exists
from src.utils.logger import get_logger

logger = get_logger(__name__)


SYNC_TABLE_OPTIONS = {
    "fact_meta_delivery_ad": {
        "mode": "merge",
        "merge_keys": ["ad_id", "date_start"],
        "partition_field": "date_start",
        "cluster_fields": ["account_id", "campaign_id", "adset_id", "ad_id"],
    },
    "fact_meta_ads_combined": {
        "mode": "truncate",
    },
    "dim_goals": {
        "mode": "truncate",
    },
    "vw_meta_ads_full": {
        "mode": "truncate",
    },
}


def resolve_sync_options(table_name: str, mode: str = "auto") -> dict:
    mode = mode.lower()
    if mode not in {"auto", "merge", "truncate", "append"}:
        raise ValueError(f"Unsupported sync mode: {mode}")

    defaults = SYNC_TABLE_OPTIONS.get(table_name, {})
    if mode == "auto":
        effective_mode = defaults.get("mode", "truncate")
    else:
        effective_mode = mode

    if effective_mode == "merge" and not defaults.get("merge_keys"):
        raise ValueError(
            f"No merge strategy configured for table '{table_name}'. "
            "Use --mode truncate or --mode append instead."
        )

    return {
        "mode": effective_mode,
        "merge_keys": defaults.get("merge_keys"),
        "partition_field": defaults.get("partition_field"),
        "cluster_fields": defaults.get("cluster_fields"),
        "exclude_columns": defaults.get("exclude_columns") or set(),
    }


def _validate_sync_targets(
    table_names: list[str],
    *,
    conn_string: str,
    profile: str | None = None,
    bq_table_name: Optional[str] = None,
    create_if_missing: bool = False,
) -> list[tuple[str, str, dict]]:
    targets: list[tuple[str, str, dict]] = []
    for source_table in table_names:
        target_table = bq_table_name if bq_table_name and len(table_names) == 1 else source_table
        if not relation_exists(source_table, conn_string=conn_string):
            raise ValueError(f"Source PostgreSQL table or view does not exist: {source_table}")
        if not create_if_missing and not bigquery_table_exists(target_table, profile=profile):
            raise ValueError(f"Target BigQuery table does not exist: {target_table}")
        targets.append((source_table, target_table, {}))
    return targets


def resolve_sync_table_names(
    table_names: list[str],
    *,
    conn_string: str,
    profile: str | None = None,
    create_if_missing: bool = False,
) -> list[str]:
    from src.schema.tables import TABLE_SCHEMAS

    normalized = [str(name).strip() for name in table_names if str(name).strip()]
    if not normalized:
        raise ValueError("Provide at least one PostgreSQL table to sync.")

    if len(normalized) == 1 and normalized[0].lower() == "all":
        postgres_tables = set(list_postgres_tables(conn_string=conn_string))
        if create_if_missing:
            # Include all ETL tables that exist in Postgres, not just those already in BQ
            etl_tables = set(TABLE_SCHEMAS.keys())
            selected_tables = sorted(postgres_tables & etl_tables)
            if not selected_tables:
                raise ValueError("No ETL tables found in PostgreSQL to sync.")
        else:
            bigquery_tables = set(list_bigquery_tables(profile=profile))
            selected_tables = sorted(postgres_tables & bigquery_tables)
            if not selected_tables:
                raise ValueError("No overlapping PostgreSQL and BigQuery tables were found to sync.")
        logger.info(
            "Resolved sync-to-bigquery all",
            postgres_tables=sorted(postgres_tables),
            create_if_missing=create_if_missing,
            selected_tables=selected_tables,
        )
        return selected_tables

    return normalized


def run_sync_to_bigquery(
    *,
    table_names: list[str],
    db_config: PostgresConfig,
    profile: Optional[str] = None,
    mode: str = "auto",
    chunk_size: int = 50000,
    bq_table_name: Optional[str] = None,
    create_if_missing: bool = False,
) -> None:
    resolved_table_names = resolve_sync_table_names(
        table_names,
        conn_string=db_config.conn_string,
        profile=profile,
        create_if_missing=create_if_missing,
    )
    if bq_table_name and len(resolved_table_names) != 1:
        raise ValueError("--bq-table can only be used when syncing a single source table.")
    if chunk_size < 1:
        raise ValueError("chunk_size must be >= 1")

    validations = _validate_sync_targets(
        resolved_table_names,
        conn_string=db_config.conn_string,
        profile=profile,
        bq_table_name=bq_table_name,
        create_if_missing=create_if_missing,
    )

    for source_table, target_table, _ in validations:
        sync_options = resolve_sync_options(source_table, mode=mode)
        logger.info(
            "Starting PostgreSQL to BigQuery sync",
            source_table=source_table,
            target_table=target_table,
            mode=sync_options["mode"],
            chunk_size=chunk_size,
        )

        exclude_cols: set[str] = sync_options.get("exclude_columns") or set()
        chunk_count = 0
        total_rows = 0
        for chunk in iterate_table_chunks(
            source_table,
            conn_string=db_config.conn_string,
            chunk_size=chunk_size,
        ):
            chunk_count += 1
            total_rows += len(chunk)
            if exclude_cols:
                chunk = chunk.drop(columns=[c for c in exclude_cols if c in chunk.columns])
            require_existing = not create_if_missing
            if sync_options["mode"] == "merge":
                save_df_to_bigquery(
                    chunk,
                    table_name=target_table,
                    profile=profile,
                    merge_keys=sync_options["merge_keys"],
                    partition_field=sync_options["partition_field"],
                    cluster_fields=sync_options["cluster_fields"],
                    require_existing_table=require_existing,
                )
            else:
                write_disposition = "WRITE_APPEND"
                if sync_options["mode"] == "truncate" and chunk_count == 1:
                    write_disposition = "WRITE_TRUNCATE"

                save_df_to_bigquery(
                    chunk,
                    table_name=target_table,
                    profile=profile,
                    write_disposition=write_disposition,
                    require_existing_table=require_existing,
                )

        if chunk_count == 0 and sync_options["mode"] == "truncate":
            truncate_table(target_table)

        logger.info(
            "PostgreSQL to BigQuery sync completed",
            source_table=source_table,
            target_table=target_table,
            mode=sync_options["mode"],
            chunks=chunk_count,
            rows=total_rows,
        )

    ensure_bigquery_views(profile=profile)
