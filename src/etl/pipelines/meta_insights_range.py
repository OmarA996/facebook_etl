# src/etl/pipelines/meta_insights_range.py

import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from src.etl.extract.meta_insights import fetch_insights
from src.etl.transform.meta_insights import normalize_insights, get_insights_table_name
from src.etl.load.postgres_loader import insert_raw_insights, save_df_to_postgres_upsert
from src.etl.load.csv_loader import save_df_to_csv
from src.clients.graph_client import GraphAPIError
from src.schema.unique_keys import UNIQUE_KEYS
from src.config import PostgresConfig, load_ad_account_ids

from src.utils.logger import get_logger

logger = get_logger(__name__)

RATE_LIMIT_SLEEP_SECONDS = 60
CHUNK_DELAY_SECONDS = 1


def _date_chunks(start: datetime, end: datetime, chunk_size_days: int):
    """
    Yield (since, until) date pairs in 'YYYY-MM-DD' format,
    covering the inclusive range [start, end] in chunks.
    """
    one_day = timedelta(days=1)
    chunk_delta = timedelta(days=chunk_size_days - 1)

    current = start
    while current <= end:
        chunk_end = min(current + chunk_delta, end)
        yield (
            current.strftime("%Y-%m-%d"),
            chunk_end.strftime("%Y-%m-%d"),
        )
        current = chunk_end + one_day


def _is_rate_limit_error(err: GraphAPIError) -> bool:
    msg = str(err)
    return (
        "Application request limit reached" in msg
        or "code': 4" in msg
        or 'code": 4' in msg
    )


def run_meta_insights_range(
    level: str,
    from_date: str,
    to_date: str,
    chunk_size_days: int = 7,
    breakdowns: Optional[List[str]] = None,
    to_db: bool = True,
    csv_path: Optional[str] = None,
    db_config: Optional[PostgresConfig] = None,
    ad_account_ids: Optional[List[str]] = None,
    max_workers: int = 1,
):
    """
    Fetch Meta insights for a date range [from_date, to_date],
    split into smaller chunks so each API call is manageable.
    """

    start_dt = datetime.strptime(from_date, "%Y-%m-%d")
    end_dt = datetime.strptime(to_date, "%Y-%m-%d")

    all_records: List[Dict[str, Any]] = []

    logger.info(
        "Fetching range insights",
        level=level,
        from_date=from_date,
        to_date=to_date,
        chunk_days=chunk_size_days,
        breakdowns=breakdowns or []
    )

    accounts = ad_account_ids or load_ad_account_ids()

    for since, until in _date_chunks(start_dt, end_dt, chunk_size_days):
        logger.info("Processing chunk", range=f"{since} -> {until}")

        attempts = 0
        while True:
            attempts += 1
            try:
                chunk_records = fetch_insights(
                    level=level,
                    since=since,
                    until=until,
                    breakdowns=breakdowns,
                    ad_account_ids=accounts,
                    max_workers=max_workers,
                )
                break
            except GraphAPIError as e:
                if _is_rate_limit_error(e) and attempts == 1:
                    logger.warning(
                        "Rate limit hit",
                        range=f"{since}->{until}",
                        sleep_seconds=RATE_LIMIT_SLEEP_SECONDS,
                        action="Retrying once"
                    )
                    time.sleep(RATE_LIMIT_SLEEP_SECONDS)
                    continue
                logger.error("Error processing chunk", range=f"{since}->{until}", error=str(e))
                chunk_records = []
                break

        logger.info("Chunk fetched", range=f"{since} -> {until}", rows=len(chunk_records))
        all_records.extend(chunk_records)
        if CHUNK_DELAY_SECONDS > 0:
            time.sleep(CHUNK_DELAY_SECONDS)

    logger.info("Total rows fetched", count=len(all_records))

    if not all_records:
        logger.info("No data returned for this range")
        return None

    raw_sample_ids = {r.get("ad_id") for r in all_records if r.get("ad_id")}
    logger.info("Raw sample ad_ids", sample=list(raw_sample_ids)[:5])

    # Insert raw payloads before normalization
    if to_db and db_config is not None:
        insert_raw_insights(all_records, level=level, breakdowns=breakdowns, conn_string=db_config.conn_string)

    logger.info("Normalizing records")
    df = normalize_insights(all_records, level=level, breakdowns=breakdowns)
    norm_count = len(df)
    if norm_count > len(all_records):
        logger.warning(
            "Normalized rows exceed raw rows",
            normalized=norm_count,
            raw=len(all_records),
            action="Dropping duplicates"
        )
        df = df.drop_duplicates()
        norm_count = len(df)
    logger.info("Normalized stats", rows=norm_count, shape=str(df.shape))

    if csv_path:
        logger.info("Saving to CSV", path=csv_path)
        save_df_to_csv(df, csv_path)

    if to_db and db_config is not None:
        table_name = get_insights_table_name(level, breakdowns)
        unique_cols = UNIQUE_KEYS.get(table_name)
        if unique_cols is None:
            raise ValueError(f"No UNIQUE_KEYS defined for table '{table_name}'")
        logger.info("Upserting to DB", table=table_name, unique_keys=unique_cols)
        save_df_to_postgres_upsert(
            df,
            table_name,
            unique_cols=unique_cols,
            conn_string=db_config.conn_string,
        )

    return df
