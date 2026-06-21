from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from src.clients.graph_client import GraphAPIError
from src.config import PostgresConfig, load_ad_account_ids
from src.etl.extract.meta_insights import fetch_insights
from src.etl.load.checkpoints import fetch_completed, mark_completed
from src.etl.load.csv_loader import save_df_to_csv
from src.etl.load.postgres_loader import save_df_to_postgres_upsert
from src.etl.transform.meta_insights import get_insights_table_name, normalize_insights
from src.schema.unique_keys import UNIQUE_KEYS
from src.utils.logger import get_logger

logger = get_logger(__name__)

RATE_LIMIT_SLEEP_SECONDS = 60
CHUNK_DELAY_SECONDS = 1

BIGQUERY_TABLE_OPTIONS = {
    "fact_meta_delivery_ad": {
        "merge_keys": ["ad_id", "date_start"],
        "partition_field": "date_start",
        "cluster_fields": ["account_id", "campaign_id", "adset_id", "ad_id"],
    },

}


def _date_chunks(start: datetime, end: datetime, chunk_size_days: int):
    one_day = timedelta(days=1)
    chunk_delta = timedelta(days=chunk_size_days - 1)
    current = start
    while current <= end:
        chunk_end = min(current + chunk_delta, end)
        yield current.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d")
        current = chunk_end + one_day


def _is_rate_limit_error(err: GraphAPIError) -> bool:
    msg = str(err)
    return (
        "Application request limit reached" in msg
        or "code': 4" in msg
        or 'code": 4' in msg
    )


def get_bigquery_load_options(table_name: str) -> dict[str, Any]:
    return dict(BIGQUERY_TABLE_OPTIONS.get(table_name, {}))


def _fetch_records_for_range(
    *,
    level: str,
    from_date: str,
    to_date: str,
    chunk_size_days: int,
    breakdowns: Optional[List[str]],
    ad_account_ids: List[str],
    max_workers: int,
) -> List[Dict[str, Any]]:
    start_dt = datetime.strptime(from_date, "%Y-%m-%d")
    end_dt = datetime.strptime(to_date, "%Y-%m-%d")

    all_records: List[Dict[str, Any]] = []
    for since, until in _date_chunks(start_dt, end_dt, chunk_size_days):
        logger.info("Processing range chunk", since=since, until=until)
        attempts = 0
        while True:
            attempts += 1
            try:
                chunk_rows = fetch_insights(
                    level=level,
                    since=since,
                    until=until,
                    breakdowns=breakdowns,
                    ad_account_ids=ad_account_ids,
                    max_workers=max_workers,
                )
                all_records.extend(chunk_rows)
                break
            except GraphAPIError as exc:
                if _is_rate_limit_error(exc) and attempts == 1:
                    logger.warning(
                        "Rate limit hit for chunk; retrying once",
                        since=since,
                        until=until,
                        sleep_seconds=RATE_LIMIT_SLEEP_SECONDS,
                    )
                    time.sleep(RATE_LIMIT_SLEEP_SECONDS)
                    continue
                logger.error("Chunk failed; continuing", since=since, until=until, error=str(exc))
                break
        if CHUNK_DELAY_SECONDS > 0:
            time.sleep(CHUNK_DELAY_SECONDS)

    return all_records


def _process_one_chunk(
    *,
    level: str,
    since: str,
    until: str,
    breakdowns: Optional[List[str]],
    ad_account_ids: List[str],
    max_workers: int,
    table_name: str,
    unique_cols: List[str],
    db_config: Optional[PostgresConfig],
    to_db: bool,
    to_bigquery: bool,
    bq_write_disposition: str,
    profile: Optional[str],
) -> int:
    """Fetch + transform + load a single since/until window. Returns row count."""
    attempts = 0
    chunk_rows: List[Dict[str, Any]] = []
    while True:
        attempts += 1
        try:
            chunk_rows = fetch_insights(
                level=level,
                since=since,
                until=until,
                breakdowns=breakdowns,
                ad_account_ids=ad_account_ids,
                max_workers=max_workers,
            )
            break
        except GraphAPIError as exc:
            if _is_rate_limit_error(exc) and attempts == 1:
                logger.warning(
                    "Rate limit hit for chunk; retrying once",
                    since=since,
                    until=until,
                    sleep_seconds=RATE_LIMIT_SLEEP_SECONDS,
                )
                time.sleep(RATE_LIMIT_SLEEP_SECONDS)
                continue
            logger.error("Chunk failed; skipping", since=since, until=until, error=str(exc))
            return 0

    if not chunk_rows:
        return 0

    df = normalize_insights(chunk_rows, level=level, breakdowns=breakdowns)
    if len(df) > len(chunk_rows):
        df = df.drop_duplicates()

    if to_db and db_config is not None:
        save_df_to_postgres_upsert(
            df,
            table_name,
            unique_cols=unique_cols,
            conn_string=db_config.conn_string,
        )

    if to_bigquery:
        from src.etl.load.bigquery_loader import save_df_to_bigquery

        bq_options = get_bigquery_load_options(table_name)
        save_df_to_bigquery(
            df,
            table_name=table_name,
            profile=profile,
            write_disposition=bq_write_disposition,
            **bq_options,
        )

    return len(df)


def run_meta_insights(
    *,
    level: str = "ad",
    date_preset: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    chunk_size_days: int = 7,
    breakdowns: Optional[List[str]] = None,
    profile: Optional[str] = None,
    to_db: bool = True,
    to_bigquery: bool = False,
    bq_write_disposition: str = "WRITE_APPEND",
    bq_table_name: Optional[str] = None,
    csv_path: Optional[str] = None,
    db_config: Optional[PostgresConfig] = None,
    ad_account_ids: Optional[List[str]] = None,
    max_workers: int = 1,
    force: bool = False,
):
    """
    Unified delivery insights pipeline.

    Use either:
    - date_preset mode (daily/snapshot pull), or
    - explicit from_date + to_date mode (range pull).
    """
    using_preset = bool(date_preset)
    using_range = bool(from_date and to_date)
    if using_preset == using_range:
        raise ValueError("Use either date_preset OR from_date+to_date.")

    if using_range and chunk_size_days < 1:
        raise ValueError("chunk_size_days must be >= 1.")

    accounts = ad_account_ids or load_ad_account_ids(profile)
    logger.info(
        "Starting insights pipeline",
        level=level,
        mode="preset" if using_preset else "range",
        date_preset=date_preset,
        from_date=from_date,
        to_date=to_date,
        breakdowns=breakdowns or [],
        account_count=len(accounts),
    )

    table_name = bq_table_name or get_insights_table_name(level, breakdowns)
    unique_cols = UNIQUE_KEYS.get(table_name)
    if to_db and db_config is not None and unique_cols is None:
        raise ValueError(f"No UNIQUE_KEYS defined for table '{table_name}'")

    if using_preset:
        try:
            records = fetch_insights(
                level=level,
                date_preset=date_preset,
                breakdowns=breakdowns,
                ad_account_ids=accounts,
                max_workers=max_workers,
            )
        except GraphAPIError as exc:
            logger.error("Failed to fetch insights", error=str(exc))
            return None

        logger.info("Insights fetched", rows=len(records))
        if not records:
            logger.info("No insights rows returned")
            return None

        df = normalize_insights(records, level=level, breakdowns=breakdowns)
        if len(df) > len(records):
            logger.warning(
                "Normalized rows exceed raw rows; dropping duplicates",
                normalized=len(df),
                raw=len(records),
            )
            df = df.drop_duplicates()
        logger.info("Insights normalized", rows=len(df), columns=len(df.columns))

        if csv_path:
            save_df_to_csv(df, csv_path)

        if to_db and db_config is not None:
            save_df_to_postgres_upsert(
                df,
                table_name,
                unique_cols=unique_cols,
                conn_string=db_config.conn_string,
            )

        if to_bigquery:
            from src.etl.load.bigquery_loader import save_df_to_bigquery

            bq_options = get_bigquery_load_options(table_name)
            save_df_to_bigquery(
                df,
                table_name=table_name,
                profile=profile,
                write_disposition=bq_write_disposition,
                **bq_options,
            )

        return df

    # Range mode: process each chunk independently so checkpoints can skip
    # already-completed windows and a mid-range failure doesn't lose work.
    completed: set = set()
    if to_db and db_config is not None and not force:
        try:
            completed = fetch_completed(
                conn_string=db_config.conn_string,
                profile=profile,
                level=level,
                breakdowns=breakdowns,
            )
        except Exception as exc:
            logger.warning("Could not load checkpoints; processing all chunks", error=str(exc))
            completed = set()

    start_dt = datetime.strptime(from_date or "", "%Y-%m-%d")
    end_dt = datetime.strptime(to_date or "", "%Y-%m-%d")
    total_rows = 0
    skipped = 0
    processed = 0

    for since, until in _date_chunks(start_dt, end_dt, chunk_size_days):
        if (since, until) in completed:
            logger.info("Skipping already-completed chunk", since=since, until=until)
            skipped += 1
            continue

        logger.info("Processing range chunk", since=since, until=until)
        rows = _process_one_chunk(
            level=level,
            since=since,
            until=until,
            breakdowns=breakdowns,
            ad_account_ids=accounts,
            max_workers=max_workers,
            table_name=table_name,
            unique_cols=unique_cols or [],
            db_config=db_config,
            to_db=to_db,
            to_bigquery=to_bigquery,
            bq_write_disposition=bq_write_disposition,
            profile=profile,
        )
        total_rows += rows
        processed += 1

        if to_db and db_config is not None:
            try:
                mark_completed(
                    conn_string=db_config.conn_string,
                    profile=profile,
                    level=level,
                    breakdowns=breakdowns,
                    since=since,
                    until=until,
                    rows_loaded=rows,
                )
            except Exception as exc:
                logger.warning("Could not write checkpoint; chunk will rerun next time", error=str(exc))

        if CHUNK_DELAY_SECONDS > 0:
            time.sleep(CHUNK_DELAY_SECONDS)

    logger.info(
        "Insights range completed",
        chunks_processed=processed,
        chunks_skipped=skipped,
        rows_total=total_rows,
    )
    return None
