from typing import Optional

import pandas as pd

from src.clients.graph_client import GraphAPIError
from src.etl.extract.campaigns import fetch_campaigns
from src.etl.transform.core import (
    apply_rename_map,
    flatten_json,
    fill_numeric_keep_nulls,
    ensure_id_and_name,
    coerce_datetime_columns,
)
from src.etl.load.csv_loader import save_df_to_csv
from src.etl.load.postgres_loader import save_df_to_postgres_upsert
from src.schema.unique_keys import UNIQUE_KEYS
from src.config import PostgresConfig, load_ad_account_ids
from src.utils.logger import get_logger

logger = get_logger(__name__)


def run_campaigns_info(
    csv_path: Optional[str] = None,
    to_db: bool = True,
    effective_statuses: Optional[list[str]] = None,
    db_config: Optional[PostgresConfig] = None,
    ad_account_ids: Optional[list[str]] = None,
    max_workers: int = 1,
) -> Optional[pd.DataFrame]:
    """
    Fetch campaigns, flatten, optional CSV, optional DB upsert.
    """
    logger.info("Fetching campaigns")
    accounts = ad_account_ids or load_ad_account_ids()
    try:
        records = fetch_campaigns(
            effective_statuses=effective_statuses,
            ad_account_ids=accounts,
            max_workers=max_workers,
        )
    except GraphAPIError as e:
        logger.error("Error fetching campaigns", error=str(e))
        return None

    logger.info("Fetched campaigns", count=len(records))
    if not records:
        logger.warning("No campaigns returned")
        return None

    df = flatten_json(records)
    df = ensure_id_and_name(df, id_col="campaign_id", name_col="campaign_name")
    df = apply_rename_map(df, "campaigns-info", table_name="dim_meta_campaigns")
    df = coerce_datetime_columns(df, ["created_time", "start_time", "stop_time"])
    df = fill_numeric_keep_nulls(df)
    logger.info("DataFrame ready", shape=df.shape)

    if csv_path:
        save_df_to_csv(df, csv_path)

    if to_db:
        table_name = "dim_meta_campaigns"
        unique_cols = UNIQUE_KEYS.get(table_name)
        if unique_cols is None:
            raise ValueError(f"No UNIQUE_KEYS defined for table '{table_name}'")
        logger.info("Upserting to Postgres", table=table_name, unique_cols=unique_cols)
        save_df_to_postgres_upsert(
            df,
            table_name,
            unique_cols=unique_cols,
            conn_string=db_config.conn_string if db_config else None,
        )

    return df
