from typing import Optional

import pandas as pd

from src.clients.graph_client import GraphAPIError
from src.etl.extract.adsets import fetch_adsets
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


def run_adsets_info(
    csv_path: Optional[str] = None,
    to_db: bool = True,
    effective_statuses: Optional[list[str]] = None,
    db_config: Optional[PostgresConfig] = None,
    ad_account_ids: Optional[list[str]] = None,
    max_workers: int = 1,
) -> Optional[pd.DataFrame]:
    """
    Fetch adsets, flatten, optional CSV, optional DB upsert.
    """
    logger.info("Fetching adsets")
    accounts = ad_account_ids or load_ad_account_ids()
    try:
        records = fetch_adsets(
            effective_statuses=effective_statuses,
            ad_account_ids=accounts,
            max_workers=max_workers,
        )
    except GraphAPIError as e:
        logger.error("Error fetching adsets", error=str(e))
        return None

    logger.info("Fetched adsets", count=len(records))
    if not records:
        logger.warning("No adsets returned")
        return None

    df = flatten_json(records)
    df = ensure_id_and_name(df, id_col="adset_id", name_col="adset_name")
    df = apply_rename_map(df, "adsets-info", table_name="dim_meta_adsets")
    df = coerce_datetime_columns(df, ["created_time", "start_time", "end_time"])
    df = fill_numeric_keep_nulls(df)
    logger.info("DataFrame ready", shape=df.shape)

    if csv_path:
        save_df_to_csv(df, csv_path)

    if to_db:
        table_name = "dim_meta_adsets"
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
