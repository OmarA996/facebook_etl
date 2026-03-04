# src/etl/pipelines/meta_insights_daily.py

from typing import Optional, List

from src.etl.extract.meta_insights import fetch_insights
from src.etl.transform.meta_insights import normalize_insights, get_insights_table_name
from src.etl.load.csv_loader import save_df_to_csv
from src.etl.load.postgres_loader import insert_raw_insights, save_df_to_postgres_upsert
from src.clients.graph_client import GraphAPIError
from src.schema.unique_keys import UNIQUE_KEYS
from src.config import PostgresConfig, load_ad_account_ids


from src.utils.logger import get_logger

logger = get_logger(__name__)

def run_meta_insights_daily(
    level: str = "ad",
    date_preset: str = "yesterday",
    breakdowns: Optional[List[str]] = None,
    to_db: bool = True,
    csv_path: Optional[str] = None,
    db_config: Optional[PostgresConfig] = None,
    ad_account_ids: Optional[List[str]] = None,
    max_workers: int = 1,
):
    """
    Run a daily Meta insights pipeline using a date_preset
    (e.g. 'yesterday', 'last_7d').

    level: 'ad', 'adset', 'campaign', or 'account'
    """

    logger.info("Fetching insights", level=level, date_preset=date_preset)

    accounts = ad_account_ids or load_ad_account_ids()
    try:
        records = fetch_insights(
            level=level,
            date_preset=date_preset,
            breakdowns=breakdowns,
            ad_account_ids=accounts,
            max_workers=max_workers,
        )
    except GraphAPIError as e:
        logger.error("Error fetching insights", error=str(e))
        return None
    logger.info("Fetched records", count=len(records))

    if not records:
        logger.info("No records returned")
        return None
    
    raw_sample_ids = {r.get("ad_id") for r in records if r.get("ad_id")}
    logger.info("Raw sample ad_ids", sample=list(raw_sample_ids)[:5])
    logger.info("Breakdowns", breakdowns=breakdowns or [])

    # Insert raw payloads before normalization
    if to_db and db_config is not None:
        insert_raw_insights(records, level=level, breakdowns=breakdowns, conn_string=db_config.conn_string)

    logger.info("Normalizing records")
    df = normalize_insights(records, level=level, breakdowns=breakdowns)
    norm_count = len(df)
    if norm_count > len(records):
        logger.warning("Normalized rows exceed raw rows", normalized=norm_count, raw=len(records), action="Dropping duplicates")
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
